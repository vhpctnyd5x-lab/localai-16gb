#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tsetlin_kotoba.py -- ツェットリン機械に「語の見極め」をやらせ、いまのやり方と比べる

  【公平に比べるために】
  はじめ、語の「字面」だけを条件にして試したら 9/17 だった。
  だが pc_kind（1万ビット）が見ているのは字面ではなく
  「どの記事に出たか」。材料が違うのに勝ち負けは言えない。
  そこで同じ材料に揃えた。

  条件 = 「記事 A に出てくる」を 83 本ぶん（＋字面）
  掛け算はしない。式は読める。
"""
import json, os, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsetlin, pc_kind

KUMI = ["画像", "動画", "音楽", "書類", "テキスト", "圧縮"]
HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    d = json.load(open(os.path.join(HERE, "pc_web.json")))
    kiji = d["記事ごとの語"]
    # 語 -> 出てきた記事の番号
    deta = {}
    for i, a in enumerate(kiji):
        for w, c in a["語"]:
            deta.setdefault(w, set()).add(i)
    return d, kiji, deta


def main():
    d, kiji, deta = load()
    namae = [f"「{a['題']}」に出る" for a in kiji]
    n = len(kiji)
    print(f"条件 {n} 本（記事の題）／語 {len(deta):,}")

    def xb_of(w):
        b = 0
        for i in deta.get(w, ()):
            b |= 1 << i
        return b

    data = []
    for kind in KUMI:
        for w, c in d["話ごとの語"].get(kind, []):
            if len(w) >= 2:
                data.append((w, kind))
    nozoku = {w for w, _ in pc_kind.TESTS}
    tr = [(w, k) for w, k in data if w not in nozoku]
    rnd = random.Random(0); rnd.shuffle(tr)
    X = [(xb_of(w), k) for w, k in tr]
    X = [(x, k) for x, k in X if x]
    print(f"学ぶ語 {len(X):,}（試験の語は外してある）")

    m = tsetlin.Wakeru(n, KUMI, kata=100, T=15, s=6.0)
    t0 = time.time()
    for _ in range(20):
        rnd.shuffle(X)
        for x, y in X:
            m.manabu(x, y)
    print(f"学ぶのに {time.time()-t0:.1f} 秒\n")

    print("■ 見たことのない語（pc_kind と同じ問題・同じ材料）")
    ok = 0
    for w, want in pc_kind.TESTS:
        got, sc = m.kotae(xb_of(w), shikii=1)
        ok += (got == want)
        mark = "✓" if got == want else "✗"
        print(f"   {mark} {w} → {got}" + ("" if got == want else f"（ほしい: {want}）"))
    print(f"   {ok}/{len(pc_kind.TESTS)}   ← pc_kind は 14/17")

    print("\n■ 関係のない語（答えてはいけない）")
    dam = 0
    for w in pc_kind.NONSENSE:
        got, sc = m.kotae(xb_of(w), shikii=1)
        dam += (got is None)
        print(f"   {'✓黙った' if got is None else '✗'+str(got)} {w}"
              f"  （最高票 {max(sc.values())}）")
    print(f"   {dam}/{len(pc_kind.NONSENSE)}   ← pc_kind は 9/9")

    print("\n■ 学んだ式（ここが ニューラルネットには出せない）")
    for k in ("音楽", "圧縮", "書類"):
        print(f"  ［{k}］")
        for p, jo in m.ki[k].shiki(namae, 3):
            print(f"     {p}: " + " かつ ".join(jo))


if __name__ == "__main__":
    main()
