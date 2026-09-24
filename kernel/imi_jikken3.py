#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imi_jikken3.py -- 「まわりの数え方」を変えると、意味の差は広がるか

  前回（imi_jikken.py）は まわりを 2文字ならび で数えて 差 +0.054 だった。
  2文字ならびは、語の切れ目を無視して切っている。
      「画像を見る」→ 画像 / 像を / を見 / 見る
      「像を」「を見」は 語をまたいだゴミ。半分がゴミかもしれない。

  そこで 樹形図（文字のトライ木）の 分岐の多さ で語に切ってから数える。
      「画像を見る」→ 画像 / を / 見る
  ゴミが減れば、差は広がるはず。これを測る。

  比べるやり方（同じ資料・同じ組で）:
      ① 1文字
      ② 2文字ならび      … 前回のやり方
      ③ 3文字ならび
      ④ 樹形図で語に切る  … 今回の本命

  資料は corpus_snap_A.txt（凍らせた写し）を使う。
  裏で資料を集めているので、生の corpus_moji.txt を使うと数字が動く。
"""
import os, sys, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv, mojiyosou

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "corpus_snap_A.txt")
MADO = 10
SAIDAI = 4000
KI_JI = 2_000_000     # 樹形図を建てるのに使う字数
KI_N = 4              # 樹形図の深さ

NITERU = [("絵", "画像"), ("音声", "音楽"), ("資料", "書類"),
          ("映像", "動画"), ("写真", "画像"), ("曲", "音楽"),
          ("机", "椅子"), ("犬", "猫"), ("車", "電車"),
          ("学校", "大学"), ("医者", "看護師"), ("川", "湖"),
          ("東京", "大阪"), ("父", "母"), ("朝", "夕方"),
          ("本", "雑誌"), ("道路", "線路"), ("会社", "工場")]
MUKANKEI = [("絵", "ラーメン"), ("音声", "宇宙"), ("資料", "ラーメン"),
            ("映像", "宇宙"), ("写真", "ラーメン"), ("曲", "宇宙"),
            ("机", "宇宙"), ("犬", "ラーメン"), ("車", "宇宙"),
            ("学校", "ラーメン"), ("医者", "宇宙"), ("川", "ラーメン"),
            ("東京", "宇宙"), ("父", "ラーメン"), ("朝", "宇宙"),
            ("本", "ラーメン"), ("道路", "宇宙"), ("会社", "ラーメン")]


def _mado_moji(text, word, mado=MADO, saidai=SAIDAI):
    """その語のまわりの 生の文字列 を集めて返す"""
    out = []
    i, n = 0, len(word)
    while len(out) < saidai:
        i = text.find(word, i)
        if i < 0:
            break
        a = max(0, i - mado)
        b = min(len(text), i + n + mado)
        out.append(text[a:i])
        out.append(text[i + n:b])
        i += n
    return out, len(out) // 2


def kazoeru_ngram(mados, n):
    c = collections.Counter()
    for s in mados:
        for k in range(len(s) - n + 1):
            g = s[k:k + n]
            if g.strip():
                c[g] += 1
    return c


def kazoeru_kugiri(mados, y):
    c = collections.Counter()
    for s in mados:
        if not s.strip():
            continue
        for g in y.kugiri(s):
            g = g.strip()
            if g:
                c[g] += 1
    return c


def tsukuru(c, joui=600):
    if not c:
        return None
    vs, ws = [], []
    for g, k in c.most_common(joui):
        vs.append(hdv.atom(g))
        ws.append(k)
    return hdv.bundle(vs, ws)


def hyouka(namae, tsukurikata, goi, mados):
    v = {}
    for w in goi:
        v[w] = tsukurikata(mados[w])
    def d(a, b):
        if v[a] is None or v[b] is None:
            return None
        return hdv.hamming(v[a], v[b]) / hdv.DIM
    kek = {}
    for label, kumi in (("似", NITERU), ("無", MUKANKEI)):
        ds = [x for x in (d(a, b) for a, b in kumi) if x is not None]
        kek[label] = sum(ds) / len(ds) if ds else None
    sa = kek["無"] - kek["似"]
    print(f"  {namae:　<14} 似 {kek['似']:.3f} ／ 無 {kek['無']:.3f} → 差 {sa:+.3f}")
    return sa


def main():
    print("資料を読みます…", flush=True)
    text = open(SNAP, encoding="utf-8").read()
    print(f"  {len(text):,} 文字（凍らせた写し）\n")

    goi = sorted({w for p in NITERU + MUKANKEI for w in p})
    print("まわりを切り出します…", flush=True)
    mados, t0 = {}, time.time()
    for w in goi:
        mados[w], n = _mado_moji(text, w)
        print(f"  {w:　<5} {n:>5} 回")
    print(f"  （{time.time()-t0:.1f} 秒）\n")

    print("=" * 60)
    print("■ まわりの数え方をくらべる")
    print("=" * 60)
    kek = {}
    for n in (1, 2, 3):
        kek[f"{n}文字"] = hyouka(f"{n}文字ならび",
                                 lambda m, n=n: tsukuru(kazoeru_ngram(m, n)),
                                 goi, mados)

    print(f"\n  樹形図を建てます（{KI_JI:,}字・深さ{KI_N}）…", flush=True)
    t0 = time.time()
    y = mojiyosou.Yosou(max_n=KI_N)
    y.oboeru(text[:KI_JI])
    print(f"  （{time.time()-t0:.1f} 秒・文脈 {len(y.tbl):,} 通り）")

    t0 = time.time()
    kek["語切り"] = hyouka("樹形図で語に切る",
                           lambda m: tsukuru(kazoeru_kugiri(m, y)),
                           goi, mados)
    print(f"  （{time.time()-t0:.1f} 秒）")

    print("\n" + "=" * 60)
    best = max(kek, key=lambda k: kek[k])
    print(f"  いちばん差が大きい: {best}（{kek[best]:+.3f}）")
    print(f"  前回のやり方(2文字): {kek['2文字']:+.3f}")
    if best == "語切り" and kek["語切り"] > kek["2文字"] + 0.005:
        print("  → 語に切るほうが良い。採用する価値あり")
    else:
        print("  → 語に切っても良くならなかった")
    print("=" * 60)


if __name__ == "__main__":
    main()
