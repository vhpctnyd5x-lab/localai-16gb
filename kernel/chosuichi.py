#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chosuichi.py -- セルオートマトンの貯水池（Reservoir / ReCA）

  【ねらい】
  「時間の流れ」を、学習なしで ほどく道具。
  中身は、一列に並んだマスが XOR で書き変わっていくだけ。
  学ぶのは、出口の一段だけ（ここはツェットリン機械にやらせる）。

  【なぜ効くのか】
      入れたもの → 規則90 で何段も広げる
      →  最初のわずかな違いが、段が進むほど大きく開く
      →  もともと混ざっていたものが、離れて置き直される
  ばらばらにするのは ただの XOR。掛け算はしない。

  【カーネルでの使いどころ】
      音の並び、押した順、字の並び ── 順番が意味を持つもの。
      いまのカーネルは「順番」をほとんど見ていない。
"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def kisoku90(s, n):
    """規則90: 自分は消え、左右の XOR になる"""
    hidari = ((s << 1) | (s >> (n - 1))) & ((1 << n) - 1)   # 輪にする
    migi = (s >> 1) | ((s & 1) << (n - 1))
    return hidari ^ migi


def kisoku150(s, n):
    """規則150: 左 XOR 自分 XOR 右。90 より混ざり方が濃い"""
    hidari = ((s << 1) | (s >> (n - 1))) & ((1 << n) - 1)
    migi = (s >> 1) | ((s & 1) << (n - 1))
    return hidari ^ s ^ migi


class Chosuichi:
    def __init__(self, haba=64, dan=8, kisoku=kisoku90):
        self.haba, self.dan, self.kisoku = haba, dan, kisoku

    def hirogeru(self, tane):
        """一つの入れものを、段ごとに広げて つなげた ビット列にする"""
        n, s = self.haba, tane & ((1 << self.haba) - 1)
        out, sh = 0, 0
        for _ in range(self.dan):
            s = self.kisoku(s, n)
            out |= s << sh
            sh += n
        return out

    @property
    def hirosa(self):
        return self.haba * self.dan

    def nagare(self, tsubu):
        """順番に来るものを、混ぜながら流し込む（前の状態を持ち越す）"""
        n = self.haba
        s = 0
        ato = 0
        for t in tsubu:
            s ^= (t & ((1 << n) - 1))       # 新しい入力を混ぜる
            for _ in range(self.dan):
                s = self.kisoku(s, n)
                ato ^= s                     # 通った跡を残す
        return ato


def tameshi():
    import tsetlin
    print("■ ばらばらにする道具として役に立つか\n")
    rnd = random.Random(0)

    # 課題: 7ビットの偶奇（ぜんぶの XOR）。
    # 「かつ／でない」の式ひとつでは絶対に書けない、いちばん意地悪な問題
    N = 7
    D = [(b, bin(b).count("1") % 2) for b in range(1 << N)]
    rnd.shuffle(D)
    tr, te = D[:100], D[100:]

    def hakaru(x_of, hirosa, namae):
        m = tsetlin.Kikai(hirosa, kata=60, T=12, s=4.0)
        for _ in range(60):
            rnd.shuffle(tr)
            for b, y in tr:
                m.manabu(x_of(b), y)
        ok = sum(1 for b, y in te if m.kotae(x_of(b)) == y)
        print(f"  {namae}: {ok}/{len(te)}  ({ok/len(te):.0%})")

    hakaru(lambda b: b, N, "そのまま          ")
    c = Chosuichi(haba=N, dan=6, kisoku=kisoku150)
    hakaru(c.hirogeru, c.hirosa, f"貯水池を通す（{c.hirosa}ビットに広がる）")

    print("\n  ── 順番を見分けられるか（同じ材料・並びだけ違う）──")
    c2 = Chosuichi(haba=32, dan=4)
    a = c2.nagare([1, 2, 4])
    b = c2.nagare([4, 2, 1])
    d = c2.nagare([1, 2, 4])
    print(f"    [1,2,4] と [4,2,1] : 違うビット {bin(a ^ b).count('1')} 個")
    print(f"    [1,2,4] と [1,2,4] : 違うビット {bin(a ^ d).count('1')} 個"
          "  ← 同じ並びなら ぴったり同じ")


if __name__ == "__main__":
    tameshi()
