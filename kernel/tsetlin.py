#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tsetlin.py -- ツェットリン機械。ニューラルネットでもカーネルでもない第三の道

  【何が違うか】
  ニューラルネット: 重み（小数）を、微分で少しずつ動かす。中身は読めない。
  ツェットリン機械: 「かつ／でない」の式を、○×の投票で組み立てる。
                    小数を使わない。足し引きだけ。中身がそのまま読める。

  【仕組み】
  条件（例:「"画"という字が入っている」）ごとに 賭け札 を1枚持つ。
      札の目盛りが真ん中より上 → その条件を式に入れる
      当たったら +1、外したら -1。それだけ。
  式（かたまり）を何本も持ち、賛成の式と反対の式で多数決する。

      かたまり3 = 「音」が入っている かつ 「像」が入っていない  → 音楽に賛成

  【カーネルとの関係】
  カーネルが「みそ汁は書類です」と間違えたとき、
  ニューラルネットなら理由が出せない。これは式が出るので、
  どの条件で間違えたかが読めて、直せる。
"""
import json, math, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))



#   【速さの話】
#   素直に書くと、式1本ごとに条件を全部見るので遅い（実測: 終わらない）。
#   条件の入り／切りを ひとつの整数のビット として持てば、
#   式の判定が「and 2回」で済む。1万ビットの道具と同じ手。
#       入れている条件が、すべて立っているか  →  (いれた & ~x) == 0

class Kikai:
    """ひとつの「はい／いいえ」を決める機械"""

    def __init__(self, tokushu, kata=100, T=15, s=3.9, nokori=100, tane=0):
        """tokushu: 条件の数 / kata: 式の本数（半分は賛成、半分は反対）
        T: 何票集まれば満足するか / s: 式の細かさ（大きいほど条件を多く付ける）
        nokori: 賭け札の目盛りの数"""
        self.n, self.kata, self.T, self.s = tokushu, kata, T, s
        self.N = nokori
        self.rnd = random.Random(tane)
        r = self.rnd.random
        self.ta = [[self.N - 1 if r() < 0.5 else self.N
                    for _ in range(2 * tokushu)] for _ in range(kata)]
        # 入れている条件を、ビットで持っておく（速さのため）
        self.ari = [0] * kata     # 「その条件が 1」を入れている
        self.nai = [0] * kata     # 「その条件が 0」を入れている
        for j in range(kata):
            a = b = 0
            for i in range(tokushu):
                if self.ta[j][i] >= self.N:
                    a |= 1 << i
                if self.ta[j][tokushu + i] >= self.N:
                    b |= 1 << i
            self.ari[j], self.nai[j] = a, b

    def _ugoku(self, j, k, d):
        """賭け札を d だけ動かす。真ん中をまたいだらビットも直す"""
        ta = self.ta[j]
        v = ta[k] + d
        if v < 0 or v > 2 * self.N - 1:
            return
        mae, ta[k] = ta[k] >= self.N, v
        ima = v >= self.N
        if mae != ima:
            n = self.n
            if k < n:
                self.ari[j] = (self.ari[j] | (1 << k)) if ima else (self.ari[j] & ~(1 << k))
            else:
                i = k - n
                self.nai[j] = (self.nai[j] | (1 << i)) if ima else (self.nai[j] & ~(1 << i))

    def _kata_hyoka(self, j, xb, manabi):
        a, b = self.ari[j], self.nai[j]
        if a == 0 and b == 0:
            return 1 if manabi else 0      # 空の式は、学び始めの種
        if (a & ~xb) or (b & xb):
            return 0
        return 1

    def wa(self, xb, manabi=False):
        s = 0
        for j in range(self.kata):
            v = self._kata_hyoka(j, xb, manabi)
            if v:
                s += 1 if j % 2 == 0 else -1
        return s

    def kotae(self, xb):
        return 1 if self.wa(xb) >= 0 else 0

    # ---- 学ぶ ------------------------------------------------------
    def manabu(self, xb, y):
        T, s, N, n = self.T, self.s, self.N, self.n
        v = max(-T, min(T, self.wa(xb, manabi=True)))
        p = (T - v) / (2 * T) if y else (T + v) / (2 * T)
        if p <= 0:
            return
        r = self.rnd.random
        wasureru = 1.0 / s
        for j in range(self.kata):
            if r() > p:
                continue
            sansei = (j % 2 == 0)
            out = self._kata_hyoka(j, xb, True)
            if (y == 1) == sansei:
                if out:
                    # あたり: 成り立っている側を強め、反対側をすこし忘れる
                    for i in range(n):
                        tatte = (xb >> i) & 1
                        k = i if tatte else n + i
                        if r() > wasureru:
                            self._ugoku(j, k, +1)
                        if r() <= wasureru:
                            self._ugoku(j, n + i if tatte else i, -1)
                else:
                    for k in range(2 * n):
                        if r() <= wasureru:
                            self._ugoku(j, k, -1)
            elif out:
                # 反対側を削る: 効く条件を足させて、成り立たなくする
                for i in range(n):
                    k = n + i if ((xb >> i) & 1) else i
                    if self.ta[j][k] < N:
                        self._ugoku(j, k, +1)

    # ---- 中身を読む ------------------------------------------------
    def shiki(self, namae, kagiri=6):
        """学んだ式を、人が読める形で返す"""
        out = []
        for j in range(self.kata):
            jo = [namae[i] for i in range(self.n) if (self.ari[j] >> i) & 1]
            jo += ["not " + namae[i] for i in range(self.n) if (self.nai[j] >> i) & 1]
            if jo:
                out.append((("賛成" if j % 2 == 0 else "反対"), jo))
        out.sort(key=lambda x: len(x[1]))
        return out[:kagiri]


class Wakeru:
    """いくつもの答えから選ぶ（答えの数だけ機械を持つ）"""

    def __init__(self, tokushu, kumi, **kw):
        self.kumi = list(kumi)
        self.ki = {k: Kikai(tokushu, tane=i, **kw) for i, k in enumerate(self.kumi)}

    def manabu(self, xb, y):
        for k, m in self.ki.items():
            m.manabu(xb, 1 if k == y else 0)

    def kotae(self, xb, shikii=None):
        sc = {k: m.wa(xb) for k, m in self.ki.items()}
        best = max(sc, key=sc.get)
        if shikii is not None and sc[best] < shikii:
            return None, sc
        return best, sc
