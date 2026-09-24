#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bake.py -- 抜いた表を「焼く」

  巨大な表(2.35GB, 7168次元)から必要な語だけ取り出し、
  次元を落として小さな表にする。以後は掛け算がほぼゼロになる。

  ・次元削減はランダム射影（決定的な種を使う）。
    Johnson–Lindenstrauss の定理より、内積・角度はおおむね保たれる。
  ・「1トークンで引ける語」だけを焼く。分割される語は表が壊れるため除外し、
    その事実を印として残す（呼び出し側が別の手段に切り替えられるように）
"""
import os, json, math, random, time, sys
from embed_cards import EmbedCards

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "baked_cards.json")


def projection(dim_in, dim_out, seed=20260823):
    """決定的なランダム射影行列。列ごとに生成してメモリを節約"""
    rng = random.Random(seed)
    s = 1.0 / math.sqrt(dim_out)
    return [[rng.gauss(0, 1) * s for _ in range(dim_in)] for _ in range(dim_out)]


def bake(words, tag="Kimi-K2-Instruct", dim_out=256, verbose=True):
    e = EmbedCards(tag=tag)
    P = projection(e.dim, dim_out)
    baked, skipped = {}, []
    t0 = time.time()
    for w in words:
        ids = e.encode(w)
        if len(ids) != 1:                 # 1トークンで引けない語は焼かない
            skipped.append((w, len(ids)))
            continue
        v = e.row(ids[0])
        small = [sum(p[i] * v[i] for i in range(e.dim)) for p in P]
        n = math.sqrt(sum(x * x for x in small)) or 1.0
        baked[w] = [round(x / n, 5) for x in small]   # 正規化して丸める
    if verbose:
        print(f"  焼けた: {len(baked)} 語 / 除外: {len(skipped)} 語  "
              f"({time.time()-t0:.1f}秒)")
    return baked, skipped


class Baked:
    """焼いた表。読み込みは一瞬、比較は256次元だけ"""
    def __init__(self, path=OUT):
        d = json.load(open(path, encoding="utf-8"))
        self.v = d["vecs"]; self.meta = d["meta"]

    def has(self, w):  return w in self.v

    def similarity(self, a, b):
        va, vb = self.v.get(a), self.v.get(b)
        if not va or not vb: return None          # 引けない＝別の手段へ
        return sum(x * y for x, y in zip(va, vb)) # すでに正規化済み

    def nearest(self, w, candidates):
        va = self.v.get(w)
        if not va: return None, 0.0
        best, sc = None, -2.0
        for c in candidates:
            vb = self.v.get(c)
            if not vb: continue
            s = sum(x * y for x, y in zip(va, vb))
            if s > sc: best, sc = c, s
        return best, sc


if __name__ == "__main__":
    import kernel
    # 焼く対象＝エンジンが知っている語＋概念の値＋動作でよく使う語
    words = set(kernel.SEED.keys())
    for slot, vals in kernel.vocab_table().items():
        words.update(vals)
    words.update(["猫","犬","石","川","橋","箸","写真","画像","動画","音楽",
                  "移動","削除","整理","複製","検索","一覧","合計","重複",
                  "書類","資料","保存","作成","変更","確認"])
    words = sorted(w for w in words if w)
    print(f"■ 焼く語: {len(words)} 語")
    baked, skipped = bake(words)
    json.dump({"meta": {"source": "Kimi-K2-Instruct", "dim": 256,
                        "skipped": skipped}, "vecs": baked},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  → {OUT}  ({os.path.getsize(OUT)/1e6:.1f} MB)")
