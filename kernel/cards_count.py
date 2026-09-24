#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cards_count.py -- 「ちゃんと単語で切ってから」数えてカードを作る

  前の版は文字N-gramで切っていたため、語彙が「ァイル」「そうい」のような
  断片だらけになり、使いものにならなかった。

  そこで、巨大モデルから抜いてきた日本語トークナイザ(99,574語)で
  正しく単語に切ってから数える。
  ＝ AIが作った辞書を借りて、統計は自分で取る。掛け算はゼロ。
"""
import os, sys, json, math, glob, time, re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TOK  = os.path.join(HERE, "mined", "llmjp.tokenizer.json")


class Tokenizer:
    """SentencePiece Unigram をビタビ探索で解く（一番もっともらしい切り方を選ぶ）"""

    def __init__(self, path=TOK):
        d = json.load(open(path, encoding="utf-8"))
        self.score = {}
        for ent in d["model"]["vocab"]:
            tok, sc = (ent[0], ent[1]) if isinstance(ent, list) else (ent, 0.0)
            self.score[tok.replace("▁", "")] = sc
        self.score.pop("", None)
        self.maxlen = max(len(k) for k in self.score)

    def cut(self, s):
        n = len(s)
        best = [(-1e18, -1)] * (n + 1)
        best[0] = (0.0, -1)
        for i in range(1, n + 1):
            for L in range(1, min(self.maxlen, i) + 1):
                sc = self.score.get(s[i - L:i])
                if sc is None:
                    if L > 1: continue
                    sc = -30.0                      # 未知の1文字は強く罰する
                cand = best[i - L][0] + sc
                if cand > best[i][0]:
                    best[i] = (cand, i - L)
        out, i = [], n
        while i > 0:
            j = best[i][1]
            if j < 0: break
            out.append(s[j:i]); i = j
        return out[::-1]


# ひらがなだけの語は、ほとんどが助詞・活用語尾。意味の担い手は漢字・カナ・英数
_CONTENT = re.compile(r"[ァ-ヴ一-龥A-Za-z0-9]")

# 助詞・記号など、意味を持たない語は数えない
STOP = set("のをにへとがはでやかもねよなさこそあどでもだけしてしたするですますませんでしたある"
           "いるいうことそれこれあれどれ、。！？!?…「」『』（）()・ー~ 　\t")
STOP |= {"の","を","に","へ","と","が","は","で","や","か","も","ね","よ","な","さ",
         "し","て","た","する","です","ます","ん","だ","ある","いる","いう","こと",
         "する","した","して","ない","なる","れる","られる","この","その","あの",
         "です","ました","ません","でしょ","そう","もの","ため","よう","的","性"}


def build(paths, out="jp_counted.json", window=5, min_count=4, top_k=120):
    tk = Tokenizer()
    files = []
    for p in paths:
        files += glob.glob(os.path.join(p, "**", "*.txt"), recursive=True) \
            if os.path.isdir(p) else [p]
    docs, chars = [], 0
    for f in files:
        t = open(f, encoding="utf-8", errors="ignore").read()
        chars += len(t)
        docs.append(t)
    print(f"  材料 {len(files)} ファイル / {chars} 文字")

    t0 = time.time()
    toks_all = []
    for d in docs:
        for line in d.splitlines():
            ws = []
            for w in tk.cut(line.strip()):
                w = w.strip("。、．，.,！!？?「」『』（）()・…〜~ 　\t")
                if len(w) >= 2 and w not in STOP and _CONTENT.search(w):
                    ws.append(w)
            if len(ws) >= 2:
                toks_all.append(ws)
    freq = Counter(w for ws in toks_all for w in ws)
    keep = {w for w, c in freq.items() if c >= min_count}
    print(f"  切った語 {sum(len(x) for x in toks_all)} / 種類 {len(freq)} / "
          f"{min_count}回以上 {len(keep)}   ({time.time()-t0:.1f}秒)")

    co = defaultdict(Counter); tot = 0
    for ws in toks_all:
        ws = [w for w in ws if w in keep]
        for i, a in enumerate(ws):
            for b in ws[max(0, i - window):i + window + 1]:
                if a != b:
                    co[a][b] += 1; tot += 1
    N = sum(freq[w] for w in keep) or 1
    vecs = {}
    for a, ctr in co.items():
        row = {}
        for b, c in ctr.items():
            # PPMI：一緒に出やすさを、それぞれの出やすさで割る
            pmi = math.log((c / tot) / ((freq[a] / N) * (freq[b] / N)) + 1e-12)
            if pmi > 0:
                row[b] = round(pmi, 4)
        if row:
            vecs[a] = dict(sorted(row.items(), key=lambda x: -x[1])[:top_k])
    json.dump({"meta": {"chars": chars, "words": len(vecs)}, "vecs": vecs},
              open(os.path.join(HERE, out), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"  → {out}  {len(vecs)}語  {os.path.getsize(os.path.join(HERE,out))/1e6:.1f} MB")
    return vecs


class Counted:
    def __init__(self, path="jp_counted.json"):
        d = json.load(open(os.path.join(HERE, path), encoding="utf-8"))
        self.v = d["vecs"]

    def sim(self, a, b):
        x, y = self.v.get(a), self.v.get(b)
        if not x or not y:
            return None
        if len(x) > len(y): x, y = y, x
        d = sum(w * y[k] for k, w in x.items() if k in y)
        na = math.sqrt(sum(w * w for w in x.values()))
        nb = math.sqrt(sum(w * w for w in y.values()))
        return d / (na * nb) if na and nb else 0.0

    def near(self, w, n=6):
        if w not in self.v: return []
        out = [(self.sim(w, o) or 0, o) for o in self.v if o != w]
        out.sort(reverse=True)
        return out[:n]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "near":
        c = Counted()
        for sc, w in c.near(sys.argv[2]):
            print(f"  {sc:.4f}  {w}")
    else:
        build([os.path.join(HERE, "corpus")])
