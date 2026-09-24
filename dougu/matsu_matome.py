#!/usr/bin/env python3
"""matsu.sh actions の終わりの要約: kekka 枝の md から 主な数だけを 1行ずつ（9/24）。標準入力 = md のパス。"""
import re, subprocess, sys

def hitotsu(pat, text):
    m = re.search(pat, text)
    return m.group(1) if m else None

for f in sys.stdin.read().split():
    t = subprocess.run(["git", "show", "origin/kekka:" + f], capture_output=True, text=True).stdout
    jikken = t.split("## 速さ")[-1]            # 基準（同じ機械）の表より後ろ = 実験の速さ
    kazu = [("正解率", hitotsu(r'"正解率"\s*:\s*"?([^",\n]+)', t)), ("平均秒", hitotsu(r'"平均秒"\s*:\s*"?([\d.]+)', t)),
            ("GiB", hitotsu(r"\|\s*([\d.]+) GiB", jikken)), ("PPL", hitotsu(r"PPL = ([\d.]+)", t)),
            ("tg", hitotsu(r"tg128 \|\s*([\d.]+)", jikken)), ("基準比tg", hitotsu(r"基準比 tg128: ([\d.]+)", t)),
            ("失敗", hitotsu(r"失敗: (exit=\d+ 行=\d+)", t))]
    print(f.split("/")[-1][:-3] + ": " + (" ".join(f"{k} {v}" for k, v in kazu if v) or "指標なし"))
