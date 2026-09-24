#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同じ条件で llama-server の速度を測る小さな再利用可能ハーネス。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from public_bench import (  # noqa: E402
    HARNESS_VERSION,
    LocalClient,
    atomic_write,
    collect_runtime_metadata,
    collect_server_metadata,
    redact_url,
)


PROMPTS = [
    "Return only the next prime number after 100.",
    "Write one short sentence explaining why the sky appears blue.",
    "Compute 37 * 29. Return only the integer.",
    "Return a Python function named square(x) that returns x*x, with no explanation.",
]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    index = (len(xs) - 1) * q
    low = int(index)
    high = min(low + 1, len(xs) - 1)
    return xs[low] + (xs[high] - xs[low]) * (index - low)


def write_json(path: Path, obj: dict) -> None:
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080/v1/chat/completions")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--retry-backoff", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--think", action="store_true")
    args = ap.parse_args()
    if args.repeat <= 0 or args.warmup < 0:
        ap.error("--repeat は正数、--warmup は0以上が必要です")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out_dir or Path(__file__).resolve().parent / "bench_results" /
               f"speed-{stamp}")
    out.mkdir(parents=True, exist_ok=True)
    client = LocalClient(args.url, args.think, args.max_tokens, args.timeout,
                         retries=args.retries, retry_backoff=args.retry_backoff,
                         seed=args.seed)
    for i in range(args.warmup):
        result = client.call(PROMPTS[i % len(PROMPTS)], f"warmup/{i}")
        if result.get("error"):
            print(f"warmup error: {result['error']}", file=sys.stderr)

    rows = []
    started = time.monotonic()
    for repeat in range(args.repeat):
        for prompt_index, prompt in enumerate(PROMPTS):
            rid = f"p{prompt_index}/r{repeat}"
            result = client.call(prompt, rid)
            rows.append({
                "id": rid,
                "prompt_index": prompt_index,
                "repeat": repeat,
                "elapsed_sec": result.get("elapsed_sec", 0),
                "timings": result.get("timings") or {},
                "usage": result.get("usage"),
                "model": result.get("model"),
                "error": result.get("error"),
                "error_type": result.get("error_type"),
                "http_status": result.get("http_status"),
                "attempts": result.get("attempts") or [],
                "retry_count": result.get("retry_count", 0),
            })
            print(f"  {rid}: {rows[-1]['elapsed_sec']:.3f}s "
                  f"{rows[-1]['error'] or 'ok'}", flush=True)

    successful = [r for r in rows if not r.get("error")]
    elapsed = [float(r.get("elapsed_sec", 0)) for r in successful]
    tps = [float((r.get("timings") or {}).get("predicted_per_second", 0) or 0)
           for r in successful if (r.get("timings") or {}).get("predicted_per_second")]
    prompt_tps = [float((r.get("timings") or {}).get("prompt_per_second", 0) or 0)
                  for r in successful if (r.get("timings") or {}).get("prompt_per_second")]
    summary = {
        "harness_version": HARNESS_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "url": redact_url(args.url),
        "repeat": args.repeat,
        "warmup": args.warmup,
        "n": len(rows),
        "successful_n": len(successful),
        "failed_n": len(rows) - len(successful),
        "elapsed_total_sec": time.monotonic() - started,
        "mean_sec": statistics.mean(elapsed) if elapsed else None,
        "median_sec": statistics.median(elapsed) if elapsed else None,
        "p95_sec": percentile(elapsed, 0.95),
        "mean_predicted_tps": statistics.mean(tps) if tps else None,
        "median_predicted_tps": statistics.median(tps) if tps else None,
        "mean_prompt_tps": statistics.mean(prompt_tps) if prompt_tps else None,
        "error_types": {
            str(k): sum(1 for r in rows if (r.get("error_type") or "error") == k)
            for k in sorted({r.get("error_type") or "error" for r in rows
                             if r.get("error")})
        },
        "runtime": collect_runtime_metadata(),
        "server": collect_server_metadata(args.url),
    }
    jsonl = out / "speed.jsonl"
    atomic_write(jsonl, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    write_json(out / "speed.summary.json", summary)
    write_json(out / "config.json", {
        "harness_version": HARNESS_VERSION,
        "argv": sys.argv,
        "url": redact_url(args.url),
        "max_tokens": args.max_tokens,
        "think": args.think,
        "seed": args.seed,
        "repeat": args.repeat,
        "warmup": args.warmup,
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"結果: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
