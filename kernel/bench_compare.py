#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ベンチマーク結果を同じ表にまとめ、データ選抜の一致も確認する。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from public_bench import HARNESS_VERSION, atomic_write, sha256_file  # noqa: E402


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_run(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError(f"--run は LABEL=DIR 形式です: {value}")
    label, directory = value.split("=", 1)
    if not label or not directory:
        raise ValueError(f"--run は LABEL=DIR 形式です: {value}")
    return label, Path(directory)


def run_summary(directory: Path) -> dict:
    summary_path = directory / "summary.json"
    base = load_json(summary_path) if summary_path.exists() else {}
    by_name = {x.get("name"): x for x in base.get("summaries", [])
               if isinstance(x, dict) and x.get("name")}
    eval_summaries = []
    for path in sorted(directory.glob("*.summary.json")):
        if path.name in {"speed.summary.json"}:
            continue
        try:
            item = load_json(path)
            if path.name.endswith(".eval.summary.json") and item.get("data_n") is not None:
                eval_summaries.append((path, item))
                continue
            if item.get("name"):
                by_name[item["name"]] = item
        except Exception:
            continue
    for path, item in eval_summaries:
        # HumanEval の生成サマリーを、採点済みの pass@1 で上書きする。
        current = by_name.get("humaneval", {})
        by_name["humaneval"] = {
            **current,
            "name": "humaneval",
            "n": item.get("data_n"),
            "scored_n": item.get("data_n"),
            "correct": item.get("pass"),
            "accuracy": item.get("accuracy_over_data"),
            "failed_n": item.get("fail"),
            "eval_summary": str(path),
        }
    if not any(path.name.endswith("humaneval.eval.summary.json") for path, _ in eval_summaries):
        detail = directory / "humaneval.eval.jsonl"
        if detail.exists():
            try:
                rows = [json.loads(line) for line in detail.read_text(
                    encoding="utf-8").splitlines() if line.strip()]
                current = by_name.get("humaneval", {})
                passed = sum(bool(row.get("pass")) for row in rows)
                by_name["humaneval"] = {
                    **current,
                    "name": "humaneval",
                    "n": len(rows),
                    "scored_n": len(rows),
                    "correct": passed,
                    "accuracy": passed / len(rows) if rows else None,
                    "failed_n": len(rows) - passed,
                    "eval_detail": str(detail),
                }
            except Exception:
                pass
    return {**base, "summaries": list(by_name.values())}


def manifests(directory: Path) -> dict[str, dict]:
    out = {}
    for path in directory.glob("*.manifest.json"):
        try:
            out[path.name.removesuffix(".manifest.json")] = load_json(path)
        except Exception:
            pass
    return out


def make_report(runs: list[tuple[str, Path]]) -> tuple[dict, str]:
    data = {"harness_version": HARNESS_VERSION, "created_at": dt.datetime.now(
        dt.timezone.utc).isoformat(), "runs": {}}
    bench_names = set()
    for label, directory in runs:
        run = run_summary(directory)
        summaries = {x.get("name"): x for x in run.get("summaries", [])
                     if isinstance(x, dict) and x.get("name")}
        manifests_data = manifests(directory)
        data["runs"][label] = {
            "directory": str(directory),
            "summary": run,
            "manifests": {
                name: {
                    "selected_n": manifest.get("selected_n"),
                    "selected_rows_sha256": manifest.get("selected_rows_sha256"),
                    "manifest_sha256": sha256_file(directory / f"{name}.manifest.json"),
                }
                for name, manifest in manifests_data.items()
            },
        }
        bench_names.update(summaries)

    lines = [
        "# ベンチマーク比較",
        "",
        f"- harness: `{HARNESS_VERSION}`",
        f"- generated: `{data['created_at']}`",
        "",
        "| ベンチマーク | " + " | ".join(label for label, _ in runs) + " |",
        "|---|" + "---:|" * len(runs),
    ]
    for name in sorted(bench_names):
        cells = []
        for label, _ in runs:
            summary = next((x for x in data["runs"][label]["summary"].get("summaries", [])
                            if x.get("name") == name), None)
            if not summary:
                cells.append("—")
                continue
            acc = summary.get("accuracy")
            score = (f"{summary.get('correct')}/{summary.get('scored_n')} "
                     f"({100*acc:.1f}%)" if acc is not None else "未完了")
            failed = summary.get("failed_n")
            if failed is None:
                file_name = summary.get("file")
                if file_name and Path(file_name).exists():
                    try:
                        failed = sum(1 for line in Path(file_name).read_text(
                            encoding="utf-8").splitlines()
                            if line.strip() and (json.loads(line).get("error")
                                                 or not json.loads(line).get("content", "").strip()))
                    except Exception:
                        failed = None
            if failed is None and summary.get("n") is not None and summary.get("scored_n") is not None:
                failed = summary["n"] - summary["scored_n"]
            cells.append(f"{score}; 失敗 {failed if failed is not None else '?'}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    lines += ["", "## データ選抜の一致", ""]
    for name in sorted(bench_names):
        entries = []
        for label, _ in runs:
            manifest = data["runs"][label]["manifests"].get(name)
            entries.append(f"{label}={manifest.get('selected_rows_sha256') if manifest else 'なし'}")
        lines.append(f"- `{name}`: " + ", ".join(entries))

    speed_rows = []
    for label, directory in runs:
        path = directory / "speed.summary.json"
        if path.exists():
            speed_rows.append((label, load_json(path)))
    if speed_rows:
        lines += ["", "## 速度", "", "| 実行 | 平均秒 | 中央値秒 | p95秒 | 生成tok/s |", "|---|---:|---:|---:|---:|"]
        for label, speed in speed_rows:
            lines.append("| %s | %s | %s | %s | %s |" % (
                label,
                _fmt(speed.get("mean_sec")), _fmt(speed.get("median_sec")),
                _fmt(speed.get("p95_sec")), _fmt(speed.get("median_predicted_tps"))))
    return data, "\n".join(lines) + "\n"


def _fmt(value) -> str:
    return "—" if value is None else f"{float(value):.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", required=True,
                    help="比較対象 LABEL=結果ディレクトリ（2つ以上推奨）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    try:
        runs = [parse_run(value) for value in args.run]
    except ValueError as exc:
        ap.error(str(exc))
    if len(runs) < 1:
        ap.error("少なくとも1つの --run が必要です")
    for _, directory in runs:
        if not directory.exists():
            ap.error(f"結果ディレクトリがありません: {directory}")
    data, markdown = make_report(runs)
    out = Path(args.out or f"benchmark-comparison-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.md")
    if out.suffix.lower() == ".json":
        json_path = out
        md_path = out.with_suffix(".md")
    else:
        md_path = out
        json_path = out.with_suffix(".json")
    atomic_write(md_path, markdown)
    atomic_write(json_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"Markdown: {md_path}\nJSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
