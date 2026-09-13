#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_tanomi.py -- 物差し: 頼み文の屑よけと並び。

2026-09-13 の実測（モデルの /tokenize）: 頼み文 1021トークンのうち **画面が 487（48%）**。
そこだけが毎手まるごと変わるので、llama-server の使い回しが 45% しか効いていなかった
（llama.log の f_sim 0.455）。しかも頭脳は「①」「Q」を押して 1手まるごと捨てていた。
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/Volumes/Mac Windows/LocalAI/kernel")
import sousa

KUZU = ["①", "Q", "〇", "22", "60", "_", "21:57", "9月13日（日）", "・", "3"]
NOKOSU = ["ファイル", "書類", "Documents", "カーネル試験_0913.txt", "新規メモ", "80 アーティファクト", "OK"]

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
    import inspect
    src = inspect.getsource(sousa._te_wo_kimeru)
    owari = src.rindex("p.append")
    nochi = src[owari:]
    ok2 = "画面（資料）" in nochi
    m2 += ok2
    print("  %s  頼み文の最後は【画面（資料）】" % ("○" if ok2 else "×"))
    ok3 = "rireki[-8:]" not in src
    m2 += ok3
    print("  %s  これまでの手の窓をずらさない（前半を壊さない）" % ("○" if ok3 else "×"))
    print("\n  頼み文: %d/%d" % (maru + m2, len(MONDAI) + 3))
    return 0 if (maru == len(MONDAI) and m2 == 3) else 1


if __name__ == "__main__":
    sys.exit(main())
