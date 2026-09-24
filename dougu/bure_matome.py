#!/usr/bin/env python3
"""kekka/ 枝から bure seed × runner の正解率の揺れを集計する。"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from kurabe import records_from


def list_files(ref: str) -> list[tuple[str, str]]:
    proc = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, "kekka/"],
                          text=True, encoding="utf-8", capture_output=True)
    if proc.returncode == 0:
        return [(name, "git") for name in proc.stdout.splitlines()
                if name.endswith(".tochuu.jsonl") and re.search(r"_bure\d+_f\d+(?:_|\.)", name)]
    folder = Path("kekka")
    if folder.is_dir():
        return [(str(path), "file") for path in folder.glob("*.tochuu.jsonl")
                if re.search(r"_bure\d+_f\d+(?:_|\.)", path.name)]
    raise ValueError(f"{ref} の kekka/ を読めない")


def get_text(name: str, mode: str, ref: str) -> str:
    if mode == "file":
        return Path(name).read_text(encoding="utf-8")
    proc = subprocess.run(["git", "show", ref + ":" + name],
                          text=True, encoding="utf-8", capture_output=True, check=True)
    return proc.stdout


def main() -> int:
    ref = sys.argv[1] if len(sys.argv) > 1 else "origin/kekka"
    try:
        files = list_files(ref)
        if not files:
            print("bure 結果なし (kekka/ に *_bure<N>_f*.tochuu.jsonl が必要)")
            return 0
        groups = {}
        for name, mode in files:
            base = Path(name).name
            m = re.match(r"7dan_(ubuntu-24\.04(?:-arm)?)(.*?)_bure(\d+)(_.+)\.tochuu\.jsonl$", base)
            if not m:
                continue
            runner, setting, seed, suffix = m.groups()
            arch = "arm" if runner.endswith("-arm") else "x64"
            key = (setting, suffix)
            rows = records_from(get_text(name, mode, ref), name)
            groups.setdefault(key, {}).setdefault(arch, {})[int(seed)] = sum(rows.values()) / len(rows)
        if not groups:
            raise ValueError("bure 結果のファイル名を解釈できない")
        print("設定                         機械   runs   平均     SD      最小–最大")
        for key, machines in sorted(groups.items()):
            setting, suffix = key
            for arch in ("x64", "arm"):
                vals = [v for _, v in sorted(machines.get(arch, {}).items())]
                if not vals:
                    continue
                mean = sum(vals) / len(vals)
                sd = (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** .5 if len(vals) > 1 else 0.0
                print(f"{setting}{suffix:<20} {arch:<4} {len(vals):>4} {100*mean:>6.1f}% {100*sd:>6.2f}pp {100*min(vals):.1f}–{100*max(vals):.1f}%")
            x, a = machines.get("x64", {}), machines.get("arm", {})
            common = sorted(x.keys() & a.keys())
            if common:
                diffs = [x[s] - a[s] for s in common]
                print(f"{'  x64−arm (同seed)':<32} {len(common):>4} {100*sum(diffs)/len(diffs):>+6.2f}pp seed別平均差")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
