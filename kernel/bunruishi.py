#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bunruishi.py -- 分類子システム。組み合わせを 自分で 発明する

  【なぜ】
  いまのカーネルは、私が書いた部品を、私が書いた札のとおりに組む。
  「テトリス」の札を引けば テトリスが出る。それは発明ではない。
  ここでは 札を使わず、部品の組み合わせを 交配と突然変異で作り、
  良し悪しだけを見て 残す。私が思いつかなかった組み合わせが出る。

  【良し悪しの決め方（ここが要）】
  「面白い」は測れないので、測れるものだけを見る:
      ・前提が満たせるか（要る/出す が通っているか）
      ・遊ぶ手だてがあるか（押す・動かす部品が入っているか）
      ・終わりがあるか（点／時間／勝ち）
      ・短いほどよい（だらだら足さない）
  これは「面白さ」ではない。「成り立っているか」。そこは正直に言う。

  【掛け算】
  足し引きと、選ぶだけ。
"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gameparts as G

BUHIN = list(G.PARTS)
SOUSA = {"よこうごき", "まわす", "ラケット", "こうごおき"}   # 遊ぶ手だて
OWARI = {"てんすう", "じかん", "そろえたら勝ち"}             # 終わり


def yosa(kumi):
    """組み合わせの点数。高いほど「成り立っている」"""
    if not kumi:
        return -99, "からっぽ"
    try:
        junjo = G.resolve(kumi)
    except Exception:
        return -99, "組めない"
    # 前提が本当に通っているか、自分で確かめ直す
    aru = set()
    for n in junjo:
        p = G.PARTS[n]
        for i in p["要る"]:
            if i not in aru:
                return -50, f"{n} に {i} が足りない"
        aru.update(p["出す"])

    ten, riyuu = 0, []
    if SOUSA & set(junjo):
        ten += 3; riyuu.append("遊べる")
    else:
        ten -= 2; riyuu.append("見ているだけ")
    if OWARI & set(junjo):
        ten += 2; riyuu.append("終われる")
    else:
        ten -= 1; riyuu.append("終わらない")
    ten += min(3, len(set(junjo)) - 2)          # 中身の厚み（ほどほどまで）
    ten -= max(0, len(junjo) - 6)               # 長すぎたら減点
    ten -= (len(junjo) - len(set(junjo))) * 3   # 重複は無駄
    return ten, "・".join(riyuu)


class Hinshu:
    """組み合わせの群れ。交配と突然変異で入れ替わっていく"""

    def __init__(self, kazu=40, tane=0):
        self.rnd = random.Random(tane)
        r = self.rnd
        self.mure = [r.sample(BUHIN, r.randint(1, 4)) for _ in range(kazu)]

    def _kouhai(self, a, b):
        r = self.rnd
        kiri = r.randint(0, min(len(a), len(b)))
        ko = a[:kiri] + b[kiri:]
        # 突然変異
        if r.random() < 0.3 and len(ko) < 6:
            ko.append(r.choice(BUHIN))
        if r.random() < 0.3 and len(ko) > 1:
            ko.pop(r.randrange(len(ko)))
        if r.random() < 0.2 and ko:
            ko[r.randrange(len(ko))] = r.choice(BUHIN)
        # 同じ部品は1回でよい
        mita, out = set(), []
        for x in ko:
            if x not in mita:
                mita.add(x); out.append(x)
        return out or [r.choice(BUHIN)]

    def sedai(self):
        r = self.rnd
        ten = [(yosa(k)[0], k) for k in self.mure]
        ten.sort(key=lambda x: -x[0])
        nokosu = ten[:len(ten) // 3]                 # 上位を残す
        atarashii = [k for _, k in nokosu]
        while len(atarashii) < len(self.mure):
            a = max(r.sample(ten, 3), key=lambda x: x[0])[1]
            b = max(r.sample(ten, 3), key=lambda x: x[0])[1]
            atarashii.append(self._kouhai(a, b))
        self.mure = atarashii
        return ten[0]


def hatsumei(sedai=40, tane=None):
    """札に無い、成り立つ組み合わせを ひとつ発明して返す。

    毎回ちがう答えが出るように、種を変える。
    出す前に、前提が通っていることを こちらで確かめる。
    """
    import time as _t
    tane = tane if tane is not None else int(_t.time()) % 100000
    h = Hinshu(kazu=50, tane=tane)
    for _ in range(sedai):
        h.sedai()
    shitteru = {tuple(G.resolve(v)) for v in G.NAMES.values()}
    kouho = []
    for k in h.mure:
        j = tuple(G.resolve(k))
        if j in shitteru:
            continue
        t, _r = yosa(list(k))
        if t >= 7:
            kouho.append((t, list(k)))
    if not kouho:
        return None
    kouho.sort(key=lambda x: -x[0])
    return kouho[0][1]


def tameshi(sedai=60):
    print("■ 札を使わずに、成り立つ組み合わせを 見つけられるか\n")
    h = Hinshu(kazu=60, tane=1)
    for i in range(sedai):
        best = h.sedai()
    # 出そろったものを、良い順に、重複なく
    mita, deki = set(), []
    for k in h.mure:
        j = tuple(G.resolve(k))
        if j in mita:
            continue
        mita.add(j)
        t, r = yosa(list(k))
        deki.append((t, j, r))
    deki.sort(key=lambda x: -x[0])

    shitteru = {tuple(G.resolve(v)) for v in G.NAMES.values()}
    print(f"  {sedai} 世代まわして、{len(deki)} 通りが残った\n")
    n = 0
    for t, j, r in deki[:10]:
        atarashii = j not in shitteru
        n += atarashii
        print(f"  {t:>3}点 {'★はじめて' if atarashii else '（札にある）'}"
              f"  {' → '.join(j)}")
        print(f"       {r}")
    print(f"\n  このうち {n} 通りは、私が札に書いていない組み合わせ。")


if __name__ == "__main__":
    tameshi()
