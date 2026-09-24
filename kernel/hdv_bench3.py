#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hdv_bench3.py -- 材料を替えたら、語の意味あては当たるようになるか

  前回わかったこと:
    ・1万ビットで語の意味をあてる … 12%
    ・いまの表引き（掛け算あり）  … 24%
    どちらもひどい。しかも近さが全部 0.51（＝でたらめと同じ）だった。

  原因は表し方ではなく材料だった。
    辞書の「画像」     → 人物 / 洋風 / 弟子    （絵画の意味）
    Wikipediaの「壁紙」→ 建築物の内装仕上材    （建材の意味）

  そこで材料を「パソコンの話の記事」に替えて、同じ測り方でやり直す。

  ────────────────────────────────────────
  ずるをしないための決めごと
  ────────────────────────────────────────
  試す語そのものは、どのベクトルにも入れない。
  入れると「自分で自分を当てる」ことになる。

    記事のベクトル = その記事に出てくる語をたばねたもの（試す語は抜く）
    種類の手本     = その種類の記事のベクトルをたばねたもの
    試す語の姿     = その語が出てくる記事のベクトルをたばねたもの

  つまり「その語が出てくる記事は、どの種類の記事に似ているか」で決める。
  掛け算は1回も使わない。
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv, corpus_pc

TESTS = [
    ("スナップ写真", "画像"), ("自撮り", "画像"), ("壁紙", "画像"),
    ("サムネイル", "画像"), ("挿絵", "画像"),
    ("映画", "動画"), ("実写", "動画"), ("アニメ", "動画"),
    ("契約書", "書類"), ("請求書", "書類"), ("報告書", "書類"),
    ("覚書", "テキスト"), ("下書き", "テキスト"), ("原稿", "テキスト"),
    ("楽曲", "音楽"), ("音源", "音楽"), ("歌詞", "音楽"),
]
BANNED = {w for w, _k in TESTS}


def doc_vec(words, drop=BANNED):
    """記事1本を1万ビットにする。試す語は必ず抜く"""
    vs, ws = [], []
    for w, n in words:
        if w in drop:
            continue
        vs.append(hdv.atom(w))
        ws.append(min(n, 5))          # 出過ぎる語に引っぱられないよう頭打ち
    return hdv.bundle_bits(vs, ws) if vs else 0


def main():
    data = corpus_pc.load()
    if not data or "記事ごとの語" not in data:
        print("  材料がありません。先に  python3 corpus_pc.py  を動かしてください")
        return
    docs = data["記事ごとの語"]
    kinds = sorted({d["種類"] for d in docs})
    print(f"  材料: 記事 {len(docs)} 本 / 語 {data['語数']:,} 個 / 種類 {len(kinds)}\n")

    t0 = time.time()
    dvec = [doc_vec(d["語"]) for d in docs]
    proto = {}
    for k in kinds:
        vs = [v for d, v in zip(docs, dvec) if d["種類"] == k]
        proto[k] = hdv.bundle_bits(vs) if vs else 0
    build_ms = (time.time() - t0) * 1000

    # どの語が、どの記事に出るか
    where = {}
    for i, d in enumerate(docs):
        for w, n in d["語"]:
            where.setdefault(w, []).append((i, n))

    t1 = time.time()
    ok, rows, unknown = 0, [], 0
    for w, want in TESTS:
        hits = where.get(w)
        if not hits:
            unknown += 1
            rows.append((w, want, "（材料に無い）", 0.0, 0.0, False))
            continue
        q = hdv.bundle_bits([dvec[i] for i, _n in hits],
                            [min(n, 5) for _i, n in hits])
        sc = sorted(((hdv.near(q, p), k) for k, p in proto.items()), reverse=True)
        got, s = sc[0][1], sc[0][0]
        good = got == want
        ok += good
        rows.append((w, want, got, s, s - sc[1][0], good))
    ms = (time.time() - t1) * 1000

    print("■ パソコンの話を材料にして、1万ビットで当てる（かけ算 0回）")
    print(f"  正解: {ok}/{len(TESTS)}  （{ok/len(TESTS)*100:.0f}%）"
          f"   材料に無かった語: {unknown}")
    print(f"  時間: 手本づくり {build_ms:.0f}ミリ秒 ／ 判定 {ms:.1f}ミリ秒\n")
    for w, want, got, s, mg, good in rows:
        mark = "✓" if good else "✗"
        print(f"  {mark} {w:<12} → {got:<8} (近さ {s:.3f} 差 {mg:+.3f})"
              + ("" if good else f"  ほしい: {want}"))

    # 比べる相手① 数えるだけ（1万ビットも使わない）
    prof = data["語の話ぶり"]
    ok2 = sum(1 for w, want in TESTS
              if prof.get(w) and max(prof[w], key=prof[w].get) == want)
    print(f"\n■ 数えるだけ（どの話に多く出たか）: {ok2}/{len(TESTS)}"
          f"  （{ok2/len(TESTS)*100:.0f}%）")

    # 比べる相手② いままでの材料（辞書）
    print("■ 前の材料（辞書）での成績          :  2/17  （12%）")
    print("■ いままでの表引き（小数のかけ算）   :  4/17  （24%）")


if __name__ == "__main__":
    main()
