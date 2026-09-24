#!/usr/bin/env python3
"""問ごとの結果から Wilson 区間・McNemar 検定・対応 bootstrap を出す。"""
from __future__ import annotations

import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

BOOTSTRAPS = 10_000
Z95 = 1.959963984540054


def read_source(name: str) -> tuple[str, str]:
    """Return file contents and a human readable source label, including origin/kekka."""
    path = Path(name)
    if path.is_file():
        return path.read_text(encoding="utf-8"), str(path)
    repo_path = name.removeprefix("origin/kekka:")
    if repo_path.startswith("kekka/"):
        candidates = [repo_path]
    else:
        candidates = ["kekka/" + repo_path]
    for candidate in candidates:
        proc = subprocess.run(["git", "show", "origin/kekka:" + candidate],
                              text=True, encoding="utf-8", capture_output=True)
        if proc.returncode == 0:
            return proc.stdout, "origin/kekka:" + candidate
    raise ValueError(f"ファイルがない: {name} (kekka/ 枝のパスも指定できます)")


def records_from(text: str, source: str) -> dict[str, bool]:
    objects = []
    if source.endswith(".jsonl") or ".jsonl" in source:
        for line_no, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{line_no}: JSONL を読めない: {exc}") from exc
            if isinstance(obj, dict) and "id" in obj and "○" in obj:
                objects.append(obj)
    elif source.endswith(".md"):
        # Actions の markdown 名札から、kekka/ 枝に積まれた問別 JSONL を引く。
        match = re.search(r"(?:^|/)actions-(.+?)\.md$", source)
        if match:
            candidate = "kekka/7dan_" + match.group(1) + ".tochuu.jsonl"
            try:
                content, label = read_source(candidate)
                return records_from(content, label)
            except ValueError:
                pass
        # `7dan_*.md` や JSONL 名を記載した markdown にも対応する。
        stem = Path(source).name
        candidate_names = []
        if stem.startswith("7dan_"):
            candidate_names.append("kekka/" + stem[:-3] + ".tochuu.jsonl")
        for raw in re.findall(r"(?:kekka/)?[^\s`()]+\.tochuu\.jsonl", text):
            candidate_names.append(raw if raw.startswith("kekka/") else "kekka/" + raw)
        for candidate in candidate_names:
            try:
                content, label = read_source(candidate)
                return records_from(content, label)
            except ValueError:
                continue
        raise ValueError(f"{source}: 対応する問別 .tochuu.jsonl が見つからない")
    else:
        try:
            root = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}: JSON を読めない: {exc}") from exc

        def walk(value):
            if isinstance(value, dict):
                if "id" in value and "○" in value:
                    objects.append(value)
                else:
                    for child in value.values():
                        walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(root)

    result = {}
    for row in objects:
        key = str(row["id"])
        if key in result:
            raise ValueError(f"{source}: 問題 id が重複: {key}")
        result[key] = bool(row["○"])
    if not result:
        raise ValueError(f"{source}: id と ○ を持つ問別記録が見つからない")
    return result


def wilson(correct: int, n: int) -> tuple[float, float]:
    p = correct / n
    den = 1 + Z95 * Z95 / n
    center = (p + Z95 * Z95 / (2 * n)) / den
    radius = Z95 * math.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n)) / den
    return center - radius, center + radius


def exact_mcnemar(a_only: int, b_only: int) -> float:
    discordant = a_only + b_only
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, k) for k in range(min(a_only, b_only) + 1)) / (2 ** discordant)
    return min(1.0, 2 * tail)


def bootstrap_ci(deltas: list[float]) -> tuple[float, float]:
    rng = random.Random(240925)
    n = len(deltas)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(BOOTSTRAPS))
    return means[int(0.025 * BOOTSTRAPS)], means[int(0.975 * BOOTSTRAPS) - 1]


def pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def analyze(label: str, rows: dict[str, bool]) -> tuple[int, int, float, float]:
    n = len(rows)
    correct = sum(rows.values())
    lo, hi = wilson(correct, n)
    print(f"{label:<18} {correct:>4}/{n:<4} {pct(correct / n):>7}   [{pct(lo)}, {pct(hi)}]")
    return correct, n, lo, hi


def main() -> int:
    if len(sys.argv) != 3:
        print("使い方: python3 dougu/kurabe.py <A> <B>", file=sys.stderr)
        return 2
    try:
        a_text, a_name = read_source(sys.argv[1])
        b_text, b_name = read_source(sys.argv[2])
        a = records_from(a_text, a_name)
        b = records_from(b_text, b_name)
        if a.keys() != b.keys():
            missing_a, missing_b = len(b.keys() - a.keys()), len(a.keys() - b.keys())
            raise ValueError(f"比較できない問題集合: Aのみ {missing_b}問、Bのみ {missing_a}問")
        ids = sorted(a)
        a_only = sum(a[i] and not b[i] for i in ids)
        b_only = sum(b[i] and not a[i] for i in ids)
        deltas = [int(b[i]) - int(a[i]) for i in ids]
        ci_lo, ci_hi = bootstrap_ci(deltas)
        p_value = exact_mcnemar(a_only, b_only)
        print("設定                 正解       正解率   Wilson 95% 区間")
        analyze("A " + Path(a_name).name, a)
        analyze("B " + Path(b_name).name, b)
        print(f"対応差 B−A       {b_only - a_only:+d}/{len(ids)}   {pct(sum(deltas) / len(ids))}   bootstrap 95% [{pct(ci_lo)}, {pct(ci_hi)}]")
        print(f"不一致 A○B×/A×B○ {a_only}/{b_only}   McNemar exact p={p_value:.4g} → "
              f"{'差があるとは言えない' if p_value >= .05 else '差を示す証拠あり'}")
        print("bootstrap は問題の復元抽出 10,000 回。")
    except (OSError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
