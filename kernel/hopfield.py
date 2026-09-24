#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hopfield.py -- 考えが だんだん落ち着く（連想記憶・引き込み）

  【なぜ入れるか】
  いまのカーネルは、答えが「出る／出ない」の二択で、
  途中の「考えている最中」が無い。
  これは、崩れた形を入れると、揺れながら覚えた形へ寄っていく。
  何回ゆれたかが、そのまま「どれくらい難しかったか」になる。
  ＝じっくり考えている、が本当に目に見える。

  【仕組み】
  覚えるとき: 一緒に立っているビット同士の絆を +1、
              食い違うビット同士を -1
  思い出すとき: 一つずつ「まわりの多数決」で自分を決め直す。
                動かなくなったら、そこが答え（谷に落ちた）

  掛け算はしない。±1 を足し引きするだけ。

  【限界（正直に）】
  覚えられる数は、ビット数の 15% ほど。それを超えると、
  覚えていない偽の谷ができて、変なものを思い出す。
  これは仕組み上どうにもならない。実測もする。
"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Hopfield:
    def __init__(self, n):
        self.n = n
        self.w = [[0] * n for _ in range(n)]

    def oboeru(self, bits):
        """bits: 0/1 の並び"""
        s = [1 if b else -1 for b in bits]
        w, n = self.w, self.n
        for i in range(n):
            si = s[i]
            wi = w[i]
            for j in range(i + 1, n):
                d = si * s[j]           # ±1 同士。実際は足すか引くか だけ
                wi[j] += d
                w[j][i] += d
        return self

    def omoidasu(self, bits, kagiri=50, tane=0):
        """崩れた形から、覚えた形へ寄せる。(答え, ゆれた回数)"""
        s = [1 if b else -1 for b in bits]
        rnd = random.Random(tane)
        n, w = self.n, self.w
        yure = 0
        for _ in range(kagiri):
            junban = list(range(n))
            rnd.shuffle(junban)
            ugoita = False
            for i in junban:
                wi = w[i]
                a = 0
                for j in range(n):
                    if j != i:
                        a += wi[j] if s[j] > 0 else -wi[j]
                atarashii = 1 if a >= 0 else -1
                if atarashii != s[i]:
                    s[i] = atarashii
                    ugoita = True
            yure += 1
            if not ugoita:
                break
        return [1 if x > 0 else 0 for x in s], yure


def tameshi():
    print("■ 崩れた形から、覚えた形へ 落ち着けるか\n")
    rnd = random.Random(0)
    N = 200
    for kazu in (5, 15, 30, 45):
        h = Hopfield(N)
        kata = [[rnd.randint(0, 1) for _ in range(N)] for _ in range(kazu)]
        for k in kata:
            h.oboeru(k)
        ok, yure_wa = 0, 0
        for k in kata[:10]:
            kuzu = [b ^ (1 if rnd.random() < 0.2 else 0) for b in k]  # 2割こわす
            got, yure = h.omoidasu(kuzu)
            au = sum(1 for a, b in zip(got, k) if a == b) / N
            ok += (au > 0.95)
            yure_wa += yure
        n = min(10, kazu)
        print(f"  {kazu:2d} 個 覚えさせる（ビットの {kazu/N:.0%}）"
              f"  → {ok}/{n} 正しく戻った"
              f"   ゆれ 平均 {yure_wa/n:.1f} 回")
    print("\n  ビット数の 15%（30個）を超えると崩れる。理屈どおり。")


if __name__ == "__main__":
    tameshi()
