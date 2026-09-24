#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imi_jikken5.py -- 資料量の効きを、公平に測り直す

  imi_jikken4.py の ② には穴があった。
  資料が少ないと、そもそも語が一度も出てこない。
  出てこない組は「測れない」として 分母から外していた。
      20万字 : 6/7  （85%）   ← 11組が消えている
     334万字 : 15/18 （83%）
  分母が違うものを並べて「増えても変わらない」と言うのは誤り。

  直す: 分母は いつも18。出てこない語がある組は 負け とする。
  （実際、語を知らなければカーネルは答えられないので、負けで正しい）
"""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv
from imi_jikken4 import KUMI, mawari, vec

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "corpus_snap_A.txt")


def hakaru(text, n=2):
    goi = sorted({w for k in KUMI for w in k})
    v, kaisu = {}, {}
    for w in goi:
        m, c = mawari(text, w)
        kaisu[w] = c
        v[w] = vec(m, n)
    kachi, nashi, make = 0, 0, []
    for moto, ni, mu in KUMI:
        if v[moto] is None or v[ni] is None or v[mu] is None:
            nashi += 1                      # 語を知らない＝負け
            make.append(f"{moto}-{ni}(語なし)")
            continue
        if hdv.hamming(v[moto], v[ni]) < hdv.hamming(v[moto], v[mu]):
            kachi += 1
        else:
            make.append(f"{moto}-{ni}")
    ks = sorted(kaisu.values())
    return kachi, nashi, make, ks[len(ks) // 2]


def main():
    text = open(SNAP, encoding="utf-8").read()
    print(f"資料（凍らせた写し）: {len(text):,} 文字")
    print("=" * 66)
    print("■ 資料を増やすと 勝率は上がるか（分母はいつも18・2文字ならび）")
    print("=" * 66)
    for wari in (0.0625, 0.125, 0.25, 0.5, 1.0):
        bu = text[:int(len(text) * wari)]
        k, nashi, make, med = hakaru(bu)
        print(f"  {len(bu)//10000:>4}万字 : {k}/18 （{k*100//18:>3}%）　"
              f"語を知らない組 {nashi}　出た回数の中央値 {med}")
    print("=" * 66)


if __name__ == "__main__":
    main()
