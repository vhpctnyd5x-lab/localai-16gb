#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事前学習用に、公開された資料を出どころ別に1件ずつ取る。標準ライブラリのみ。"""
import csv
import io
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "kernel-ai/0.1 (personal offline assistant; contact: local user) Python-urllib"
GAP = 1.0
MAX_CHARS = 8000
_last = [0.0]
_aozora_rows = None

SOURCES = {
    "wikibooks": "https://ja.wikibooks.org/w/api.php",
    "wikisource": "https://ja.wikisource.org/w/api.php",
}
AOZORA_CSV = "https://raw.githubusercontent.com/aozorahack/jleaners/master/list_person_all_extended_utf8.csv"
AOZORA_TEXT = "https://raw.githubusercontent.com/aozorahack/aozorabunko_text/master/cards"
EGOV_API = "https://laws.e-gov.go.jp/api/2"
ARXIV_API = "https://export.arxiv.org/api/query"


def _get(url, timeout=25):
    """間隔を空けて名乗って取得。通信・HTTPエラーは呼び出し元で None 扱い。"""
    wait = GAP - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
        _last[0] = time.monotonic()
        return data
    except Exception:
        _last[0] = time.monotonic()
        raise


def _url(base, params):
    return base + "?" + urllib.parse.urlencode(params)


def _clean_result(title, body, source, url, license_name, others):
    title, body = str(title or "").strip(), str(body or "").strip()
    if not title or not body:
        return None
    return {"題": title, "本文": body[:MAX_CHARS], "出どころ": source,
            "url": url, "ライセンス": license_name,
            "ほかの候補": [str(x).strip() for x in others if str(x).strip() and str(x).strip() != title][:8]}


def _wiki(name, title):
    api = SOURCES[name]
    source = "ja." + name
    license_name = ("CC BY-SA 4.0（ページ個別の表示・例外を確認）" if name == "wikibooks"
                    else "各ページの権利表示に従う（PD・CC BY-SA 等）")
    query = title or {"wikibooks": "プログラミング", "wikisource": "著作権の切れた作品"}[name]
    hits = json.loads(_get(_url(api, {"action": "query", "list": "search", "srsearch": query,
                                      "srlimit": 8, "format": "json", "utf8": 1})).decode("utf-8"))
    titles = [x.get("title", "") for x in hits.get("query", {}).get("search", [])]
    if not titles:
        return None
    selected = next((x for x in titles if x.casefold() == query.casefold()), titles[0])
    pages = json.loads(_get(_url(api, {"action": "query", "prop": "extracts", "explaintext": 1,
                                       "titles": selected, "redirects": 1, "format": "json", "utf8": 1})).decode("utf-8"))
    for page in pages.get("query", {}).get("pages", {}).values():
        result = _clean_result(page.get("title", selected), page.get("extract", ""), source,
                               "https://ja." + name + ".org/wiki/" + urllib.parse.quote(page.get("title", selected).replace(" ", "_")),
                               license_name, titles)
        if result:
            return result
    return None


def _csv_rows(text):
    # aozorahack の一覧は UTF-8。旧版・ミラーの CP932 も受け付ける。
    try:
        decoded = text.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = text.decode("cp932")
    return list(csv.DictReader(io.StringIO(decoded)))


def _field(row, *names):
    for name in names:
        if row.get(name):
            return row[name].strip()
    return ""


def _aozora(title):
    global _aozora_rows
    if _aozora_rows is None:
        _aozora_rows = _csv_rows(_get(AOZORA_CSV, timeout=60))
    rows = _aozora_rows
    usable = []
    for row in rows:
        work = _field(row, "作品名")
        url = _field(row, "テキストファイルURL", "テキストファイルＵＲＬ", "テキストファイル")
        if not work or not url:
            continue
        # 著作権フラグが明示的に「なし」の作品だけを選ぶ。
        work_right = _field(row, "作品著作権フラグ")
        author_right = _field(row, "人物著作権フラグ")
        if work_right != "なし" or author_right != "なし":
            continue
        person_id = _field(row, "人物ID")
        parts = urllib.parse.urlsplit(url).path.strip("/").split("/")
        if len(parts) >= 5 and parts[-2] and person_id:
            url = AOZORA_TEXT + "/" + person_id + "/files/" + "/".join(parts[-2:])
        usable.append((work, url))
    if not usable:
        return None
    found = next((item for item in usable if item[0] == title), None) if title else None
    selected = found or (random.choice(usable) if not title else next((x for x in usable if title in x[0]), None))
    if not selected:
        return None
    work, url = selected
    raw = _get(url, timeout=40)
    # 青空文庫のテキストは Shift_JIS 系が中心。HTMLも文字コードを見てデコードする。
    try:
        body = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        body = raw.decode("cp932", errors="replace")
    body = re.sub(r"［＃.*?］", "", body, flags=re.S)
    body = re.sub(r"《.*?》", "", body, flags=re.S)
    body = body.replace("｜", "")
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return _clean_result(work, body, "青空文庫", url,
                         "パブリックドメイン（一覧で作品・人物の著作権フラグが『なし』）",
                         [w for w, _ in usable if w != work])


def _egov_laws(query):
    data = json.loads(_get(_url(EGOV_API + "/laws", {"law_title": query, "limit": 10, "response_format": "json"})).decode("utf-8"))
    laws = data.get("laws", data.get("law_list", []))
    return laws if isinstance(laws, list) else []


def _egov(title):
    query = title or "日本国憲法"
    laws = _egov_laws(query)
    if not laws:
        return None
    def val(d, *keys):
        return next((d[k] for k in keys if d.get(k)), "")
    def info(x, section, *keys):
        nested = x.get(section, {}) if isinstance(x, dict) else {}
        return val(nested, *keys) if isinstance(nested, dict) else ""
    selected = next((x for x in laws if info(x, "revision_info", "law_title") == query), laws[0])
    law_id = info(selected, "law_info", "law_id")
    law_title = info(selected, "revision_info", "law_title") or query
    if not law_id:
        return None
    obj = json.loads(_get(_url(EGOV_API + "/law_data/" + urllib.parse.quote(str(law_id), safe=""), {"response_format": "json"})).decode("utf-8"))
    # v2 JSON の法令本文は tag/children の木。条文の文字だけを順につなぐ。
    leaves = []
    def walk(node):
        if isinstance(node, str):
            if node.strip(): leaves.append(node.strip())
        elif isinstance(node, list):
            for item in node: walk(item)
        elif isinstance(node, dict):
            if "children" in node:
                walk(node["children"])
            elif "tag" not in node:
                for key, value in node.items():
                    if key not in ("attr", "law_info", "revision_info", "current_revision_info"):
                        walk(value)
    walk(obj.get("law_full_text", {}))
    body = "\n".join(leaves)
    others = [info(x, "revision_info", "law_title") for x in laws]
    return _clean_result(law_title, body, "e-Gov法令検索", EGOV_API + "/law_data/" + str(law_id),
                         "著作権法第13条（法令本文は著作権の目的とならない）", others)


def _arxiv(name, title):
    category = name.split(":", 1)[1] if ":" in name else "cs"
    allowed = {"cs", "stat", "math"}
    if category not in allowed:
        return None
    query = ("all:\"" + title.replace('"', "") + "\"") if title else "cat:" + {"cs": "cs.CL", "stat": "stat.ML", "math": "math.OC"}[category]
    xml = ET.fromstring(_get(_url(ARXIV_API, {"search_query": query, "start": 0, "max_results": 10, "sortBy": "submittedDate", "sortOrder": "descending"})))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = xml.findall("a:entry", ns)
    if not entries:
        return None
    def val(entry, key):
        node = entry.find("a:" + key, ns)
        return " ".join(node.itertext()).strip() if node is not None else ""
    selected = next((x for x in entries if val(x, "title").casefold() == (title or "").casefold()), entries[0])
    url = val(selected, "id")
    return _clean_result(val(selected, "title"), val(selected, "summary"), "arXiv (" + category + ")", url,
                         "arXiv 個別論文のライセンス（要旨のみ。本文の権利は各論文ページ参照）",
                         [val(x, "title") for x in entries])


def toru(name, title=None):
    """1件取得。name: wikibooks, wikisource, aozora, egov, arxiv:cs|stat|math。"""
    try:
        key = str(name).strip().lower()
        if key in ("wikibooks", "wikisource"):
            return _wiki(key, title)
        if key in ("aozora", "青空文庫"):
            return _aozora(title)
        if key in ("egov", "e-gov", "法令"):
            return _egov(title)
        if key == "arxiv" or key.startswith("arxiv:"):
            return _arxiv(key if ":" in key else "arxiv:cs", title)
        return None
    except Exception:
        return None


def _self_test():
    """固定レスポンスと偽 urlopen だけで各アダプターを確認。通信しない。"""
    import unittest
    from unittest.mock import patch

    class Reply:
        def __init__(self, data): self.data = data
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return self.data

    wiki_search = json.dumps({"query": {"search": [{"title": "試験題"}, {"title": "候補題"}]}}).encode()
    wiki_page = json.dumps({"query": {"pages": {"1": {"title": "試験題", "extract": "固定本文"}}}}).encode()
    csv_data = "作品ID,作品名,人物ID,テキストファイルURL,作品著作権フラグ,人物著作権フラグ\n000001,試験作品,000001,https://example.test/cards/000001/files/book/book.txt,なし,なし\n000002,候補,000002,https://example.test/cards/000002/files/other/other.txt,なし,なし\n".encode()
    aozora_text = "冒頭｜漢字《かんじ》［＃注記］おわり".encode("cp932")
    egov_search = json.dumps({"laws": [{"law_info": {"law_id": "0000000000000000"}, "revision_info": {"law_title": "試験法"}}]}).encode()
    egov_body = json.dumps({"law_full_text": {"tag": "Law", "children": [{"tag": "Article", "children": ["第一条", "本文"]}]}}).encode()
    arxiv = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/1</id><title>Test Paper</title><summary>Fixed abstract.</summary></entry><entry><id>https://arxiv.org/abs/2</id><title>Other Paper</title><summary>Other.</summary></entry></feed>'''
    routes = {"wikibooks.org/w/api.php": [wiki_search, wiki_page], "wikisource.org/w/api.php": [wiki_search, wiki_page],
              "raw.githubusercontent.com/aozorahack/jleaners/": [csv_data], "raw.githubusercontent.com/aozorahack/aozorabunko_text/": [aozora_text],
              "laws.e-gov.go.jp/api/2/laws": [egov_search], "laws.e-gov.go.jp/api/2/law_data/": [egov_body],
              "export.arxiv.org/api/query": [arxiv]}
    def fake_urlopen(request, timeout=0):
        url = request.full_url
        key = next(k for k in routes if k in url)
        return Reply(routes[key].pop(0))
    checks = 0
    def check(ok):
        nonlocal checks
        checks += 1
        if not ok: raise AssertionError("shiryou self test failed at " + str(checks))
    with patch("urllib.request.urlopen", fake_urlopen), patch("time.sleep", lambda _: None):
        _last[0] = 0
        for src, want in (("wikibooks", "ja.wikibooks"), ("wikisource", "ja.wikisource")):
            got = toru(src, "試験題")
            check(got is not None and got["出どころ"] == want and got["題"] == "試験題")
            check(got["本文"] == "固定本文" and got["ほかの候補"] == ["候補題"])
        got = toru("aozora", "試験作品")
        check(got is not None and got["題"] == "試験作品" and "漢字" in got["本文"] and "かんじ" not in got["本文"] and "注記" not in got["本文"])
        check(got["ほかの候補"] == ["候補"])
        got = toru("egov", "試験法")
        check(got is not None and got["題"] == "試験法" and "第一条" in got["本文"] and "本文" in got["本文"])
        got = toru("arxiv:cs", "Test Paper")
        check(got is not None and got["題"] == "Test Paper" and got["本文"] == "Fixed abstract." and got["ほかの候補"] == ["Other Paper"])
    print("shiryou 自己試験: %d/%d PASS" % (checks, checks))


def _live_test():
    sources = [("wikibooks", "プログラミング"), ("wikisource", "坊っちゃん"),
               ("aozora", "走れメロス"), ("egov", "民法"), ("arxiv:cs", None)]
    failed = False
    for name, title in sources:
        result = toru(name, title)
        if result:
            print("%s: %d字" % (name, len(result["本文"])))
        else:
            print("%s: None" % name)
            failed = True
    if failed:
        print("一部の取得に失敗（通信環境または出典側の応答を確認）")


if __name__ == "__main__":
    if "--tameshi" in sys.argv:
        _live_test()
    else:
        _self_test()
