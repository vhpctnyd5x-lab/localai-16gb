#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pc_kind.py -- 知らない語が、どの種類のファイルの話かを見極める

  カードに無い語が来たとき、これまでは「抜いてきた表」に聞いていた。
  当たったのは 4/17（24%）。しかも近さが 0.51 で、
  でたらめに答えているのと変わらなかった。

  原因は、材料が辞書だったこと。
      辞書の「画像」     → 人物 / 洋風 / 弟子   （＝絵画の意味）
      Wikipediaの「壁紙」→ 建築物の内装仕上材   （＝建材の意味）
  どれも言葉としては正しいが、ファイルの話ではない。

  そこで材料を「パソコンの話の記事」だけに替えた（corpus_pc.py）。
  同じ測り方で 11/17（65%）。材料に載っている語だけなら 11/12（92%）。

  やり方（掛け算は1回も使わない）
  ────────────────────────────
    記事のすがた = その記事に出てくる語を たばねた 1万ビット
    種類の手本   = その種類の記事のすがたを たばねたもの
    語のすがた   = その語が出てくる記事のすがたを たばねたもの
    答え         = 手本のうち、いちばん近いもの（XOR して1を数えるだけ）
"""
import os, sys, functools

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hdv

# これ以下の近さ、これ以下の差なら「分からない」と答える。
# でたらめな2本は必ず 0.50 になるので、0.58 は偶然では出ない。
# 差（1位と2位の開き）も見るのは、2つの種類のあいだで
# 迷っているのに1位を答えてしまうのを防ぐため
MIN_NEAR   = 0.58
MIN_MARGIN = 0.03


class Guesser:
    def __init__(self, data):
        docs = data.get("記事ごとの語") or []
        self.docs = docs
        self.dvec = [self._doc_vec(d["語"]) for d in docs]
        self.proto = {}
        for k in sorted({d["種類"] for d in docs}):
            vs = [v for d, v in zip(docs, self.dvec) if d["種類"] == k]
            if vs:
                self.proto[k] = hdv.bundle_bits(vs)
        self.where = {}
        for i, d in enumerate(docs):
            for w, n in d["語"]:
                self.where.setdefault(w, []).append((i, min(n, 5)))

    @staticmethod
    def _doc_vec(words):
        vs = [hdv.atom(w) for w, _n in words]
        ws = [min(n, 5) for _w, n in words]
        return hdv.bundle_bits(vs, ws) if vs else 0

    def guess(self, word):
        """(種類, 近さ, 2位との差) を返す。分からなければ (None, 0, 0)"""
        hits = self.where.get(word)
        if not hits:
            # そのままの形で無くても、語の一部として載っていることがある
            # （「スナップ写真」の中の「写真」）
            hits = []
            for w, hs in self.where.items():
                if len(w) >= 2 and (w in word):
                    hits.extend(hs)
            if not hits:
                return None, 0.0, 0.0
        q = hdv.bundle_bits([self.dvec[i] for i, _n in hits],
                            [n for _i, n in hits])
        sc = sorted(((hdv.near(q, p), k) for k, p in self.proto.items()),
                    reverse=True)
        if not sc:
            return None, 0.0, 0.0
        near, kind = sc[0]
        margin = near - (sc[1][0] if len(sc) > 1 else 0.5)
        if near < MIN_NEAR or margin < MIN_MARGIN:
            return None, near, margin       # 迷っている。黙る
        return kind, near, margin

    def __len__(self):
        return len(self.where)


@functools.lru_cache(maxsize=1)
def _g():
    import corpus_pc
    data = corpus_pc.load()
    if not data or not data.get("記事ごとの語"):
        return None
    return Guesser(data)


def guess(word):
    """入口。材料が無ければ黙って (None,0,0)"""
    try:
        g = _g()
    except Exception:
        return None, 0.0, 0.0
    if g is None:
        return None, 0.0, 0.0
    return g.guess(word)


def ready():
    try:
        return _g() is not None
    except Exception:
        return False


# ------------------------------------------------------------------
# 採点
# ------------------------------------------------------------------
TESTS = [
    ("スナップ写真", "画像"), ("自撮り", "画像"), ("壁紙", "画像"),
    ("サムネイル", "画像"), ("挿絵", "画像"),
    ("映画", "動画"), ("実写", "動画"), ("アニメ", "動画"),
    ("契約書", "書類"), ("請求書", "書類"), ("報告書", "書類"),
    ("覚書", "テキスト"), ("下書き", "テキスト"), ("原稿", "テキスト"),
    ("楽曲", "音楽"), ("音源", "音楽"), ("歌詞", "音楽"),
]
# ファイルの種類とは、まったく関係のない語。
# ここで何か答えてしまうのがいちばん危ない。
# 前に作った grow_all.py は、宇宙飛行士→画像、醤油→PDF、へび→画像 と答えた。
# 「分からない」と言えることが、当てることと同じくらい大事
NONSENSE = ["みそ汁", "宇宙飛行士", "へび", "醤油", "校庭", "税金",
            "自転車", "台風", "友情"]


def score():
    g = _g()
    if g is None:
        print("  材料がありません。先に  python3 corpus_pc.py  を動かしてください")
        return
    print(f"  材料の語: {len(g):,} 個 / 種類: {', '.join(sorted(g.proto))}\n")

    print("■ ファイルの種類の語（当ててほしい）")
    ok = wrong = mute = 0
    for w, want in TESTS:
        k, n, m = guess(w)
        if k is None:
            mute += 1; mark = "－"
        elif k == want:
            ok += 1; mark = "✓"
        else:
            wrong += 1; mark = "✗"
        print(f"  {mark} {w:<12} → {k or '（分からない）':<10}"
              f" 近さ {n:.3f} 差 {m:+.3f}"
              + ("" if k == want or k is None else f"   ほしい: {want}"))

    print("\n■ 関係のない語（黙ってほしい）")
    ok2 = bad2 = 0
    for w in NONSENSE:
        k, n, m = guess(w)
        if k is None:
            ok2 += 1
            print(f"  ✓ {w:<12} → 分からない と言えた")
        else:
            bad2 += 1
            print(f"  ✗ {w:<12} → 【{k}】と言ってしまった（近さ {n:.3f}）")

    n1 = len(TESTS)
    print("\n" + "=" * 58)
    print(f"  当てた   : {ok}/{n1}   間違えた: {wrong}/{n1}   黙った: {mute}/{n1}")
    print(f"  関係ない語で黙れた: {ok2}/{len(NONSENSE)}   口を出した: {bad2}")
    print("\n  くらべる相手（同じ17語）")
    print("    前の材料（辞書）で1万ビット :  2/17  （12%）")
    print("    いままでの表引き（かけ算あり）:  4/17  （24%）")
    print("  ※ かけ算の回数: 0")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for w in sys.argv[1:]:
            k, n, m = guess(w)
            print(f"  {w:<14} → {k or '（分からない）':<10} 近さ {n:.3f} 差 {m:+.3f}")
    else:
        score()
