#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imi_shiken.py -- 意味ベクトルを 札引き に繋いだら、残りの失敗は直るか

  言い換え25問で いま外している2つ:
      「デスクトップの資料は何個」  資料 → 書類 に寄せたい
      「いちばん重いファイル」      重い → 大きい に寄せたい
  どちらも「札に無い言い方」。資料から作った意味ベクトルで
  いちばん近い札に寄せられるか、繋ぐ前に ここで確かめる。

  合格の線: 正しい札が 1位 に来ること。2位以下なら繋いでも効かない。
"""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv
from imi_jikken4 import mawari, vec

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "corpus_snap_A.txt")

SHIKEN = [
    ("資料", ["書類", "画像", "音楽", "動画", "文字"]),
    ("重い", ["大きい", "小さい", "古い", "新しい"]),
    ("絵",   ["画像", "音楽", "動画", "書類"]),
    ("動画", ["映像", "画像", "音楽", "書類"]),
    ("軽い", ["小さい", "大きい", "古い", "新しい"]),
    ("最近", ["新しい", "古い", "大きい", "小さい"]),
]


def main():
    text = open(SNAP, encoding="utf-8").read()
    print(f"資料: {len(text):,} 文字\n")
    goi = sorted({w for a, b in SHIKEN for w in [a] + b})
    v = {}
    for w in goi:
        m, n = mawari(text, w)
        v[w] = vec(m, 2)
        if v[w] is None:
            print(f"  ※ {w} は資料に出てこない")
    print()
    atari = 0
    for moto, kouho in SHIKEN:
        if v[moto] is None:
            print(f"  {moto}: 測れない"); continue
        ten = []
        for k in kouho:
            if v[k] is None:
                continue
            ten.append((hdv.hamming(v[moto], v[k]) / hdv.DIM, k))
        ten.sort()
        ichii = ten[0][1] if ten else None
        seikai = kouho[0]
        ok = ichii == seikai
        atari += ok
        nami = "  ".join(f"{k}{d:.3f}" for d, k in ten)
        print(f"  {'○' if ok else '×'} {moto:　<4}→ {nami}")
    print(f"\n  1位が当たった: {atari}/{len(SHIKEN)}")
    print("  → 繋ぐ価値あり" if atari >= 4 else "  → まだ繋げない")


if __name__ == "__main__":
    main()
