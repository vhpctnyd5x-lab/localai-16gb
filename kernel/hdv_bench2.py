#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hdv_bench2.py -- 正しいやり方で測り直す

  前回は「辞書が教える画像の意味（＝絵画）」と比べていた。
  それでは当たるはずがない。

  HDC の本来の使い方は「見本から手本(prototype)を作る」。
    画像の手本 = 写真・イメージ・スクショ… を たばねたもの
  そして、知らない語の意味を、その手本と比べる。

  大事なのは、試す語を手本の材料に入れないこと（自分で自分を当てない）。
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv, kernel

kernel.load_learned()
sp = hdv.Space().load(os.path.join(os.path.dirname(__file__), "hdv_space.bin"))
web = json.load(open(os.path.join(os.path.dirname(__file__), "bg_web.json"),
                     encoding="utf-8"))

# 札から「見本」を集める
EXAMPLES = {}
for k, (slot, val) in kernel.SEED.items():
    if slot == "種類" and len(k) >= 2:
        EXAMPLES.setdefault(val, []).append(k)

# 試す語（札に無いもの）
TESTS = [
    ("スナップ写真", "画像"), ("自撮り", "画像"), ("壁紙", "画像"),
    ("サムネイル", "画像"), ("挿絵", "画像"),
    ("映画", "動画"), ("実写", "動画"), ("アニメ", "動画"),
    ("契約書", "書類"), ("請求書", "書類"), ("報告書", "書類"),
    ("覚書", "テキスト"), ("下書き", "テキスト"), ("原稿", "テキスト"),
    ("楽曲", "音楽"), ("音源", "音楽"), ("歌詞", "音楽"),
]


def ctx_of(w):
    """その語のまわりの語。無ければ語そのもの"""
    return web.get(w) or [w]


def prototype(kind):
    """見本から手本を作る。語そのものと、そのまわりを両方たばねる"""
    vs, ws = [], []
    for ex in EXAMPLES.get(kind, []):
        vs.append(hdv.atom(ex)); ws.append(3)
        for c in ctx_of(ex)[:8]:
            vs.append(hdv.atom(c)); ws.append(1)
    return hdv.bundle_bits(vs, ws) if vs else 0


def query(w):
    """試す語も、同じやり方でベクトルにする"""
    vs, ws = [hdv.atom(w)], [3]
    for c in ctx_of(w)[:8]:
        vs.append(hdv.atom(c)); ws.append(1)
    return hdv.bundle_bits(vs, ws)


def main():
    print("■ 手本の材料（札から集めたもの）")
    for k, v in sorted(EXAMPLES.items()):
        print(f"  {k:<8} {' / '.join(v)}")

    protos = {k: prototype(k) for k in EXAMPLES}
    t0 = time.time()
    ok, rows = 0, []
    for w, want in TESTS:
        q = query(w)
        scored = sorted(((hdv.near(q, p), k) for k, p in protos.items()),
                        reverse=True)
        got, s = scored[0][1], scored[0][0]
        margin = s - scored[1][0]
        good = got == want
        ok += good
        rows.append((w, want, got, s, margin, good))
    ms = (time.time() - t0) * 1000

    print(f"\n■ 手本と比べる（かけ算 0回）")
    print(f"  正解: {ok}/{len(TESTS)}  （{ok/len(TESTS)*100:.0f}%）")
    print(f"  時間: {ms:.0f} ミリ秒 （1件 {ms/len(TESTS):.2f}）\n")
    for w, want, got, s, mg, good in rows:
        mark = "✓" if good else "✗"
        print(f"  {mark} {w:<12} → {got:<6} (近さ {s:.3f} 差 {mg:+.3f})"
              + ("" if good else f"  ほしい: {want}"))

    # 比べる相手
    from cards_unified import UnifiedCards
    u = UnifiedCards()
    ok2, t1 = 0, time.time()
    for w, want in TESTS:
        b, s, _ = u.nearest(w, list(EXAMPLES))
        ok2 += (b == want)
    ms2 = (time.time() - t1) * 1000
    print(f"\n■ いまの表引き（小数のかけ算）")
    print(f"  正解: {ok2}/{len(TESTS)}  （{ok2/len(TESTS)*100:.0f}%）")
    print(f"  時間: {ms2:.0f} ミリ秒 （1件 {ms2/len(TESTS):.2f}）")


if __name__ == "__main__":
    main()
