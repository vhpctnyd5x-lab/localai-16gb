#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bake_raw.py -- 次元を落とさずに焼く

  次元圧縮（射影）は、掛け算を減らすためにやっていたが、
  実測で意味の差が潰れることが分かった。
  そこで圧縮はやめ、int8 に量子化するだけにする。

    ・品質の損失は量子化ぶんだけ（ごくわずか）
    ・大きさは 1/2（BF16 → int8）
    ・全部をメモリに載せず、必要な行だけ mmap で読む
"""
import os, json, math, time, re, sys
from embed_cards import EmbedCards

HERE = os.path.dirname(os.path.abspath(__file__))


def bake(tag, tokfile, tok_kind, out, pattern=None, report=4000):
    e = EmbedCards(tag=tag, tokfile=tokfile, tok_kind=tok_kind)
    inv = {}
    for b, i in e.vocab.items():
        try: inv[i] = b.decode("utf-8")
        except Exception: pass
    targets = []
    for tid, w in inv.items():
        w = w.replace("▁", "")
        if len(w) < 2: continue
        if pattern and not pattern.search(w): continue
        targets.append((tid, w))
    print(f"  対象 {len(targets)} 語 × {e.dim} 次元", flush=True)

    idx, seen, t0 = {}, set(), time.time()
    with open(out + ".bin", "wb") as f:
        for n, (tid, w) in enumerate(targets, 1):
            if w in seen: continue
            v = e.row(tid)
            if not v: continue
            nrm = math.sqrt(sum(x * x for x in v)) or 1.0
            f.write(bytes(max(0, min(255, int(round(x / nrm * 127)) + 128)) for x in v))
            idx[w] = len(seen); seen.add(w)
            if n % report == 0:
                el = time.time() - t0
                print(f"  {n}/{len(targets)}  ({el:.0f}秒, 残り約{el/n*(len(targets)-n):.0f}秒)",
                      flush=True)
    json.dump({"meta": {"source": tag, "dim": e.dim, "quant": "int8",
                        "count": len(idx)}, "index": idx},
              open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  → {len(idx)}語  索引{os.path.getsize(out)/1e6:.1f}MB "
          f"+ 本体{os.path.getsize(out+'.bin')/1e6:.0f}MB  ({time.time()-t0:.0f}秒)", flush=True)


if __name__ == "__main__":
    JP = re.compile(r"[ぁ-んァ-ヴー一-龥]")
    bake("llm-jp-3-13b", "llmjp.tokenizer.json", "unigram",
         os.path.join(HERE, "jp_cards.json"), pattern=JP)
