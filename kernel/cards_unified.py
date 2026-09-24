#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cards_unified.py -- 複数のカード表を束ねて引く

  実測から分かったこと:
    ・巨大モデル(Kimi K2)の表は、日本語のかな語が 285 語しか無く役に立たない
    ・日本製モデル(llm-jp)の表は、かな語が 21981 語あり日本語に強い
    ・自分で数えたカードは、語彙を無制限に増やせる（材料しだい）
    ・どれも引けない語は、文字の重なりで一番近い既知語に寄せる

  そこで、上から順に試して、最初に自信のある答えが出た表を採用する。
"""
import os, json, functools

HERE = os.path.dirname(os.path.abspath(__file__))


class UnifiedCards:
    # 2位との差の下限。実測で入力埋め込みの差は 0.01〜0.06 に収まるため、
    # 「決めてよい差」はスロットの危なさで変える
    MARGIN = 0.025

    def __init__(self, verbose=False):
        self.srcs = []          # (名前, 引く関数, 採用の閾値)
        self._load_dict()
        self._load_mm("jp_cards.json", "日本語の大表", 0.10)
        self._load_baked("llm-jp-3-13b", "日本製モデルの表", 0.15)
        self._load_baked("Kimi-K2-Instruct", "巨大モデルの表", 0.15)
        # ★ 数えたカードは、いまは作り物の小コーパス製で語彙が断片だらけ。
        #   概念の判定に使うと誤答するので、本物の材料で作り直すまで外す。
        if os.environ.get("USE_COUNTED_CARDS"):
            self._load_counted()
        if verbose:
            for n, _, th in self.srcs:
                print(f"  使える表: {n}（閾値 {th}）")

    # ---- 焼いた表 ----
    def _load_baked(self, tag, label, th):
        p = os.path.join(HERE, f"baked_{tag}.json")
        if not os.path.exists(p):
            return
        d = json.load(open(p, encoding="utf-8"))
        v = d["vecs"]

        def look(word, cands):
            a = v.get(word)
            if not a:
                return None, 0.0, 0.0
            ss = []
            for c in cands:
                b = v.get(c)
                if b:
                    ss.append((sum(x * y for x, y in zip(a, b)), c))
            if not ss:
                return None, 0.0, 0.0
            ss.sort(reverse=True)
            # 2位との差。差が小さい＝どれとも似ている＝判断できない
            margin = ss[0][0] - ss[1][0] if len(ss) > 1 else ss[0][0]
            return ss[0][1], ss[0][0], margin
        self.srcs.append((f"{label}({len(v)}語)", look, th))

    # ---- 辞書から数えた表（一番あてになるが、自信がある時しか答えない）----
    def _load_dict(self):
        p = os.path.join(HERE, "dict_cards.json")
        if not os.path.exists(p):
            return
        try:
            from dict_cards import DictCards
            d = DictCards(p)
        except Exception:
            return

        def look(word, cands):
            b, s, mg = d.nearest(word, list(cands))
            # 実測：正解は 0.14 以上、誤りは 0.05 以下にきれいに分かれた。
            # 迷うくらいなら答えない
            if b is None or s < 0.10 or mg < 0.05:
                return None, 0.0, 0.0
            return b, s, mg
        self.srcs.insert(0, (f"辞書から数えた表({len(d.v)}語)", look, 0.10))

    # ---- 大表（次元を落とさず int8。必要な行だけ mmap で読む）----
    def _load_mm(self, name, label, th):
        import mmap
        idxp = os.path.join(HERE, name)
        binp = idxp + ".bin"
        if not (os.path.exists(idxp) and os.path.exists(binp)):
            return
        meta = json.load(open(idxp, encoding="utf-8"))
        idx, dim = meta["index"], meta["meta"]["dim"]
        f = open(binp, "rb")
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        cache = {}

        def row(w):
            if w in cache:
                return cache[w]
            i = idx.get(w)
            r = None if i is None else mm[i * dim:(i + 1) * dim]
            if len(cache) < 4000:
                cache[w] = r
            return r

        def look(word, cands):
            a = row(word)
            if a is None:
                return None, 0.0, 0.0
            ss = []
            for c in cands:
                b = row(c)
                if b is None:
                    continue
                d = sum((x - 128) * (y - 128) for x, y in zip(a, b))
                ss.append((d / (127.0 * 127.0), c))
            if not ss:
                return None, 0.0, 0.0
            ss.sort(reverse=True)
            mg = ss[0][0] - ss[1][0] if len(ss) > 1 else ss[0][0]
            return ss[0][1], ss[0][0], mg
        self.srcs.append((f"{label}({len(idx)}語)", look, th))

    # ---- 圧縮した表（旧方式。残してあるが既定では使わない）----
    def _load_big(self, name, label, th):
        idxp = os.path.join(HERE, name)
        binp = idxp + ".bin"
        if not (os.path.exists(idxp) and os.path.exists(binp)):
            return
        meta = json.load(open(idxp, encoding="utf-8"))
        idx, dim = meta["index"], meta["meta"]["dim"]
        blob = open(binp, "rb").read()

        def row(w):
            i = idx.get(w)
            return None if i is None else blob[i * dim:(i + 1) * dim]

        def look(word, cands):
            a = row(word)
            if a is None:
                return None, 0.0, 0.0
            ss = []
            for c in cands:
                b = row(c)
                if b is None:
                    continue
                d = sum((x - 128) * (y - 128) for x, y in zip(a, b))
                ss.append((d / (127.0 * 127.0), c))
            if not ss:
                return None, 0.0, 0.0
            ss.sort(reverse=True)
            mg = ss[0][0] - ss[1][0] if len(ss) > 1 else ss[0][0]
            return ss[0][1], ss[0][0], mg
        self.srcs.append((f"{label}({len(idx)}語)", look, th))

    # ---- 数えたカード ----
    def _load_counted(self):
        p = os.path.join(HERE, "cards.json")
        if not os.path.exists(p):
            return
        try:
            from cards_build import Cards
            c = Cards.load(p)
        except Exception:
            return

        vocab = set(getattr(c, "vecs", {}) or {})

        def look(word, cands):
            # 語彙に無い語を強引に寄せると誤答するので、必ず実在を確かめる
            if word not in vocab:
                return None, 0.0, 0.0
            try:
                return c.nearest(word, cands, threshold=0.0)
            except Exception:
                return None, 0.0
        self.srcs.append((f"数えたカード({len(vocab)}語)", look, 0.35))

    # ---- 文字の重なり（最後の砦） ----
    @staticmethod
    def _bigrams(s):
        s = "\x02" + s.lower() + "\x03"
        return set(s[i:i+2] for i in range(len(s)-1))

    def _overlap(self, word, cands):
        A = self._bigrams(word)
        best, sc = None, 0.0
        for c in cands:
            B = self._bigrams(c)
            s = len(A & B) / len(A | B) if (A | B) else 0.0
            if s > sc:
                best, sc = c, s
        return best, sc

    # ---- 公開: 一番近い候補を返す ----
    @functools.lru_cache(maxsize=4096)
    def _resolve(self, word, cands_key):
        cands = cands_key.split("\x00")
        for name, look, th in self.srcs:
            try:
                r = look(word, cands)
            except Exception:
                continue
            b, s, mg = r if len(r) == 3 else (r[0], r[1], r[1])
            # 1位であること、かつ2位を明確に引き離していること
            if b is not None and s >= th and mg >= self.MARGIN:
                return b, round(s, 4), f"{name} 差{mg:+.3f}"
        b, s = self._overlap(word, cands)
        return (b, round(s, 4), "文字の重なり") if s >= 0.45 else (None, 0.0, "なし")

    def nearest(self, word, candidates):
        """戻り値: (一番近い候補, 近さ, どの表が答えたか)"""
        return self._resolve(word, "\x00".join(candidates))

    def hints(self, word, candidates, n=3):
        """決めずに、上位候補だけ返す。先生に渡すヒント用"""
        for name, look, _ in self.srcs:
            try:
                r = look(word, list(candidates))
            except Exception:
                continue
            if r[0] is None:
                continue
            scored = []
            for c in candidates:
                b, s, _m = look(word, [c])
                if b: scored.append((round(s, 3), c))
            scored.sort(reverse=True)
            if scored:
                return [c for _s, c in scored[:n]], name
        return [], ""


if __name__ == "__main__":
    import sys, time
    u = UnifiedCards(verbose=True)
    tests = [("写真", ["画像", "動画", "テキスト", "PDF"]),
             ("スナップ", ["画像", "動画", "テキスト", "PDF"]),
             ("まとめて", ["移動", "数える", "一覧", "削除"]),
             ("片付けて", ["移動", "数える", "一覧", "削除"]),
             ("何個", ["移動", "数える", "一覧", "削除"]),
             ("机の上", ["Desktop", "Downloads", "Documents"]),
             ("書類入れ", ["Desktop", "Downloads", "Documents"])]
    print()
    t0 = time.time()
    for w, cs in tests:
        b, s, src = u.nearest(w, tuple(cs) if False else cs)
        print(f"  {w:8} → {str(b):10} ({s:+.3f})  [{src}]")
    print(f"\n  {len(tests)}件で {(time.time()-t0)*1000:.1f} ミリ秒")
