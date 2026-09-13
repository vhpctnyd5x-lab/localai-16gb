#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_ikisaki.py -- 物差し: 「どこへ移すか」を読み違えないか。

2026-09-14 の実測: 「書類フォルダに移して」の 書類 が「書類ファイル（種類）」と読まれ、
行き先が消え、代わりに **動かす相手のファイル名** が行き先に回っていた。
その結果「そのファイル名のフォルダ」を作ってそこへ入れようとして止まっていた。
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/Volumes/Mac Windows/LocalAI/kernel")
import kernel

MONDAI = [
    ("書類フォルダ → 書類",        "デスクトップの メモ.txt を 書類フォルダ に移して", "書類"),
    ("書類 → 書類",                "デスクトップの メモ.txt を 書類 に移して",         "書類"),
    ("ダウンロードフォルダ",        "デスクトップの a.txt を ダウンロードフォルダ に移して", "ダウンロード"),
    ("デスクトップ",                "書類の a.txt を デスクトップ に移して",            "デスクトップ"),
    ("★形式の名前は行き先にしない", "写真をPDFにまとめて",                              None),
    ("★「フォルダ」だけは行き先でない", "これをフォルダに移して",                        None),
]


def main():
    maru = 0
    for midashi, bun, machi in MONDAI:
        tgt, dest = kernel._move_pair(bun)
        ok = (dest == machi)
        maru += ok
        print("  %s  %s（行き先 %r ／ 期待 %r）" % ("○" if ok else "×", midashi, dest, machi))
    print("\n  行き先の読み方: %d/%d" % (maru, len(MONDAI)))
    return 0 if maru == len(MONDAI) else 1


if __name__ == "__main__":
    sys.exit(main())
