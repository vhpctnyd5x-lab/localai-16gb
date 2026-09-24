#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crawler.py -- 辞書を辿って、意味の網を自分で編む

  「あ」を調べる → 説明文に「かな文字」が出てくる → それも知らない
  → 「かな文字」を調べる → また知らない語が出てくる → …

  これを止まるまで繰り返す。止めなければ無限に広がる。
  ＝ このエンジンの「繰り返す能力」の実装そのもの。

  取ってきた説明文は、そのままカードの材料になる。
  辞書の定義文は「語と語の関係」が濃縮されているので、
  雑談の何倍も効率よく意味の網が編める。

  使い方:
    python3 crawler.py --max 500                 500語まで辿る
    python3 crawler.py --max 5000 --resume       続きから
    python3 crawler.py --seed 猫 犬 移動         出発点を指定
    python3 crawler.py --status                  今どこまで来たか
"""
import os, sys, json, time, re, urllib.parse, urllib.request, argparse

HERE  = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "dict")
PAGES = os.path.join(STORE, "pages.jsonl")
STATE = os.path.join(STORE, "state.json")

UA = "kernel-ai/0.1 (personal local dictionary crawler; contact: local user)"
WIKT = "https://ja.wiktionary.org/w/api.php"
WIKI = "https://ja.wikipedia.org/w/api.php"

# 出発点。ここから網が広がる
SEEDS = ["あ", "かな", "文字", "言葉", "意味",
         "ファイル", "フォルダ", "画像", "写真", "動画", "音楽", "文書",
         "移動", "複製", "削除", "整理", "検索", "作成", "保存",
         "大きい", "小さい", "新しい", "古い", "多い", "少ない",
         "パソコン", "机", "時間", "日付", "名前", "場所", "数"]

JP = re.compile(r"[ぁ-んァ-ヴー一-龥]")
BAD = re.compile(r"^(Wikipedia|Category|Template|Help|File|Portal|MediaWiki):")


def get(url, params, timeout=30):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_batch(api, titles):
    """まとめて説明文を取る（1件ずつより礼儀正しく、そして速い）"""
    try:
        d = get(api, {"action": "query", "prop": "extracts",
                      "explaintext": 1, "exlimit": 20, "format": "json",
                      "redirects": 1, "titles": "|".join(titles)})
    except Exception as e:
        return {}, str(e)
    out = {}
    for p in (d.get("query", {}).get("pages") or {}).values():
        t, x = p.get("title"), p.get("extract")
        if t and x:
            out[t] = x
    return out, None


class Tok:
    """抜いてきた日本語トークナイザで、説明文を単語に切る"""
    def __init__(self):
        from cards_count import Tokenizer
        self.t = Tokenizer()

    def words(self, text):
        out = []
        for line in text.splitlines():
            for w in self.t.cut(line.strip()):
                w = w.strip("。、．，.,！!？?「」『』（）()・…〜~ 　\t=*#")
                if 2 <= len(w) <= 12 and JP.search(w):
                    out.append(w)
        return out


def load_state():
    if os.path.exists(STATE):
        try:
            d = json.load(open(STATE, encoding="utf-8"))
            return set(d["visited"]), d["queue"]
        except Exception:
            pass
    return set(), []


def save_state(visited, queue):
    os.makedirs(STORE, exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump({"visited": sorted(visited), "queue": queue[:200000]},
              open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, STATE)


def crawl(max_words, seeds=None, delay=0.15, resume=True, report=50):
    os.makedirs(STORE, exist_ok=True)
    visited, queue = load_state() if resume else (set(), [])
    if not queue:
        queue = list(seeds or SEEDS)
    tok = Tok()
    f = open(PAGES, "a", encoding="utf-8")
    got, t0, miss = 0, time.time(), 0

    while queue and got < max_words:
        batch, seen_now = [], set()
        while queue and len(batch) < 20:
            w = queue.pop(0)
            if w in visited or w in seen_now or BAD.match(w):
                continue
            seen_now.add(w); batch.append(w)
        if not batch:
            break

        pages, err = fetch_batch(WIKT, batch)
        rest = [w for w in batch if w not in pages]
        if rest:                                  # 辞書に無ければ百科事典を見る
            time.sleep(delay)
            more, _ = fetch_batch(WIKI, rest)
            pages.update(more)

        for w in batch:
            visited.add(w)
        for title, text in pages.items():
            visited.add(title)
            f.write(json.dumps({"語": title, "説明": text[:4000]},
                               ensure_ascii=False) + "\n")
            got += 1
            # 説明文の中の語を、次に調べる列に足す ＝ ここが「繰り返し」
            for nw in tok.words(text[:2500]):
                if nw not in visited:
                    queue.append(nw)
        miss += len(batch) - len(pages)
        f.flush()

        if got // report != (got - len(pages)) // report:
            el = time.time() - t0
            print(f"  {got} 語  待ち {len(queue)}  "
                  f"({el:.0f}秒, {got/max(el,1):.1f} 語/秒)", flush=True)
            save_state(visited, queue)
        time.sleep(delay)

    f.close()
    save_state(visited, queue)
    print(f"  取得 {got} 語 / 見つからず {miss} / 待ち {len(queue)} / "
          f"{time.time()-t0:.0f}秒", flush=True)


def status():
    visited, queue = load_state()
    n = sum(1 for _ in open(PAGES, encoding="utf-8")) if os.path.exists(PAGES) else 0
    size = os.path.getsize(PAGES) / 1e6 if os.path.exists(PAGES) else 0
    print(f"  調べ終わった語 : {len(visited)}")
    print(f"  集めた説明文   : {n} 件  ({size:.1f} MB)")
    print(f"  次に調べる列   : {len(queue)} 語")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--seed", nargs="*")
    ap.add_argument("--delay", type=float, default=0.15)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        status()
    else:
        crawl(a.max, a.seed, a.delay, resume=not a.fresh)
