#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dict_build.py -- 日本語Wiktionaryのダンプから、語と説明の対を取り出す

  ネットを叩き続けるのは失礼だし遅い（実際429で止められた）。
  Wikimedia 自身が「大量に欲しければダンプを使え」と言っている。
  一度落とせば、あとは手元で何度でも辿れる。

  出力: dict/pages.jsonl  （1行1語。{"語":..., "説明":...}）
"""
import os, sys, json, bz2, re, time, xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DUMP = os.path.join(HERE, "dict", "jawiktionary.xml.bz2")
OUT  = os.path.join(HERE, "dict", "pages.jsonl")

NS   = "{http://www.mediawiki.org/xml/export-0.11/}"
JP   = re.compile(r"[ぁ-んァ-ヴー一-龥]")
SKIP = re.compile(r"^(Wiktionary|カテゴリ|Category|テンプレート|Template|"
                  r"MediaWiki|ヘルプ|Help|付録|索引|モジュール|Module|ファイル|File|"
                  r"利用者|User|トーク|Talk|ノート):")

# 中身が運営の話になっているページ。語の意味とは無関係なので捨てる
ADMIN = re.compile(r"(削除依頼|このページは|進行中の依頼|保護依頼|移動依頼|"
                   r"荒らし|投稿ブロック|管理者|署名|ウィキ(?:ペディア|辞典)は)")

# ウィキ記法を落として、素の文にする
CLEAN = [
    (re.compile(r"\{\{[^{}]*\}\}"), " "),          # テンプレート
    (re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]"), r"\1"),   # 内部リンク
    (re.compile(r"<ref[^>]*>.*?</ref>", re.S), " "),
    (re.compile(r"<[^>]+>"), " "),
    (re.compile(r"'''?"), ""),
    (re.compile(r"^[=*#:;|!]+", re.M), " "),
    (re.compile(r"\[https?://\S+\s*([^\]]*)\]"), r"\1"),
    (re.compile(r"https?://\S+"), " "),
    (re.compile(r"[ \t]{2,}"), " "),
    # 画像・分類・言語見出しなど、文になっていない行の材料
    (re.compile(r"(?:thumb|right|left|center|\d+px)\|"), " "),
    (re.compile(r"(?:Category|カテゴリ|File|ファイル|Image|画像):[^\n]*"), " "),
    (re.compile(r"^\s*(?:\{\||\|\}|\|-|\|).*$", re.M), " "),
]


def clean(t):
    for p, r in CLEAN:
        t = p.sub(r, t)
    lines = []
    for l in t.splitlines():
        l = l.strip(" \t|=*#:;")
        if len(l) < 4 or not JP.search(l):
            continue
        # かなが1文字も無い行は、表や分類の残りかすが多い
        if not re.search(r"[ぁ-んァ-ヴ]", l) and len(l) < 12:
            continue
        lines.append(l)
    return "\n".join(lines)


def run(limit=None, report=20000):
    t0, n, kept = time.time(), 0, 0
    fout = open(OUT, "w", encoding="utf-8")
    with bz2.open(DUMP, "rb") as f:
        title = None
        for ev, el in ET.iterparse(f, events=("end",)):
            tag = el.tag[len(NS):] if el.tag.startswith(NS) else el.tag
            if tag == "title":
                title = el.text
            elif tag == "page":
                n += 1
                txt = None
                for t in el.iter(NS + "text"):
                    txt = t.text
                if title and txt and not SKIP.match(title):
                    body = clean(txt)
                    if (len(body) >= 20 and JP.search(title)
                            and not ADMIN.search(body[:600])):
                        fout.write(json.dumps({"語": title, "説明": body[:6000]},
                                              ensure_ascii=False) + "\n")
                        kept += 1
                el.clear()
                if n % report == 0:
                    el_s = time.time() - t0
                    print(f"  読んだ {n} / 使えた {kept}  ({el_s:.0f}秒)", flush=True)
                if limit and kept >= limit:
                    break
    fout.close()
    print(f"  → {OUT}  {kept} 語  {os.path.getsize(OUT)/1e6:.0f} MB  "
          f"({time.time()-t0:.0f}秒)")


if __name__ == "__main__":
    run(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
