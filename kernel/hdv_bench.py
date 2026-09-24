#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hdv_bench.py -- 掛け算する表引き vs 掛け算しない1万ビット

  同じ問題を同じ条件で解かせて、正解率・速さ・掛け算の回数を比べる。
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv

KINDS = ["画像", "PDF", "動画", "テキスト", "音楽", "書類", "圧縮"]

# 人が実際に言いそうな語 → 正解
CASES = [
    ("写真", "画像"), ("スナップ", "画像"), ("フォト", "画像"),
    ("イラスト", "画像"), ("スクリーンショット", "画像"), ("撮影", "画像"),
    ("動画", "動画"), ("ムービー", "動画"), ("映像", "動画"),
    ("ビデオ", "動画"), ("録画", "動画"),
    ("資料", "PDF"), ("論文", "PDF"), ("報告書", "書類"),
    ("契約書", "書類"), ("請求書", "書類"), ("履歴書", "書類"),
    ("メモ", "テキスト"), ("覚書", "テキスト"), ("下書き", "テキスト"),
    ("楽曲", "音楽"), ("音源", "音楽"), ("演奏", "音楽"),
    ("録音", "音楽"), ("歌", "音楽"),
    ("圧縮", "圧縮"), ("アーカイブ", "圧縮"),
]


def run(name, pick, warm=None):
    if warm:
        warm()
    ok, t0, rows = 0, time.time(), []
    for w, want in CASES:
        got, score, margin = pick(w)
        good = (got == want)
        ok += good
        rows.append((w, want, got, score, margin, good))
    ms = (time.time() - t0) * 1000
    print(f"\n■ {name}")
    print(f"  正解: {ok}/{len(CASES)}  （{ok/len(CASES)*100:.0f}%）")
    print(f"  時間: {ms:.0f} ミリ秒  （1件 {ms/len(CASES):.2f}）")
    bad = [r for r in rows if not r[5]]
    if bad:
        print("  外したもの:")
        for w, want, got, sc, mg, _ in bad[:10]:
            print(f"    {w:<12} ほしい {want:<6} 出た {got or '—':<6}"
                  f" (近さ {sc:.3f} 差 {mg:+.3f})")
    return ok, ms, rows


def main():
    # --- いまのやり方（小数のかけ算） ---
    from cards_unified import UnifiedCards
    u = UnifiedCards()

    def pick_old(w):
        b, s, _src = u.nearest(w, KINDS)
        return b, s, 0.0

    a = run("いまの表引き（小数のかけ算）", pick_old)

    # --- 1万ビット（かけ算ゼロ） ---
    sp = hdv.Space().load(os.path.join(os.path.dirname(__file__),
                                       "hdv_space.bin"))
    print(f"\n  （覚えている語: {len(sp.mem):,}）")

    def pick_hdv(w):
        return sp.nearest(w, KINDS)

    b = run("1万ビット（かけ算 0回）", pick_hdv)

    print("\n" + "=" * 56)
    print(f"  正解率 : {a[0]}/{len(CASES)}  →  {b[0]}/{len(CASES)}")
    print(f"  速さ   : {a[1]:.0f} ms  →  {b[1]:.0f} ms")
    print(f"  大きさ : 137 MB  →  {os.path.getsize('hdv_space.bin')/1e6:.0f} MB")
    print(f"  かけ算 : 何百万回  →  0 回")


if __name__ == "__main__":
    main()
