#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imi_kurabe.py -- 資料の「種類」を変えると、意味あては良くなるか

  量を4倍にしても 83%→83% で動かなかった（§15-2）。
  効かないのは 量ではなく 種類ではないか、というのが仮説。

  同じ字数で、二つの資料を突き合わせる。
      ① でたらめな百科事典 （corpus_snap_A.txt を頭から切る）
      ② パソコンと日常の話 （corpus_snap_PC.txt）
  字数を揃えないと 比べたことにならない。少ないほうに合わせる。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv
from imi_jikken4 import KUMI, mawari, vec
from imi_jikken5 import hakaru
import imi_shiken

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "corpus_snap_A.txt")
PC = os.path.join(HERE, "corpus_snap_PC.txt")


def main():
    pc = open(PC, encoding="utf-8").read()
    ran = open(A, encoding="utf-8").read()[:len(pc)]      # 字数を揃える
    print(f"字数を {len(pc):,} 文字に揃えて比べます\n")

    print("=" * 62)
    print("■ 似た語あて（18組・分母は固定）")
    print("=" * 62)
    for namae, t in (("でたらめな百科事典", ran), ("パソコンと日常の話", pc)):
        k, nashi, make, med = hakaru(t)
        print(f"  {namae:　<12} {k}/18 （{k*100//18:>3}%）　"
              f"語を知らない組 {nashi}　出た回数の中央値 {med}")

    print("\n" + "=" * 62)
    print("■ 札に無い言い方を、正しい札へ寄せられるか")
    print("=" * 62)
    for namae, t in (("でたらめな百科事典", ran), ("パソコンと日常の話", pc)):
        v, atari, kesu = {}, 0, []
        goi = sorted({w for a, b in imi_shiken.SHIKEN for w in [a] + b})
        for w in goi:
            m, n = mawari(t, w)
            v[w] = vec(m, 2)
        for moto, kouho in imi_shiken.SHIKEN:
            if v[moto] is None:
                kesu.append(moto); continue
            ten = sorted((hdv.hamming(v[moto], v[k]) / hdv.DIM, k)
                         for k in kouho if v[k] is not None)
            if ten and ten[0][1] == kouho[0]:
                atari += 1
            else:
                kesu.append(f"{moto}→{ten[0][1] if ten else '?'}")
        print(f"  {namae:　<12} 1位が当たった {atari}/{len(imi_shiken.SHIKEN)}"
              f"　外し: {' '.join(kesu) or 'なし'}")
    print("=" * 62)


if __name__ == "__main__":
    main()
