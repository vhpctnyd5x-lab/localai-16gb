#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imi_jikken4.py -- 測りかたを直して、資料量の効きを見る

  【前の測りかたの誤り】
  「似ている組の遠さ」と「無関係な組の遠さ」の 引き算 で比べていた。
  ところが やり方を変えると 遠さの目盛りごと変わる。
      1文字ならび : 似 0.230 ／ 無 0.257   （どちらも近い）
      3文字ならび : 似 0.410 ／ 無 0.457   （どちらも遠い）
  目盛りが違うものの引き算を並べても、公平ではない。私の測りかたが悪かった。

  【直したもの】勝ち負けで測る。目盛りに左右されない。
      「絵」にとって「画像」は「ラーメン」より近いか？ → ○か×
      18組ぜんぶで数えて 勝率 を出す。
  これは カーネルが実際にやること（どっちの札か選ぶ）と同じ形をしている。

  【いっしょに見るもの】
  資料を 50万字・100万字・200万字…と増やして、勝率が上がるかどうか。
  上がらなければ、量の問題ではないと分かる。
"""
import os, sys, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "corpus_snap_A.txt")
MADO = 10
SAIDAI = 4000

KUMI = [  # (語, 似ているはず, 無関係)
    ("絵", "画像", "ラーメン"), ("音声", "音楽", "宇宙"),
    ("資料", "書類", "ラーメン"), ("映像", "動画", "宇宙"),
    ("写真", "画像", "ラーメン"), ("曲", "音楽", "宇宙"),
    ("机", "椅子", "宇宙"), ("犬", "猫", "ラーメン"),
    ("車", "電車", "宇宙"), ("学校", "大学", "ラーメン"),
    ("医者", "看護師", "宇宙"), ("川", "湖", "ラーメン"),
    ("東京", "大阪", "宇宙"), ("父", "母", "ラーメン"),
    ("朝", "夕方", "宇宙"), ("本", "雑誌", "ラーメン"),
    ("道路", "線路", "宇宙"), ("会社", "工場", "ラーメン"),
]


def mawari(text, word, mado=MADO, saidai=SAIDAI):
    out = []
    i, n = 0, len(word)
    while len(out) < saidai:
        i = text.find(word, i)
        if i < 0:
            break
        out.append(text[max(0, i - mado):i])
        out.append(text[i + n:min(len(text), i + n + mado)])
        i += n
    return out, len(out) // 2


def vec(mados, n, joui=600):
    c = collections.Counter()
    for s in mados:
        for k in range(len(s) - n + 1):
            g = s[k:k + n]
            if g.strip():
                c[g] += 1
    if not c:
        return None
    vs, ws = [], []
    for g, k in c.most_common(joui):
        vs.append(hdv.atom(g)); ws.append(k)
    return hdv.bundle(vs, ws)


def hakaru(text, n):
    """勝率と、参考までに 出た回数の中央値 を返す"""
    goi = sorted({w for k in KUMI for w in k})
    v, kaisu = {}, {}
    for w in goi:
        m, c = mawari(text, w)
        kaisu[w] = c
        v[w] = vec(m, n)
    kachi, zen, make = 0, 0, []
    for moto, ni, mu in KUMI:
        if v[moto] is None or v[ni] is None or v[mu] is None:
            continue
        zen += 1
        d_ni = hdv.hamming(v[moto], v[ni])
        d_mu = hdv.hamming(v[moto], v[mu])
        if d_ni < d_mu:
            kachi += 1
        else:
            make.append(f"{moto}-{ni}")
    ks = sorted(kaisu.values())
    return kachi, zen, make, ks[len(ks) // 2]


def main():
    text = open(SNAP, encoding="utf-8").read()
    print(f"資料（凍らせた写し）: {len(text):,} 文字\n")

    print("=" * 62)
    print("■ ① 測りかたを直した ― 勝率（18組・全文）")
    print("=" * 62)
    for n in (1, 2, 3, 4):
        k, z, make, med = hakaru(text, n)
        print(f"  {n}文字ならび : {k}/{z}  （{k*100//z}%）　負け: {' '.join(make) or 'なし'}")

    print("\n" + "=" * 62)
    print("■ ② 資料を増やすと 勝率は上がるか（2文字ならび）")
    print("=" * 62)
    for wari in (0.0625, 0.125, 0.25, 0.5, 1.0):
        bu = text[:int(len(text) * wari)]
        k, z, make, med = hakaru(bu, 2)
        print(f"  {len(bu)//10000:>4}万字 : {k}/{z}  （{k*100//z}%）　"
              f"語の出た回数の中央値 {med}")
    print("=" * 62)


if __name__ == "__main__":
    main()
