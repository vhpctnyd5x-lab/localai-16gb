#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
embed_cards.py -- 巨大モデルから抜いた「単語カードの表」を引く

  ★ 2.35GB をメモリに載せない。必要な行だけ seek して読む（＝表引き）
  ★ 掛け算は 2本のベクトルを比べる時だけ。層を通す推論は一切しない
"""
import os, json, base64, struct, functools

HERE  = os.path.dirname(os.path.abspath(__file__))
MINED = os.path.join(HERE, "mined")


class EmbedCards:
    def __init__(self, tag="Kimi-K2-Instruct", tokfile="kimi.tiktoken.model",
                 tok_kind="tiktoken"):
        meta = json.load(open(os.path.join(MINED, f"{tag}.embed.json")))
        self.bin   = os.path.join(MINED, f"{tag}.embed.bin")
        self.rows, self.dim = meta["shape"]
        self.dtype = meta["dtype"]
        assert self.dtype == "BF16", f"未対応の型: {self.dtype}"
        self.rowbytes = self.dim * 2
        self.f = open(self.bin, "rb")
        # トークナイザ： バイト列 → 番号
        self.kind = tok_kind
        self.vocab = {}
        path = os.path.join(MINED, tokfile)
        if tok_kind == "tiktoken":
            # tiktoken 形式（base64 と順位が1行ずつ）
            for line in open(path):
                b64, rank = line.split()
                self.vocab[base64.b64decode(b64)] = int(rank)
        elif tok_kind == "unigram":
            # SentencePiece Unigram（tokenizer.json）。並び順が番号
            d = json.load(open(path, encoding="utf-8"))
            for i, ent in enumerate(d["model"]["vocab"]):
                tok = ent[0] if isinstance(ent, list) else ent
                self.vocab[tok.encode("utf-8")] = i
        else:
            raise ValueError(f"未対応のトークナイザ: {tok_kind}")
        self.maxlen = max(len(k) for k in self.vocab)

    # ---- 表引き（ここが軽さの核心） ----
    @functools.lru_cache(maxsize=20000)
    def row(self, tid):
        """番号 tid の行を読む。ファイルの該当位置へ跳んで 14KB 読むだけ"""
        if not (0 <= tid < self.rows):
            return None
        self.f.seek(tid * self.rowbytes)
        raw = self.f.read(self.rowbytes)
        # BF16 は float32 の上位16ビット。下に0を足せば float32 になる
        n = self.dim
        u16 = struct.unpack(f"<{n}H", raw)
        f32 = struct.unpack(f"<{n}f", struct.pack(f"<{n}I", *(x << 16 for x in u16)))
        return f32

    # ---- 単語 → 番号の並び（最長一致） ----
    def encode(self, s):
        if self.kind == "unigram":
            # 語そのもの、または語頭印つきで引けるかを見る
            for cand in (s, "\u2581" + s):
                t = self.vocab.get(cand.encode("utf-8"))
                if t is not None:
                    return [t]
            return self._greedy(s)
        return self._greedy(s)

    def _greedy(self, s):
        b, out, i = s.encode("utf-8"), [], 0
        while i < len(b):
            for L in range(min(self.maxlen, len(b) - i), 0, -1):
                t = self.vocab.get(b[i:i + L])
                if t is not None:
                    out.append(t); i += L; break
            else:
                i += 1                      # どうしても引けないバイトは飛ばす
        return out

    # ---- 単語のベクトル（複数トークンなら平均） ----
    def vec(self, word):
        ids = self.encode(word)
        if not ids:
            return None
        vs = [self.row(t) for t in ids]
        vs = [v for v in vs if v]
        if not vs:
            return None
        n = self.dim
        return [sum(v[i] for v in vs) / len(vs) for i in range(n)]

    # ---- 近さ ----
    @staticmethod
    def cos(a, b):
        d = sa = sb = 0.0
        for x, y in zip(a, b):
            d += x * y; sa += x * x; sb += y * y
        return d / ((sa ** .5) * (sb ** .5)) if sa and sb else 0.0

    def similarity(self, a, b):
        va, vb = self.vec(a), self.vec(b)
        return self.cos(va, vb) if va and vb else 0.0

    def nearest(self, word, candidates, threshold=0.0):
        v = self.vec(word)
        if not v:
            return None, 0.0
        best, sc = None, -1.0
        for c in candidates:
            vc = self.vec(c)
            if not vc:
                continue
            s = self.cos(v, vc)
            if s > sc:
                best, sc = c, s
        return (best, sc) if sc >= threshold else (None, 0.0)


if __name__ == "__main__":
    import sys, time
    e = EmbedCards()
    print(f"表: {e.rows} 語 × {e.dim} 次元  ({os.path.getsize(e.bin)/1e9:.2f} GB)")
    if len(sys.argv) > 2:
        t0 = time.time()
        print(f"{e.similarity(sys.argv[1], sys.argv[2]):.4f}  ({(time.time()-t0)*1000:.1f} ms)")
    else:
        pairs = [("猫","犬"),("猫","石"),("写真","画像"),("写真","石"),
                 ("まとめて","移動"),("まとめて","削除"),("片付ける","整理"),
                 ("デスクトップ","Desktop"),("机の上","デスクトップ")]
        t0 = time.time()
        for a, b in pairs:
            print(f"  {a:8} - {b:8} : {e.similarity(a,b):+.4f}")
        print(f"\n  {len(pairs)}組で {(time.time()-t0)*1000:.0f} ミリ秒")
