#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imi_jikken.py -- 「意味」を、資料から作れるか。1時間で決着をつける実験

  ────────────────────────────────────────────────
  なぜやるか
  ────────────────────────────────────────────────
  hdv.atom() は 語の名前のハッシュ から ビット列を作っている。
  だから「絵」と「画像」は、まったくの別物になる。実測:

      絵 と 画像     : 0.489
      絵 と ラーメン : 0.509      ← 区別がついていない

  1万ビットは「意味の空間」ではなく、語ごとのランダムな背番号だった。
  これでは、教えていない語は永久に分からない。

  ────────────────────────────────────────────────
  やること（掛け算なし・乱数なし）
  ────────────────────────────────────────────────
  語のビット列を、名前からではなく「その語の周りに出る文字」から作る。

      ① その語が出てくる場所を全部さがす      … 数えるだけ
      ② 前後の窓の中の 2文字ならび を集める    … 切り出すだけ
      ③ それぞれの atom を 多数決で束ねる      … 多数決だけ
      ④ 近さは XOR して 1 の数を数える         … XOR と popcount だけ

  掛け算はどこにも無い。乱数も無い（atom はハッシュ種の再現可能なもの）。

  ────────────────────────────────────────────────
  合否
  ────────────────────────────────────────────────
  「絵 と 画像」が「絵 と ラーメン」より 近くなれば 合格。
  近くならなければ、7.2MB では足りないと分かる。次は資料集めが先になる。
"""
import os, sys, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus_moji.txt")
MADO = 10          # 前後 何文字を「まわり」とみなすか
SAIDAI = 4000      # 1語あたり、集める まわり の数の上限（速さのため）

# 似ているはずの組（近くなってほしい）
NITERU = [("絵", "画像"), ("音声", "音楽"), ("資料", "書類"),
          ("映像", "動画"), ("写真", "画像"), ("曲", "音楽")]
# 無関係な組（遠くなってほしい）
MUKANKEI = [("絵", "ラーメン"), ("音声", "宇宙"), ("資料", "ラーメン"),
            ("映像", "宇宙"), ("写真", "ラーメン"), ("曲", "宇宙")]


def mawari(text, word, mado=MADO, saidai=SAIDAI):
    """その語の まわりに出る 2文字ならび を、数えて返す"""
    c = collections.Counter()
    i, n, atsumeta = 0, len(word), 0
    while atsumeta < saidai:
        i = text.find(word, i)
        if i < 0:
            break
        a = max(0, i - mado)
        b = min(len(text), i + n + mado)
        mae, ato = text[a:i], text[i + n:b]
        for s in (mae, ato):
            for k in range(len(s) - 1):
                futa = s[k:k + 2]
                if futa.strip():
                    c[futa] += 1
        i += n
        atsumeta += 1
    return c, atsumeta


def imi_vector(text, word):
    """その語の「意味」＝ まわりの 2文字ならび を束ねたもの"""
    c, n = mawari(text, word)
    if not c:
        return None, 0
    vs, ws = [], []
    for futa, kaisu in c.most_common(600):
        vs.append(hdv.atom(futa))
        ws.append(kaisu)          # 多数決の票数。掛け算ではない
    return hdv.bundle(vs, ws), n


def main():
    print("資料を読みます…", flush=True)
    text = open(CORPUS, encoding="utf-8").read()
    print(f"  {len(text):,} 文字\n")

    goi = sorted({w for pair in NITERU + MUKANKEI for w in pair})
    v, deta = {}, {}
    t0 = time.time()
    for w in goi:
        vec, n = imi_vector(text, w)
        v[w], deta[w] = vec, n
        print(f"  {w:　<5} 出てきた回数 {n:>5}")
    print(f"  （{time.time()-t0:.1f} 秒）\n")

    def tikasa(a, b):
        if v[a] is None or v[b] is None:
            return None
        return hdv.hamming(v[a], v[b]) / hdv.DIM

    print("■ 名前のハッシュから作った場合（いまのカーネル）")
    for label, kumi in (("似ている組", NITERU), ("無関係な組", MUKANKEI)):
        ds = []
        for a, b in kumi:
            d = hdv.hamming(hdv.atom(a), hdv.atom(b)) / hdv.DIM
            ds.append(d)
        print(f"  {label}の遠さ 平均 {sum(ds)/len(ds):.3f}")

    print("\n■ 資料のまわりから作った場合（この実験）")
    kekka = {}
    for label, kumi in (("似ている組", NITERU), ("無関係な組", MUKANKEI)):
        ds = []
        for a, b in kumi:
            d = tikasa(a, b)
            if d is None:
                continue
            ds.append(d)
            print(f"    {a:　<4} と {b:　<6} : {d:.3f}")
        kekka[label] = sum(ds) / len(ds) if ds else None
        print(f"  → {label}の遠さ 平均 {kekka[label]:.3f}\n")

    ni, mu = kekka["似ている組"], kekka["無関係な組"]
    sa = mu - ni
    print("=" * 56)
    print(f"  似ている組のほうが {sa:+.3f} 近い")
    if sa > 0.02:
        print("  → 合格。資料から『意味の近さ』が作れている")
    elif sa > 0:
        print("  → 差はあるが、小さい。資料が足りない可能性が高い")
    else:
        print("  → 不合格。7.2MB では足りない。次は資料集めが先")
    print("=" * 56)


if __name__ == "__main__":
    main()
