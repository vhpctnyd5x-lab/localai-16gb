#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dict_cards.py -- 辞書の説明文を数えて、カードを作る

  雑談5万字では語彙542語・ノイズだらけで失敗した。
  辞書の定義文は「語と語の関係」が濃縮されているので、
  同じ手法でも桁違いに良いカードになるはず。それを確かめる。

  ・単語で切るのは llm-jp のトークナイザ（抜いてきた辞書を借りる）
  ・数えるのは自分。掛け算はゼロ
  ・メモリ16GBに収めるため、二段構え（先に頻度で刈る）
"""
import os, sys, json, math, time, re
from collections import Counter, defaultdict

HERE  = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(HERE, "dict", "pages.jsonl")
OUT   = os.path.join(HERE, "dict_cards.json")

CONTENT = re.compile(r"[ァ-ヴ一-龥A-Za-z0-9]")
STOP = {"する","した","して","です","ます","ました","ません","ない","なる",
        "れる","られる","この","その","あの","どの","こと","もの","ため","よう",
        "いる","ある","いう","という","および","または","なお","ただし",
        "参照","出典","脚注","関連","語義","発音","用例","翻訳","対義語",
        "類義語","派生","活用","名詞","動詞","形容詞","副詞","助詞","接尾",
        "日本語","英語","中国語","ラテン","フランス","ドイツ"}


def tokens_of(text, tk):
    out = []
    for line in text.splitlines():
        for w in tk.cut(line.strip()):
            w = w.strip("。、．，.,！!？?「」『』（）()・…〜~ 　\t|=*#-")
            if 2 <= len(w) <= 10 and w not in STOP and CONTENT.search(w):
                out.append(w)
    return out


def build(min_count=6, window=6, top_k=100, max_vocab=80000):
    from cards_count import Tokenizer
    tk = Tokenizer()

    # --- 1回目：頻度を数えて、残す語を決める（メモリを守るため）---
    t0 = time.time(); freq = Counter(); n = 0
    for line in open(PAGES, encoding="utf-8"):
        d = json.loads(line)
        freq.update(tokens_of(d["説明"][:2500], tk))
        freq[d["語"]] += 3                      # 見出し語は少し重く
        n += 1
        if n % 20000 == 0:
            print(f"  1回目 {n} 語  種類 {len(freq)}  ({time.time()-t0:.0f}秒)",
                  flush=True)
    keep = {w for w, c in freq.most_common(max_vocab) if c >= min_count}
    print(f"  残す語: {len(keep)} / 全体 {len(freq)}  ({time.time()-t0:.0f}秒)",
          flush=True)

    # --- 2回目：共起を数える ---
    co = defaultdict(Counter); tot = 0; n = 0
    for line in open(PAGES, encoding="utf-8"):
        d = json.loads(line)
        head = d["語"]
        ws = [w for w in tokens_of(d["説明"][:2500], tk) if w in keep]
        # 見出し語は、その説明文の全語と結びつく（辞書ならではの強い手がかり）
        if head in keep:
            for w in ws[:120]:
                co[head][w] += 2; co[w][head] += 2; tot += 4
        for i, a in enumerate(ws):
            for b in ws[max(0, i - window):i + window + 1]:
                if a != b:
                    co[a][b] += 1; tot += 1
        n += 1
        if n % 20000 == 0:
            print(f"  2回目 {n} 語  ({time.time()-t0:.0f}秒)", flush=True)

    # --- PPMI で重みづけ ---
    N = sum(freq[w] for w in keep) or 1
    vecs = {}
    for a, ctr in co.items():
        row = {}
        for b, c in ctr.items():
            if c < 2: continue
            pmi = math.log((c / tot) / ((freq[a] / N) * (freq[b] / N)) + 1e-12)
            if pmi > 0:
                row[b] = round(pmi, 3)
        if len(row) >= 3:
            vecs[a] = dict(sorted(row.items(), key=lambda x: -x[1])[:top_k])
    json.dump({"meta": {"source": "ja.wiktionary", "words": len(vecs)},
               "vecs": vecs}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"  → {OUT}  {len(vecs)}語  {os.path.getsize(OUT)/1e6:.0f} MB  "
          f"({time.time()-t0:.0f}秒)", flush=True)


class DictCards:
    def __init__(self, path=OUT):
        self.v = json.load(open(path, encoding="utf-8"))["vecs"]

    def sim(self, a, b):
        x, y = self.v.get(a), self.v.get(b)
        if not x or not y: return None
        if len(x) > len(y): x, y = y, x
        d = sum(w * y[k] for k, w in x.items() if k in y)
        na = math.sqrt(sum(w * w for w in x.values()))
        nb = math.sqrt(sum(w * w for w in y.values()))
        return d / (na * nb) if na and nb else 0.0

    def near(self, w, n=8):
        if w not in self.v: return []
        out = [(self.sim(w, o) or 0, o) for o in self.v if o != w]
        out.sort(reverse=True)
        return out[:n]

    def nearest(self, w, cands):
        if w not in self.v: return None, 0.0, 0.0
        ss = sorted(((self.sim(w, c) or 0.0, c) for c in cands), reverse=True)
        if not ss: return None, 0.0, 0.0
        mg = ss[0][0] - ss[1][0] if len(ss) > 1 else ss[0][0]
        return ss[0][1], ss[0][0], mg


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "near":
        for sc, w in DictCards().near(sys.argv[2]):
            print(f"  {sc:.4f}  {w}")
    else:
        build()
