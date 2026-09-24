#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sdm.py -- まばらな記憶（Sparse Distributed Memory / Kanerva 1988）

  1万ビットの相棒。ノートとの違いは、ここ:

      ノート : 書いた所しか読めない。書いていなければ「無い」
      これ   : 書いていない所を読むと、近所に書いたものが混ざって出る

  つまり「思い出せないことを思い出す」。想像の芽。

  【仕組み】
  でたらめな住所を 千ヶ所ほど用意しておく（ここに実体がある）。
      書く: 頼まれた住所の「近所」の所ぜんぶに、
            ビットが 1 なら +1、0 なら -1 を足す
      読む: 近所ぜんぶの足し算を合計し、0 より上なら 1

  近所に何度も同じものを書けば、その形が濃くなる。
  近い住所を読めば、その濃い形が出てくる。
  掛け算はしない。足し引きと、ビットを数えるだけ。
"""
import os, random, sys
from array import array
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv

DIM = hdv.DIM


class Sdm:
    def __init__(self, tokoro=1000, hanni=None, tane=0):
        """tokoro: 場所の数 / hanni: 「近所」とみなすハミング距離"""
        rnd = random.Random(tane)
        self.tokoro = tokoro
        # でたらめな住所（1万ビットの整数）
        self.addr = [rnd.getrandbits(DIM) for _ in range(tokoro)]
        # 近所の広さ。ここは一度まちがえた。
        # でたらめな 1万ビット どうしの距離は 5000±50 に固まっている。
        # 4700 にしたら、どの場所も近所にならず 0 ヶ所になった。
        # 5000 から「ばらつき2つぶん」引いたあたりが、ちょうどよい
        #（全体の 2% ほどが近所になる）
        import math
        self.hanni = (hanni if hanni is not None
                      else DIM // 2 - int(2.0 * math.sqrt(DIM) / 2))
        self.kaz = [None] * tokoro       # 使うときに作る（省メモリ）
        self.tsukatta = 0

    def _chikaku(self, a):
        h, out = self.hanni, []
        for i, ad in enumerate(self.addr):
            if bin(ad ^ a).count("1") <= h:
                out.append(i)
        return out

    def kaku(self, addr, data):
        """住所 addr のあたりに data を書く"""
        ni = self._chikaku(addr)
        for i in ni:
            c = self.kaz[i]
            if c is None:
                c = self.kaz[i] = array("h", bytes(2 * DIM))
                self.tsukatta += 1
            d = data
            for b in range(DIM):
                if (d >> b) & 1:
                    if c[b] < 32000: c[b] += 1
                else:
                    if c[b] > -32000: c[b] -= 1
        return len(ni)

    def yomu(self, addr):
        """住所 addr のあたりを読む。書いていなくても、近所が混ざって出る"""
        ni = [i for i in self._chikaku(addr) if self.kaz[i] is not None]
        if not ni:
            return None, 0
        wa = array("l", bytes(8 * DIM))
        for i in ni:
            c = self.kaz[i]
            for b in range(DIM):
                wa[b] += c[b]
        out = 0
        for b in range(DIM):
            if wa[b] > 0:
                out |= 1 << b
        return out, len(ni)


def tameshi():
    print("■ まばらな記憶: 書いていない所を読めるか\n")
    s = Sdm(tokoro=400)

    kao = {w: hdv.atom("かたち:" + w) for w in ["ねこ", "いぬ", "とり"]}
    for w, v in kao.items():
        n = s.kaku(hdv.atom("なまえ:" + w), v)
        print(f"  「{w}」を {n} ヶ所に書いた")

    print("\n  ちゃんと読めるか（書いた住所）")
    for w, v in kao.items():
        got, n = s.yomu(hdv.atom("なまえ:" + w))
        print(f"    {w} → もとの形との近さ {hdv.near(got, v):.3f}"
              f"（{n} ヶ所ぶん）")

    print("\n  ── 住所を わざと汚して読む（言い間違い・打ち間違いのつもり）──")
    import random as R
    rnd = R.Random(1)
    for w in ["ねこ", "いぬ"]:
        a = hdv.atom("なまえ:" + w)
        for kizu in (500, 1500, 3000):
            b = a
            for _ in range(kizu):
                b ^= 1 << rnd.randrange(DIM)
            got, n = s.yomu(b)
            if got is None:
                print(f"    {w} を {kizu} ビット汚す → 何も出ない")
                continue
            best = max(kao, key=lambda k: hdv.near(got, kao[k]))
            print(f"    {w} を {kizu} ビット汚す → 出たのは「{best}」"
                  f"（近さ {hdv.near(got, kao[best]):.3f}）")


if __name__ == "__main__":
    tameshi()
