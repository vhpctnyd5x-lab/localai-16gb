#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hdv_build.py -- 辞書から「意味の1万ビット」を作る

  材料は2つ。どちらも手元にある。
    ・辞書の説明文（108,332語）
    ・裏の係が辿ったつながり（bg_web.json）

  作り方は「たばねる」だけ。掛け算は1回も使わない。
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv, lookup

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "hdv_space.bin")


def main(limit=None):
    t0 = time.time()
    sp = hdv.Space()
    d = lookup.Dict()

    web = {}
    p = os.path.join(HERE, "bg_web.json")
    if os.path.exists(p):
        web = json.load(open(p, encoding="utf-8"))
    print(f"つながり: {len(web):,} 語ぶん")

    words = list(web) if web else list(d.idx)[:20000]
    if limit:
        words = words[:limit]
    print(f"作る語  : {len(words):,}")

    n = 0
    for w in words:
        ctx = web.get(w) or []
        if not ctx:
            try:
                ctx = d.links(w, 8)
            except Exception:
                ctx = []
        if not ctx:
            continue
        sp.learn(w, ctx)
        n += 1
        if n % 5000 == 0:
            print(f"  {n:,} 語 … {time.time()-t0:.0f}秒")

    sp.save(OUT)
    mb = os.path.getsize(OUT) / 1e6
    print(f"\n覚えた語: {n:,}")
    print(f"ファイル: {mb:.1f} MB  （{OUT}）")
    print(f"時間    : {time.time()-t0:.1f} 秒")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
