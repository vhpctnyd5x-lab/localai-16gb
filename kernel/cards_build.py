#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""単語カード生成器 (cards_build.py)

設計思想: 掛け算(ニューラルネットの行列積)を一切使わない。
共起回数を「数えるだけ」で、言葉のブレを吸収する疎ベクトル(単語カード)を作る。
分布仮説に基づくカウントベース意味表現。GPU不要・学習不要。

- Python 3.14 標準ライブラリのみ (numpy 等の外部ライブラリは使わない)
- 形態素解析器は使わない。日本語は文字N-gram(2〜4文字)、英数字は単語単位
- メモリ16GBのIntel Macでも動くよう、逐次読み込み + 定期的な枝刈りで抑える
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import unicodedata
from collections import Counter, defaultdict

# ----------------------------------------------------------------------
# 設定値
# ----------------------------------------------------------------------

# 対象とする拡張子
TEXT_EXTS = (".txt", ".md")

# 日本語N-gramの長さ範囲
NGRAM_MIN = 2
NGRAM_MAX = 4

# ペア表が肥大化したときに枝刈りを始める閾値(メモリ保護)
MAX_PAIRS = 6_000_000

# 1行あたりに切り出すトークン数の上限(異常に長い行への保険)
MAX_SPANS_PER_LINE = 200_000


# ----------------------------------------------------------------------
# トークナイズ
# ----------------------------------------------------------------------

def _is_word_char(ch: str) -> bool:
    """英数字(ASCII語を構成する文字)かどうか。"""
    return ch.isascii() and (ch.isalnum() or ch == "_")


def _is_hiragana(ch: str) -> bool:
    """ひらがなかどうか(1文字語として採らないため)。"""
    return "ぁ" <= ch <= "ゟ"


def _is_jp_char(ch: str) -> bool:
    """日本語として N-gram 対象にする文字かどうか。

    ひらがな・カタカナ・漢字・全角英数などの「文字」を対象にし、
    句読点や記号・空白は区切りとして扱う。
    """
    if ch.isspace():
        return False
    if ch.isascii():
        return False
    cat = unicodedata.category(ch)
    # L*(文字) と Nd(数字) のみ通す。P*(記号) M* S* は区切り扱い。
    return cat.startswith("L") or cat == "Nd"


def spans(text: str):
    """テキストから (開始位置, 終了位置, 語) のリストを作る。

    - 英数字の連続 → 1語(小文字化)
    - 日本語文字の連続 → その中の 2〜4 文字のN-gramを全位置で切り出す

    位置情報を持たせるのは、共起を「文字距離」で測り、かつ
    重なり合うN-gram同士を共起としてカウントしないためである。
    """
    out = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if _is_word_char(ch):
            j = i
            while j < n and _is_word_char(text[j]):
                j += 1
            out.append((i, j, text[i:j].lower()))
            i = j
        elif _is_jp_char(ch):
            j = i
            while j < n and _is_jp_char(text[j]):
                j += 1
            seg = text[i:j]
            seg_len = j - i
            for k in range(seg_len):
                # 1文字語: ひらがな1文字は助詞などノイズになるので除外し、
                # 漢字・カタカナ・全角英数の1文字だけ語として認める
                # (「猫」「犬」「石」「川」など1文字語を拾うために必要)
                if not _is_hiragana(seg[k]):
                    out.append((i + k, i + k + 1, seg[k]))
                for L in range(NGRAM_MIN, NGRAM_MAX + 1):
                    if k + L > seg_len:
                        break
                    out.append((i + k, i + k + L, seg[k:k + L]))
            i = j
        else:
            i += 1
        if len(out) > MAX_SPANS_PER_LINE:
            break
    return out


# ----------------------------------------------------------------------
# 入力ファイルの収集
# ----------------------------------------------------------------------

def iter_files(paths):
    """パス(ファイル or ディレクトリ)のリストから対象ファイルを再帰的に列挙。"""
    seen = set()
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for f in sorted(files):
                    if f.lower().endswith(TEXT_EXTS):
                        fp = os.path.join(root, f)
                        if fp not in seen:
                            seen.add(fp)
                            yield fp
        elif os.path.isfile(p):
            if p not in seen:
                seen.add(p)
                yield p


def iter_lines(paths):
    """全対象ファイルの行を逐次返す(メモリに全文を載せない)。"""
    for fp in iter_files(paths):
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        yield line
        except OSError as e:
            print(f"[warn] 読めません: {fp}: {e}", file=sys.stderr)


# ----------------------------------------------------------------------
# 本体: 共起カウント → PPMI → 上位top_k
# ----------------------------------------------------------------------

def build(corpus_paths, out_path="cards.json", window=4, min_count=3, top_k=150) -> dict:
    """コーパスから単語カード(PPMI疎ベクトル)を作り JSON に保存する。

    corpus_paths : テキストファイル or ディレクトリのリスト(.txt .md を再帰探索)
    out_path     : 保存先 JSON
    window       : 共起とみなす文字距離(語のスパン間の隙間がこの文字数以内)
    min_count    : この回数未満しか出ない語は捨てる
    top_k        : 1語あたり残す共起相手の数(疎ベクトルの次元)

    戻り値は保存した辞書そのもの。
    """
    t0 = time.time()

    # --- パス1: 語の出現回数を数える ------------------------------------
    uni = Counter()
    n_lines = 0
    n_chars = 0
    for line in iter_lines(corpus_paths):
        n_lines += 1
        n_chars += len(line)
        for _, _, w in spans(line):
            uni[w] += 1

    # min_count 未満を捨てる(ここで語彙がぐっと減る)
    vocab = {w: c for w, c in uni.items() if c >= min_count}
    del uni

    if not vocab:
        raise ValueError("語彙が空です。コーパスが小さすぎるか min_count が大きすぎます。")

    # --- パス2: 共起回数を数える ----------------------------------------
    # pair[(a, b)] = 回数 (a < b の順に正規化して1回だけ持つ)
    pair = Counter()
    ctx_total = Counter()   # 共起カウント上の各語の周辺度数
    total_pairs = 0

    for line in iter_lines(corpus_paths):
        sp = [(s, e, w) for (s, e, w) in spans(line) if w in vocab]
        m = len(sp)
        for i in range(m):
            si, ei, wi = sp[i]
            for j in range(i + 1, m):
                sj, ej, wj = sp[j]
                # 位置は開始位置の昇順ではないので、隙間は絶対値で見る
                if sj - ei > window:
                    # 開始位置が単調非減少なので、これ以降はさらに遠い
                    if sj - ei > window + NGRAM_MAX:
                        break
                    continue
                # スパンが1文字でも重なるN-gram同士は共起にしない
                if sj < ei and ej > si:
                    continue
                if wi == wj:
                    continue
                key = (wi, wj) if wi < wj else (wj, wi)
                pair[key] += 1
                ctx_total[wi] += 1
                ctx_total[wj] += 1
                total_pairs += 1

        # メモリ保護: 大きくなりすぎたら回数1のペアを捨てる
        if len(pair) > MAX_PAIRS:
            pair = Counter({k: v for k, v in pair.items() if v > 1})

    if total_pairs == 0:
        raise ValueError("共起が1件も取れませんでした。window を広げてください。")

    # --- PPMI 化 ---------------------------------------------------------
    # PMI(a,b) = log2( P(a,b) / (P(a) * P(b)) )
    #          = log2( c(a,b) * N / (c(a) * c(b)) )   ※ N は共起総数(片側基準)
    # 負の値は 0 に切る(PPMI)。
    N = float(total_pairs * 2)  # ctx_total は1ペアにつき両側を数えているため
    vecs_raw = defaultdict(list)
    for (a, b), c in pair.items():
        if c < min_count and c < 2:
            continue
        ca = ctx_total.get(a, 0)
        cb = ctx_total.get(b, 0)
        if ca == 0 or cb == 0:
            continue
        # 掛け算は使うが行列積ではない。ここは素直に確率比を対数で取る。
        pmi = math.log2((c * N) / (ca * cb))
        if pmi <= 0.0:
            continue
        vecs_raw[a].append((b, pmi))
        vecs_raw[b].append((a, pmi))

    del pair

    # --- 上位 top_k だけ残す --------------------------------------------
    vecs = {}
    for w, items in vecs_raw.items():
        items.sort(key=lambda kv: kv[1], reverse=True)
        vecs[w] = {k: round(v, 4) for k, v in items[:top_k]}

    elapsed = time.time() - t0
    data = {
        "meta": {
            "version": 1,
            "window": window,
            "min_count": min_count,
            "top_k": top_k,
            "ngram": [NGRAM_MIN, NGRAM_MAX],
            "n_lines": n_lines,
            "n_chars": n_chars,
            "vocab_size": len(vecs),
            "total_pairs": total_pairs,
            "build_seconds": round(elapsed, 3),
        },
        "vecs": vecs,
    }

    if out_path:
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, out_path)

    return data


# ----------------------------------------------------------------------
# 使う側
# ----------------------------------------------------------------------

def _bigrams(s: str) -> set:
    """文字bigram集合(未知語のフォールバック照合用)。"""
    if not s:
        return set()
    # 前後に境界記号を付ける。こうしないと1文字語(「猫」)の bigram 集合が
    # 「子猫」などと一切重ならず、フォールバックが機能しない。
    t = "" + s + ""
    return {t[i:i + 2] for i in range(len(t) - 1)}


class Cards:
    """生成済みカードを読み込んで、語の近さを測るためのクラス。"""

    def __init__(self, vecs: dict, meta: dict | None = None):
        self.vecs = vecs
        self.meta = meta or {}
        # 疎ベクトルのノルムを前計算(コサイン類似度の分母)
        self._norm = {w: math.sqrt(sum(v * v for v in d.values())) or 1.0
                      for w, d in vecs.items()}
        # 未知語フォールバック用の bigram インデックス
        self._bi_index = None

    # -- 読み込み --------------------------------------------------------
    @classmethod
    def load(cls, path) -> "Cards":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(data.get("vecs", {}), data.get("meta", {}))

    # -- 未知語の解決 ----------------------------------------------------
    def _build_bi_index(self):
        idx = defaultdict(list)
        for w in self.vecs:
            for bg in _bigrams(w):
                idx[bg].append(w)
        self._bi_index = idx

    def resolve(self, word: str) -> str | None:
        """語彙に無い語を、文字bigramのJaccard係数が最大の既知語に寄せる。"""
        if word in self.vecs:
            return word
        if not word:
            return None
        if self._bi_index is None:
            self._build_bi_index()
        qb = _bigrams(word)
        # 候補を bigram インデックスで絞る(全語走査を避ける)
        cand = Counter()
        for bg in qb:
            for w in self._bi_index.get(bg, ()):
                cand[w] += 1
        best, best_s = None, 0.0
        for w, common in cand.items():
            wb = _bigrams(w)
            union = len(qb) + len(wb) - common
            if union <= 0:
                continue
            s = common / union
            if s > best_s:
                best, best_s = w, s
        return best

    # -- 類似度 ----------------------------------------------------------
    def _vec(self, word: str):
        w = self.resolve(word)
        if w is None:
            return None, None
        return self.vecs[w], self._norm[w]

    def similarity(self, a: str, b: str) -> float:
        """疎ベクトルのコサイン類似度。共通キーだけを足し合わせる。"""
        va, na = self._vec(a)
        vb, nb = self._vec(b)
        if va is None or vb is None:
            return 0.0
        # 小さい方を走査して共通キーだけ計算する
        if len(va) > len(vb):
            va, vb = vb, va
        dot = 0.0
        get = vb.get
        for k, x in va.items():
            y = get(k)
            if y is not None:
                dot += x * y
        if dot <= 0.0:
            return 0.0
        return dot / (na * nb)

    def nearest(self, word: str, candidates: list, threshold: float = 0.15):
        """候補リストの中から最も意味の近いものを返す。(候補, スコア)。"""
        best, best_s = None, 0.0
        for c in candidates:
            s = self.similarity(word, c)
            if s > best_s:
                best, best_s = c, s
        if best is None or best_s < threshold:
            return (None, 0.0)
        return (best, best_s)

    def neighbors(self, word: str, n: int = 10) -> list:
        """意味の近い語トップn(確認・デバッグ用)。[(語, スコア), ...]"""
        w = self.resolve(word)
        if w is None:
            return []
        vw = self.vecs[w]
        nw = self._norm[w]
        # 共通キーを持ちうる語だけを転置的に集める(全語走査を避ける)
        cands = set()
        for k in vw:
            kv = self.vecs.get(k)
            if kv:
                cands.update(kv.keys())
        cands.discard(w)
        out = []
        for c in cands:
            vc = self.vecs.get(c)
            if not vc:
                continue
            small, large = (vw, vc) if len(vw) <= len(vc) else (vc, vw)
            dot = 0.0
            get = large.get
            for k, x in small.items():
                y = get(k)
                if y is not None:
                    dot += x * y
            if dot > 0.0:
                out.append((c, dot / (nw * self._norm[c])))
        out.sort(key=lambda kv: kv[1], reverse=True)
        return out[:n]


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="共起カウントだけで単語カードを作る")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="コーパスからカードを生成")
    p_build.add_argument("paths", nargs="+", help="テキストファイル/ディレクトリ")
    p_build.add_argument("--out", default="cards.json")
    p_build.add_argument("--window", type=int, default=4)
    p_build.add_argument("--min-count", type=int, default=3)
    p_build.add_argument("--top-k", type=int, default=150)

    p_near = sub.add_parser("near", help="意味の近い語を表示")
    p_near.add_argument("word")
    p_near.add_argument("--cards", default="cards.json")
    p_near.add_argument("-n", type=int, default=10)

    p_sim = sub.add_parser("sim", help="2語の類似度")
    p_sim.add_argument("a")
    p_sim.add_argument("b")
    p_sim.add_argument("--cards", default="cards.json")

    args = ap.parse_args(argv)

    if args.cmd == "build":
        data = build(args.paths, out_path=args.out, window=args.window,
                     min_count=args.min_count, top_k=args.top_k)
        m = data["meta"]
        size = os.path.getsize(args.out) if os.path.exists(args.out) else 0
        print(f"語彙数 {m['vocab_size']} / 共起 {m['total_pairs']} / "
              f"{m['build_seconds']}秒 / {size:,} バイト -> {args.out}")
        return 0

    if args.cmd == "near":
        cards = Cards.load(args.cards)
        w = cards.resolve(args.word)
        if w is None:
            print("語彙にありません")
            return 1
        if w != args.word:
            print(f"(未知語のため『{w}』として扱います)")
        for word, score in cards.neighbors(w, args.n):
            print(f"{score:.4f}\t{word}")
        return 0

    if args.cmd == "sim":
        cards = Cards.load(args.cards)
        print(f"{cards.similarity(args.a, args.b):.4f}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
