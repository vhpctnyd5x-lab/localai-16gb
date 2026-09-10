#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kenzan3.py -- 6段の物差しを **問題文を読み直して** 検算する。

★ 作った式で検算しても同じ間違いをする。**別の道筋**で答えを出して突き合わせる。
  ここでは 生成側が整数の // を使う所を、こちらは 分数(Fraction)で解き、
  「割り切れていない」問題そのものも あぶり出す。
"""
import json, io, re, sys, os
from fractions import Fraction as F
from collections import Counter


class Dame(str):
    """問題として成り立っていないことを表す（語の答えと区別するため str の子）"""


HERE = os.path.dirname(os.path.abspath(__file__))


def _seisu(v, doko):
    if v.denominator != 1:
        return Dame("%s が 割り切れていない (%s)" % (doko, v))
    return int(v)


def kenzan(x):
    t, k = x["問"], x["型"]

    if k == "ざいこ6段":
        s0, hako, ko = map(int, re.search(
            r"が (\d+)\S+ あります。そこへ (\d+)箱ぶん（1箱 (\d+)", t).groups())
        p = int(re.search(r"ぜんぶの (\d+)% を 出荷", t).group(1))
        henpin = int(re.search(r"中から (\d+)\S+ が こわれていて", t).group(1))
        tanka = int(re.search(r"(\d+)円で ぜんぶ売り", t).group(1))
        q = int(re.search(r"金額の (\d+)% を 手数料", t).group(1))
        s1 = F(s0 + hako * ko)
        nokori = s1 * (100 - p) / 100          # 出荷後（引き算ではなく残る割合で）
        v = _seisu(nokori, "出荷後の残り")
        if isinstance(v, Dame):
            return v
        uri = F((v + henpin) * tanka)
        te = uri * (100 - q) / 100
        return _seisu(te, "手数料を引いた額")

    if k == "ダイヤ6段":
        h, m = map(int, re.search(r"を (\d+)時(\d+)分に 出る", t).groups())
        d1, v1 = map(int, re.search(r"までは (\d+)km を 時速(\d+)km", t).groups())
        machi = int(re.search(r"で (\d+)分 待って", t).group(1))
        d2, v2 = map(int, re.findall(r"(\d+)km を 時速(\d+)km", t)[1])
        aruki = int(re.search(r"目的地まで (\d+)分 歩", t).group(1))
        t1, t2 = F(d1 * 60, v1), F(d2 * 60, v2)      # 分（分数のまま）
        for nm, vv in (("1本目の所要", t1), ("2本目の所要", t2)):
            r = _seisu(vv, nm)
            if isinstance(r, Dame):
                return r
        fun = h * 60 + m + int(t1) + machi + int(t2) + aruki
        return (fun // 60) % 24 * 100 + fun % 60

    if k == "すうれつ6段":
        r0, r1, r2, r3 = map(int, re.search(
            r"は (\d+), (\d+), (\d+), (\d+), \.\.\.", t).groups())
        e = int(re.search(r"毎回 (\d+) ずつ 大きく", t).group(1))
        n = int(re.search(r"の (\d+)番目の数", t).group(1))
        hiku = int(re.search(r"数から (\d+) を 引いて", t).group(1))
        mod = int(re.search(r"、(\d+) で 割った", t).group(1))
        # ★ 別経路: 生成側は足しながら進める。こちらは 最初の4項から
        #   規則が本当に成り立っているかを確かめ、一般項の式で n番目を出す。
        d0 = r1 - r0
        if (r2 - r1) - d0 != e or (r3 - r2) - (r2 - r1) != e:
            return Dame("差の増え方が問題文と合わない")
        # a_n = r0 + (n-1)*d0 + e*(n-1)(n-2)/2
        an = r0 + (n - 1) * d0 + e * (n - 1) * (n - 2) // 2
        return (an - hiku) % mod

    if k == "ぶんぱい6段":
        t_all = int(re.search(r"ぜんぶで (\d+)", t).group(1))
        x1, y1, z1 = map(int, re.search(r"で (\d+):(\d+):(\d+) の 割合", t).groups())
        w = int(re.search(r"さんに (\d+)\S+ わたし", t).group(1))
        p = int(re.search(r"ぶんの (\d+)% を", t).group(1))
        g = F(t_all, x1 + y1 + z1)
        if g.denominator != 1:
            return Dame("比で割り切れない")
        g = int(g)
        A, B, C = x1 * g, y1 * g, z1 * g
        ido = F(C * p, 100)
        if ido.denominator != 1:
            return Dame("%d%% が割り切れない" % p)
        A2, B2, C2 = A - w + int(ido), B + w, C - int(ido)
        if min(A2, B2, C2) < 0:
            return Dame("マイナスになる")
        return max(A2, B2, C2) - min(A2, B2, C2)

    return Dame("知らない型: %s" % k)


def main():
    f = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "mondai_6dan.jsonl")
    d = [json.loads(l) for l in io.open(f, encoding="utf-8") if l.strip()]
    warui = []
    for x in d:
        try:
            v = kenzan(x)
        except Exception as e:
            warui.append((x["id"], x["型"], "検算できず", "%s: %s" % (type(e).__name__, e)))
            continue
        if isinstance(v, Dame):
            warui.append((x["id"], x["型"], "問題が成り立たない", str(v)))
            continue
        if x["答の形"] == "数":
            chigau = abs(float(v) - float(x["答"])) > 1e-9
        else:
            chigau = str(v) != x["答"]
        if chigau:
            warui.append((x["id"], x["型"], x["答"], v))
    print("%d問を 別の書き方で検算" % len(d))
    print("  食い違い: %d 件" % len(warui))
    if warui:
        print("  型ごと:", dict(Counter(w[1] for w in warui)))
        for w in warui[:8]:
            print("   ", w)
    else:
        print("  → ★ 全問 答えが正しい")
    return len(warui)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
