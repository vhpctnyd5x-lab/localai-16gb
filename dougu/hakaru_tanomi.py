#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_tanomi.py -- 物差し: 頼み文の屑よけと並び。

2026-09-13 の実測（モデルの /tokenize）: 頼み文 1021トークンのうち **画面が 487（48%）**。
そこだけが毎手まるごと変わるので、llama-server の使い回しが 45% しか効いていなかった
（llama.log の f_sim 0.455）。しかも頭脳は「①」「Q」を押して 1手まるごと捨てていた。
"""
from __future__ import annotations
import sys
import os, sys
# ★ 2026-09-16: 正は内蔵の写し（外部SSDは日に何度も切れる）。無ければ SSD を見る
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel")
                                                if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import sousa

KUZU = ["①", "Q", "〇", "_", "21:57", "9月13日（日）", "・", "3", "1234567890123"]
# ★ 2026-09-16: 2〜12桁の数字は残す（計算機の答え 408 が頭脳にも機械の確かめにも見えなかった）
NOKOSU = ["ファイル", "書類", "Documents", "カーネル試験_0913.txt", "新規メモ", "80 アーティファクト", "OK", "22", "408"]

MONDAI = [("屑を落とす: %r" % k, k, False) for k in KUZU] + \
         [("残す: %r" % n, n, True) for n in NOKOSU]


def main():
    maru = 0
    for midashi, moji, machi in MONDAI:
        deta = sousa._yakunitatsu(moji)
        ok = deta == machi
        maru += ok
        if not ok:
            print("  ×  %s（%s／期待 %s）" % (midashi, deta, machi))
    print("  屑よけ: %d/%d" % (maru, len(MONDAI)))

    # 並び: 変わる所（画面）が いちばん後ろか。締めの1行は SYSTEM へ移した
    m2 = 0
    m2 += "次の1手を JSON で" in sousa.SYSTEM
    print("  %s  締めの1行は SYSTEM にある（毎回同じ文は前半へ）" % ("○" if m2 else "×"))
    import inspect, tempfile, teachers
    src = inspect.getsource(sousa._te_wo_kimeru)
    # ★ 2026-09-16: 並びは NARABI で切り替わるので、文面ではなく 実際に組んだ頼み文で見る
    tsukanda = {}
    moto, sousa._KIROKU = sousa._KIROKU, tempfile.mkdtemp()
    teachers.ask_one, moto_ask = (lambda *a, **k: (tsukanda.__setitem__("p", a[1]), {"text": '{"手":"待つ"}'})[1]), teachers.ask_one
    try:
        g = {"アプリ": "Notes", "文字": [{"文": "新規メモ", "x": 1, "y": 1}], "枠": None, "目当て": "Notes", "窓の題": "メモ"}
        sousa._te_wo_kimeru("メモを開いて", ["アプリ「Notes」を前に出す"], g, 5)
    finally:
        teachers.ask_one, sousa._KIROKU = moto_ask, moto
    t = tsukanda.get("p", "")
    # ★ 2026-09-16 から既定は「画面が先」: 変わる所（新しい行・窓の題・履歴）が全部 画面の文字より後ろにある
    ok2 = (sousa.NARABI == "画面が先" and t.find("見えている文字") < t.find("いま前にある窓の題") < t.find("これまでの手"))
    m2 += ok2
    print("  %s  変わる所（窓の題・履歴）は画面の文字より後ろ（既定の並び 画面が先）" % ("○" if ok2 else "×"))
    # 初めて見えた順: 前の並びを渡すと、残っている行は同じ並びのまま、新しい行が後ろに付く
    g2 = {"アプリ": "Notes", "枠": None, "目当て": "Notes", "窓の題": "メモ",
          "文字": [{"文": x, "x": 1, "y": i} for i, x in enumerate(["新しい行", "ファイル", "編集", "新規メモ"])]}
    f, a = sousa._moji_narabi(g2, ["編集", "新規メモ", "消えた行", "ファイル"])
    ok4 = f == ["編集", "新規メモ", "ファイル"] and a == ["新しい行"]
    m2 += ok4
    print("  %s  画面の文字は初めて見えた順（前の並びを保ち、新しい行は後ろ）" % ("○" if ok4 else "×"))
    ok3 = "rireki[-8:]" not in src
    m2 += ok3
    print("  %s  これまでの手の窓をずらさない（前半を壊さない）" % ("○" if ok3 else "×"))
    print("\n  頼み文: %d/%d" % (maru + m2, len(MONDAI) + 4))
    return 0 if (maru == len(MONDAI) and m2 == 3) else 1


if __name__ == "__main__":
    sys.exit(main())
