#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imi_jikken2.py -- 「資料の傾向」を引いてみる

  ────────────────────────────────────────────────
  imi_jikken.py で分かったこと
  ────────────────────────────────────────────────
      似ている組 0.360 ／ 無関係な組 0.417   （差 +0.057）

  差は出たが、小さい。理由ははっきりしている。

  日本語の文はどれも「の」「は」「した」「ある」で出来ている。
  どの語のまわりにも同じものが出るので、
  「絵」も「ラーメン」も、まわりの大半が同じになる。
  この共通部分が、違いを埋めてしまっている。

  ────────────────────────────────────────────────
  やること：資料ぜんたいの「傾向」を引く
  ────────────────────────────────────────────────
  資料ぜんたいで、その2文字ならびが どれくらい よく出るかを数える。
  その語のまわりで「ぜんたいより目立って多く出る」ものだけを残す。

      その語のまわりでの割合  >  資料ぜんたいでの割合

  比べるだけ。割り算を避けるため、たすきがけの形で比べる。
      a/b > c/d  ⟺  a*d > c*b   … これは掛け算が要る
  なので、そうではなく「順位」で比べる。順位は並べ替えだけで出る。

  掛け算なし・割り算なし・乱数なし。
"""
import os, sys, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus_moji.txt")
MADO = 10
SAIDAI = 4000
NOKOSU = 400        # 1語につき、残す「まわり」の数

NITERU = [("絵", "画像"), ("音声", "音楽"), ("資料", "書類"),
          ("映像", "動画"), ("写真", "画像"), ("曲", "音楽")]
MUKANKEI = [("絵", "ラーメン"), ("音声", "宇宙"), ("資料", "ラーメン"),
            ("映像", "宇宙"), ("写真", "ラーメン"), ("曲", "宇宙")]


def zentai_junni(text, kizami=200000):
    """資料ぜんたいでの、2文字ならびの「よく出る順」の順位表"""
    c = collections.Counter()
    for i in range(0, len(text) - 1, 1):
        f = text[i:i + 2]
        if f.strip():
            c[f] += 1
    junni = {}
    for i, (f, _n) in enumerate(c.most_common()):
        junni[f] = i          # 0 が いちばん よく出る
    return junni, c


def mawari(text, word, mado=MADO, saidai=SAIDAI):
    c = collections.Counter()
    i, n, atsumeta = 0, len(word), 0
    while atsumeta < saidai:
        i = text.find(word, i)
        if i < 0:
            break
        a, b = max(0, i - mado), min(len(text), i + n + mado)
        for s in (text[a:i], text[i + n:b]):
            for k in range(len(s) - 1):
                f = s[k:k + 2]
                if f.strip():
                    c[f] += 1
        i += n
        atsumeta += 1
    return c, atsumeta


def imi_vector(text, word, zen_junni, hiku=True):
    """その語の意味。hiku=True なら「ぜんたいの傾向」を引く"""
    c, n = mawari(text, word)
    if not c:
        return None, 0
    if hiku:
        # その語のまわりでの順位と、ぜんたいでの順位を比べる。
        # ぜんたいより ぐっと上に来たものだけが、この語らしさ。
        # 順位は並べ替えだけで出る（掛け算も割り算も要らない）
        migoto = []
        for i, (f, kaisu) in enumerate(c.most_common()):
            zen = zen_junni.get(f)
            if zen is None:
                continue
            agari = zen - i          # 引き算だけ。大きいほど「この語らしい」
            migoto.append((agari, kaisu, f))
        migoto.sort(reverse=True)
        erabu = [(f, kaisu) for _a, kaisu, f in migoto[:NOKOSU]]
    else:
        erabu = c.most_common(NOKOSU)
    vs = [hdv.atom(f) for f, _k in erabu]
    ws = [k for _f, k in erabu]
    return hdv.bundle(vs, ws), n


def hyouka(text, zen_junni, hiku):
    v = {}
    for w in sorted({x for p in NITERU + MUKANKEI for x in p}):
        v[w], _ = imi_vector(text, w, zen_junni, hiku)
    def d(a, b):
        return hdv.hamming(v[a], v[b]) / hdv.DIM
    ni = [d(a, b) for a, b in NITERU]
    mu = [d(a, b) for a, b in MUKANKEI]
    return sum(ni) / len(ni), sum(mu) / len(mu), v


def main():
    print("資料を読みます…", flush=True)
    text = open(CORPUS, encoding="utf-8").read()
    print(f"  {len(text):,} 文字")
    print("ぜんたいの傾向を数えます…", flush=True)
    t0 = time.time()
    zen_junni, zen_c = zentai_junni(text)
    print(f"  2文字ならび {len(zen_junni):,} 種類  （{time.time()-t0:.1f} 秒）")
    print(f"  いちばん多い10: " + "、".join(f for f, _ in zen_c.most_common(10)))
    print()

    for hiku, label in ((False, "傾向を引かない（前回のやり方）"),
                        (True,  "傾向を引く（今回の案）")):
        ni, mu, v = hyouka(text, zen_junni, hiku)
        sa = mu - ni
        print(f"■ {label}")
        print(f"    似ている組 {ni:.3f} ／ 無関係な組 {mu:.3f}")
        print(f"    → 差 {sa:+.3f}")
        if hiku:
            print()
            for a, b in NITERU:
                print(f"      {a:　<4} と {b:　<6} : "
                      f"{hdv.hamming(v[a], v[b])/hdv.DIM:.3f}")
            for a, b in MUKANKEI:
                print(f"      {a:　<4} と {b:　<6} : "
                      f"{hdv.hamming(v[a], v[b])/hdv.DIM:.3f}")
        print()


if __name__ == "__main__":
    main()
