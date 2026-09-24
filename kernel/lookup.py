#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lookup.py -- 手元の辞書を引く。そして辿る。

  「あ」を引く → 説明に「かな」が出てくる → 「かな」を引く → …
  これを何段でも繰り返せる。＝「無限に辿る」の実装。

  ネットは使わない（一度ダンプを落としたので、以後ずっと手元で完結する）。
  引くのは索引を見て該当位置へ跳ぶだけ。掛け算ゼロ、1ミリ秒以下。

  使い方:
    python3 lookup.py あ                 引く
    python3 lookup.py あ --walk 3        3段辿る
    python3 lookup.py --index            索引を作り直す
"""
import os, sys, json, time, argparse, re

HERE  = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(HERE, "dict", "pages.jsonl")
INDEX = os.path.join(HERE, "dict", "index.json")

JP = re.compile(r"[ぁ-んァ-ヴー一-龥]")
# 中身のある語だけ辿る。助詞・機能語を辿ると意味の網にならない
CONTENT = re.compile(r"[ァ-ヴ一-龥A-Za-z0-9]")
SKIP_W = {
    "こと","もの","ため","よう","とき","ところ","場合","以下","以上","など",
    "また","その","この","あの","どの","して","する","した","ある","いる",
    "において","おいて","として","により","による","について","という",
    "参照","出典","脚注","関連","index","索引","一覧","項目","記事",
    "れる","られる","せる","たい","って","また","なお","ただし","つまり",
    "第一","第二","普通","一定","伝統的","必要","名称","正式","範囲",
}


def build_index():
    """語 → ファイル内の位置。これだけ覚えておけば、本体は読まなくていい"""
    idx, off = {}, 0
    t0 = time.time()
    with open(PAGES, "rb") as f:
        for line in f:
            try:
                w = json.loads(line)["語"]
                idx.setdefault(w, off)
            except Exception:
                pass
            off += len(line)
    json.dump(idx, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  索引 {len(idx)} 語  {os.path.getsize(INDEX)/1e6:.1f} MB  "
          f"({time.time()-t0:.0f}秒)")
    return idx


class Dict:
    def __init__(self):
        if not os.path.exists(INDEX):
            build_index()
        self.idx = json.load(open(INDEX, encoding="utf-8"))
        self.f = open(PAGES, "rb")
        self._tok = None

    def has(self, w):
        return w in self.idx

    def look(self, w):
        """引く。索引の位置へ跳んで1行読むだけ"""
        o = self.idx.get(w)
        if o is None:
            return None
        self.f.seek(o)
        return json.loads(self.f.readline())["説明"]

    def tok(self):
        if self._tok is None:
            from cards_count import Tokenizer
            self._tok = Tokenizer()
        return self._tok

    def links(self, w, n=12):
        """その語の説明の中に出てくる、辞書に載っている別の語"""
        t = self.look(w)
        if not t:
            return []
        out, seen = [], {w}
        for x in self.tok().cut(t[:1200]):
            x = x.strip("。、．，.,！!？?「」『』（）()・…〜~ 　\t|=*#-")
            if (len(x) >= 2 and x not in seen and JP.search(x)
                    and CONTENT.search(x)          # かなだけの語は助詞が多い
                    and x not in SKIP_W and self.has(x)):
                seen.add(x); out.append(x)
                if len(out) >= n:
                    break
        return out

    def walk(self, start, depth=2, width=4, show=True):
        """辿る。ここが「繰り返す能力」の芯

        知らない語が出たら、それも引く。それを指定の段数だけ繰り返す。
        """
        seen, layer, all_found = {start}, [start], []
        for d in range(depth):
            nxt = []
            for w in layer:
                ls = [x for x in self.links(w, width * 3) if x not in seen][:width]
                if show and ls:
                    print(f"{'  ' * (d + 1)}{w} → {' / '.join(ls)}")
                for x in ls:
                    seen.add(x); nxt.append(x); all_found.append((d + 1, w, x))
            layer = nxt
            if not layer:
                break
        return all_found


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("word", nargs="?")
    ap.add_argument("--walk", type=int, default=0)
    ap.add_argument("--index", action="store_true")
    a = ap.parse_args()
    if a.index:
        build_index(); sys.exit()
    d = Dict()
    if not a.word:
        print(f"  辞書 {len(d.idx)} 語"); sys.exit()
    t0 = time.time()
    t = d.look(a.word)
    if t is None:
        print(f"  「{a.word}」は辞書に無い"); sys.exit()
    print(f"■ {a.word}   （{(time.time()-t0)*1000:.2f} ミリ秒で引いた）")
    for l in t.splitlines()[:6]:
        print("   " + l[:100])
    if a.walk:
        print(f"\n■ ここから {a.walk} 段たどる")
        t0 = time.time()
        found = d.walk(a.word, depth=a.walk)
        print(f"\n  {len(found)} 語に広がった（{(time.time()-t0)*1000:.0f} ミリ秒）")


# ============================================================
# 「〜って何？」に、辞書だけで答える（先生を呼ばない）
# ============================================================
_ASK = [
    re.compile(r"[「『]?([^\s「」『』、。]{1,20})[」』]?\s*(?:とは|って)\s*(?:何|なに|どういう)"),
    re.compile(r"[「『]?([^\s「」『』、。]{1,20})[」』]?\s*の\s*(?:意味|定義|由来|字源)"),
    re.compile(r"[「『]?([^\s「」『』、。]{1,20})[」』]?\s*(?:とは|というのは)\s*[?？。]?$"),
    re.compile(r"[「『]([^」』]{1,20})[」』]\s*(?:を|について)\s*(?:教えて|調べて|説明)"),
    re.compile(r"^([^\s、。]{1,20})\s*(?:を|について)\s*(?:教えて|調べて|説明して)"),
]

_TRIM = ("です", "ですか", "ますか", "だ", "なの", "って", "とは")


def ask_word(text):
    """質問文から、意味を聞かれている語を取り出す"""
    t = (text or "").strip()
    for p in _ASK:
        m = p.search(t)
        if m:
            w = m.group(1).strip()
            for x in _TRIM:
                if w.endswith(x) and len(w) - len(x) >= 1:
                    w = w[:-len(x)]
            if len(w) >= 1:
                return w
    return None


def answer(text, d=None, max_lines=4):
    """語義の質問なら、辞書から答えを作る。違えば None

    戻り値: {"語":..., "答え":..., "関連":[...], "ms":float} or None
    """
    w = ask_word(text)
    if not w:
        return None
    d = d or Dict()
    body = d.look(w)
    if body is None:
        return None
    t0 = time.time()
    lines = [l for l in body.splitlines() if len(l) >= 6][:max_lines]
    return {"語": w, "答え": "\n".join("  " + l[:110] for l in lines),
            "関連": d.links(w, 6), "ms": (time.time() - t0) * 1000}
