#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深さの決め方を 直感役の仕組み（chokkan.Model・文字 n-gram の回帰）で学習して測る。頭脳なし。

  材料: kekka/fukasa120_f0.json・fukasa6dan_f0.json・fukasa7dan_f0.json（深さ0 の正誤つき 368問）。× → 深い、○ → 浅い
  5分割の交差検証で、線ごとに「落とした問い（×）を拾う割合」と「○ を深くする割合（無駄）」を出し、今の おまかせ（teachers.fukasa_miru）と比べる。
  9/18 の頭脳 1トークン判定は 落とした 54 を線 0.3 で 19 しか拾えなかった。学習ならどうか。
"""
import json, os, random, sys
KERNEL = os.environ.get("KERNEL_DIR") or os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import chokkan, teachers
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    rows = []
    for fn, kumi in (("fukasa120_f0.json", "120"), ("fukasa6dan_f0.json", "6段"), ("fukasa7dan_f0.json", "7段")):
        for r in json.load(open(os.path.join(HERE, "kekka", fn), encoding="utf-8"))["一件ずつ"]:
            rows.append({"組": kumi, "問": r["問"], "深い": not r.get("○"), "型": r.get("型")})
    rnd = random.Random(0)
    rnd.shuffle(rows)
    K = 5
    for i, r in enumerate(rows):
        r["fold"] = i % K
    for r in rows:
        r["p"] = None
    for k in range(K):
        gaku = [(r["問"], "深い" if r["深い"] else "浅い") for r in rows if r["fold"] != k]
        m = chokkan.Model(["浅い", "深い"]).train(gaku, epochs=30, quiet=True)
        for r in rows:
            if r["fold"] == k:
                r["p"] = m.kakuritsu(chokkan.tokuchou(r["問"]), T=1.0)[1]
        r_ = None
    ochi = [r for r in rows if r["深い"]]
    atari = [r for r in rows if not r["深い"]]
    print("落とした問い %d・合った問い %d（5分割の交差検証・学習は 4/5 で）" % (len(ochi), len(atari)))
    om = [teachers.fukasa_miru(r["問"]) == 2 for r in rows]
    print("  おまかせ（今）: 拾えた %d/%d・○を深くした %d/%d" % (sum(1 for r, o in zip(rows, om) if r["深い"] and o), len(ochi), sum(1 for r, o in zip(rows, om) if not r["深い"] and o), len(atari)))
    for sen in (0.05, 0.1, 0.2, 0.3, 0.5):
        print("  p ≧ %.2f     : 拾えた %d/%d・○を深くした %d/%d" % (sen, sum(1 for r in ochi if r["p"] >= sen), len(ochi), sum(1 for r in atari if r["p"] >= sen), len(atari)))
    for kumi in ("120", "6段", "7段"):
        rs = [r for r in rows if r["組"] == kumi]
        print("  %s: 平均 p（× %.2f／○ %.2f）" % (kumi, sum(r["p"] for r in rs if r["深い"]) / max(1, sum(1 for r in rs if r["深い"])), sum(r["p"] for r in rs if not r["深い"]) / max(1, sum(1 for r in rs if not r["深い"]))))
    print("  落とした問いの p が低い順:", ", ".join("%s %.2f" % (r["型"], r["p"]) for r in sorted(ochi, key=lambda r: r["p"])[:8]))


if __name__ == "__main__":
    main()
