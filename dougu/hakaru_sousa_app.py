#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_sousa_app.py -- 操作の課題を、動いているアプリに頼んで測る。

確かめは **ファイルが在るか**（画面を通さない）。輪の自己申告は数えない。
承認は「する」で自動で返す。**無人の試験専用。**
"""
from __future__ import annotations
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsukau_app

DESK = os.path.expanduser("~/Desktop")
DOCS = os.path.expanduser("~/Documents")
FUDA = "カーネル試験_0913.txt"


def junbi():
    with open(os.path.join(DESK, FUDA), "w", encoding="utf-8") as f:
        f.write("これは操作の輪の試験に使う紙です。消してかまいません。\n")
    q = os.path.join(DOCS, FUDA)
    if os.path.exists(q):
        os.remove(q)


def main():
    junbi()
    tanomi = f"Finderで デスクトップの {FUDA} を 書類フォルダ に移して"
    print("── Finder: デスクトップの紙を 書類へ 移す")
    print("   頼み: %s" % tanomi)
    t0 = time.time()
    r = tsukau_app.tanomu(tanomi)
    byou = time.time() - t0
    ok = os.path.exists(os.path.join(DOCS, FUDA)) and not os.path.exists(os.path.join(DESK, FUDA))
    print("\n   返事: %s" % str(r.get("出力", ""))[:200])
    print("   %s  %.0f秒 ／ 機械の確かめ: 書類に在る=%s ・ デスクトップから消えた=%s"
          % ("○" if ok else "×", byou,
             os.path.exists(os.path.join(DOCS, FUDA)),
             not os.path.exists(os.path.join(DESK, FUDA))))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
