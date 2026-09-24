#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HumanEvalの失敗候補だけを実行結果付きで修復する補助器。

生成と採点を分離したまま、既存の失敗行をモデルへ戻し、テストの失敗理由を
含めて再生成する。修復前のJSONLは変更せず、別ファイルへ原子的に保存する。
各候補の実行は既存の ``he_eval.run_case`` の制限付き子プロセスを通る。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HE_DIR = HERE.parent / "LocalAI改良" / "tools" / "ops" / "humaneval"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HE_DIR))

import public_bench as pb  # noqa: E402
import he_eval  # noqa: E402


VERSION = "1.0.0"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def atomic_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                     dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _tail(value: str, limit: int = 1800) -> str:
    value = (value or "").strip()
    return value if len(value) <= limit else value[-limit:]


def repair_prompt(problem: dict, current_code: str, feedback: dict) -> str:
    reason = feedback.get("why") or "the candidate failed the tests"
    stderr = _tail(feedback.get("stderr", ""))
    return (
        "Fix the Python function below. Return only the corrected code, preferably "
        "inside one python code block, with no explanation. Preserve the required "
        "function name and signature. The candidate was executed against the "
        "official tests and failed, so reason from the failure instead of merely "
        "rewriting it.\n\n"
        f"Original task:\n{problem['prompt']}\n\n"
        f"Current candidate:\n{current_code or '[missing]'}\n\n"
        f"Test result: {reason}\n"
        f"stderr/stdout tail:\n{stderr or '[none]'}\n\n"
        "Corrected code:"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--gen", required=True,
                    help="元のHumanEval JSONL（変更しない）")
    ap.add_argument("--out", required=True,
                    help="修復後のJSONL")
    ap.add_argument("--url", default=pb.DEFAULT_URL)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--retry-backoff", type=float, default=0.5)
    ap.add_argument("--repair-rounds", type=int, default=2)
    ap.add_argument("--eval-timeout", type=float, default=10)
    ap.add_argument("--memory-mb", type=int, default=512)
    ap.add_argument("--output-mb", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--sandbox", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--think", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()
    if min(args.max_tokens, args.timeout, args.repair_rounds,
           args.eval_timeout, args.memory_mb, args.output_mb) <= 0:
        ap.error("token/timeout/rounds/resource は正数が必要です")
    if args.retries < 0 or args.retry_backoff < 0:
        ap.error("retries と retry-backoff は0以上が必要です")

    data = Path(args.data)
    source = Path(args.gen)
    out = Path(args.out)
    problems = read_jsonl(data)
    if args.limit:
        problems = problems[:args.limit]
    source_rows = {str(row.get("task_id") or row.get("id")): row
                   for row in read_jsonl(source)}
    client = pb.LocalClient(
        args.url, args.think, args.max_tokens, args.timeout,
        retries=args.retries, retry_backoff=args.retry_backoff, seed=args.seed,
    )

    result_rows: list[dict] = []
    repaired = 0
    passed_initially = 0
    started = time.monotonic()
    for index, problem in enumerate(problems, 1):
        task_id = str(problem.get("task_id") or problem.get("id"))
        original = dict(source_rows.get(task_id) or {
            "task_id": task_id, "raw": "", "error": "missing_generation"
        })
        current_code = he_eval.extract(
            str(original.get("raw", original.get("content", "")) or ""))
        trial = he_eval.run_case(
            problem, {"raw": current_code}, args.eval_timeout, args.memory_mb,
            args.output_mb, args.sandbox)
        repair_attempts: list[dict] = []
        if trial.get("pass"):
            passed_initially += 1
            row = dict(original)
            row["repair_status"] = "not_needed"
        else:
            row = dict(original)
            for round_no in range(1, args.repair_rounds + 1):
                result = client.call(
                    repair_prompt(problem, current_code, trial),
                    f"{task_id}::repair-{round_no}",
                )
                candidate_text = result.get("content", "") or ""
                candidate_code = he_eval.extract(candidate_text)
                candidate_trial = he_eval.run_case(
                    problem, {"raw": candidate_code}, args.eval_timeout,
                    args.memory_mb, args.output_mb, args.sandbox)
                repair_attempts.append({
                    "round": round_no,
                    "profile": result.get("request", {}),
                    "elapsed_sec": result.get("elapsed_sec", 0),
                    "error": result.get("error"),
                    "trial": candidate_trial,
                })
                if candidate_code.strip():
                    current_code = candidate_code
                trial = candidate_trial
                if trial.get("pass"):
                    repaired += 1
                    row["raw"] = current_code
                    row["content"] = current_code
                    row["error"] = None
                    row["repair_status"] = "repaired"
                    break
            else:
                row["repair_status"] = "still_failed"
        row["repair_harness_version"] = VERSION
        row["repair_attempts"] = repair_attempts
        row["final_trial"] = trial
        row["source_task_id"] = task_id
        result_rows.append(row)
        atomic_jsonl(out, result_rows)
        if index == 1 or index % 10 == 0 or index == len(problems):
            state = "PASS" if trial.get("pass") else trial.get("why", "FAIL")
            print(f"  {index}/{len(problems)} {task_id} {state}", flush=True)

    # 修復後の全分母を既存の採点器で再集計する。
    detail = out.with_suffix(".eval.jsonl")
    summary_path = out.with_suffix(".eval.summary.json")
    summary, details = he_eval.evaluate(
        data, out, args.eval_timeout, args.memory_mb, args.output_mb,
        args.sandbox, args.limit)
    summary.update({
        "repair_harness_version": VERSION,
        "source_generation": str(source),
        "repaired_n": repaired,
        "passed_initially_n": passed_initially,
        "elapsed_sec_with_repair": time.monotonic() - started,
    })
    he_eval.jsonl_write(detail, details)
    he_eval.json_write(summary_path, summary)
    print(
        f"repair pass@1 = {summary['pass']}/{summary['data_n']} = "
        f"{100.0 * (summary['accuracy_over_data'] or 0):.1f}% "
        f"（初回PASS {passed_initially}, 修復成功 {repaired}）",
        flush=True,
    )
    print(f"generation: {out}\nsummary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
