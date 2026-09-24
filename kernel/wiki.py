#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wiki.py -- Wikipedia を引く

  手元の辞書（Wiktionary）は「言葉の意味」には強いが、
  「誰」「どこ」「いつ」「今どうなっている」には答えられない。
  そこだけ Wikipedia に行く。

  【決めごと】
   ・読むだけ。書き込みはしない
   ・一度引いたら手元に貯める（同じことで何度も外に出ない）
   ・名乗り（User-Agent）を必ず付ける。以前これが無くて 429 で断られた
   ・間隔をあける。急かさない
"""
import os, json, time, urllib.parse, urllib.request

HERE  = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "wiki_cache.json")

API = "https://ja.wikipedia.org/w/api.php"
UA  = ("kernel-ai/0.1 (personal offline assistant; "
       "contact: local user) Python-urllib")

# 前に呼んだ時刻。続けて叩かないための見張り
_last = [0.0]
GAP = 2.0          # 秒。これより短い間隔では出ない（429で断られた）


def _cache():
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        return {}


def _save(d):
    tmp = CACHE + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, CACHE)


def _get(params, timeout=12, tries=4):
    """API を叩く。間隔をあけ、名乗りを付ける。

    記事を続けて何十本も取ると 429（急かしすぎ）で断られる。
    断られたら、待つ時間を倍にして、もう一度だけ頼む。
    相手のサーバーに迷惑をかけないための作法でもある。
    """
    params = dict(params, format="json", utf8=1)
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    back = GAP
    last = None
    for i in range(tries):
        wait = back - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8")
            _last[0] = time.time()
            return json.loads(body)
        except Exception as e:
            last = e
            _last[0] = time.time()
            back = back * 2 + 1        # 断られたら、倍待つ
    raise Exception(f"Wikipedia につながりませんでした（{last}）")


def search(word, n=5):
    """語で探して、見出しの候補を返す"""
    key = f"search:{word}:{n}"
    c = _cache()
    if key in c:
        return c[key]
    d = _get({"action": "query", "list": "search",
              "srsearch": word, "srlimit": n})
    out = [{"題": x["title"],
            "さわり": _strip(x.get("snippet", ""))}
           for x in d.get("query", {}).get("search", [])]
    c[key] = out
    _save(c)
    return out


def _strip(html):
    import re as _re
    return _re.sub(r"<[^>]+>", "", html).replace("&quot;", '"').strip()


def summary(title, chars=700):
    """その見出しの、はじめの説明を取る"""
    key = f"sum:{title}:{chars}"
    c = _cache()
    if key in c:
        return c[key]
    d = _get({"action": "query", "prop": "extracts",
              "exintro": 1, "explaintext": 1,
              "exchars": chars, "titles": title,
              "redirects": 1})
    pages = d.get("query", {}).get("pages", {})
    for _pid, p in pages.items():
        if "extract" in p and p["extract"].strip():
            out = {"題": p.get("title", title), "本文": p["extract"].strip(),
                   "url": "https://ja.wikipedia.org/wiki/"
                          + urllib.parse.quote(p.get("title", title))}
            c[key] = out
            _save(c)
            return out
    return None


def ask(word, chars=700):
    """語をひとつ渡すと、探して、いちばん近いものの説明を返す

    まずその語をそのまま見出しとして引く。
    「徳川家康」で探すと検索は「徳川氏」を先に返してくるが、
    本人が言ったのは「徳川家康」なので、そちらを優先する
    """
    direct = summary(word, chars)
    if direct:
        try:
            hits = search(word, 5)
            direct["ほかの候補"] = [h["題"] for h in hits
                                    if h["題"] != direct["題"]][:4]
        except Exception:
            direct["ほかの候補"] = []
        return direct

    hits = search(word, 5)
    if not hits:
        return None
    # 見出しがそのまま一致するものを優先する
    best = next((h["題"] for h in hits if h["題"] == word), hits[0]["題"])
    s = summary(best, chars)
    if s:
        s["ほかの候補"] = [h["題"] for h in hits if h["題"] != best][:4]
    return s


def article(title, chars=20000):
    """見出しの本文まるごと（前書きだけでなく、記事全体）を取る。

    語の意味を「まわりの語」から掴むには、前書き数行では足りない。
    ・「壁紙」を引くと建材の話が返ってくる。
    ・ほしいのはパソコンの話のほう。
    そこで、語を引くのをやめて、
    「パソコンの話の記事」を丸ごと集め、そこに出てくる語を見る。
    """
    key = f"art:{title}:{chars}"
    c = _cache()
    if key in c:
        return c[key]
    d = _get({"action": "query", "prop": "extracts", "explaintext": 1,
              "exchars": chars, "titles": title, "redirects": 1})
    for _pid, pg in d.get("query", {}).get("pages", {}).items():
        if pg.get("extract", "").strip():
            out = {"題": pg.get("title", title), "本文": pg["extract"].strip()}
            c[key] = out
            _save(c)
            return out
    c[key] = None
    _save(c)
    return None


def cached_count():
    return len(_cache())
