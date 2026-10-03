#!/usr/bin/env python3
"""XML/bz2 と青空文庫を kernel 互換 SQLite へ。ダンプは伸ばさず逐次処理。"""
import argparse
import bz2
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import html
import itertools
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import time
from urllib.parse import quote
import xml.etree.ElementTree as ET

from db_common import add_body_edges, ensure_schema, insert_article, integrity

# 2026-10-03 kernel/gakushuu.py _TRIVIA と同じ。更新時はここも照合する。
TRIVIA = ('ゲーム', 'RPG', 'ファミリーコンピュータ', 'アニメ', '漫画', '映画', 'ドラマ', '番組',
          'アルバム', 'シングル', '楽曲', 'バンド', 'アイドル', 'キャラクター', '選手', '声優', 'タレント')
SOURCES = {'jawiki': 'Wikipedia(ダンプ)', 'jawikibooks': 'Wikibooks', 'jawikisource': 'Wikisource'}
DOMAINS = {'jawiki': 'ja.wikipedia.org', 'jawikibooks': 'ja.wikibooks.org',
           'jawikisource': 'ja.wikisource.org'}
DISAMBIG = re.compile(r'\{\{\s*(?:曖昧さ回避|aimai|disambig(?:uation)?|hndis|geodis)\b', re.I)
YEAR = re.compile(r'(?:紀元前)?[0-9０-９〇零一二三四五六七八九十百千]+(?:年|年度)?')


def log(message):
    print(f'[{time.strftime("%H:%M:%S")}] {message}', flush=True)


def wiki_pages(path, site):
    opener = bz2.open if str(path).endswith('.bz2') else open
    with opener(path, 'rb') as stream:
        events = ET.iterparse(stream, events=('start', 'end'))
        _, root = next(events)
        ns = root.tag.partition('}')[0] + '}' if '}' in root.tag else ''
        for event, page in events:
            if event != 'end' or page.tag != ns + 'page':
                continue
            title = (page.findtext(ns + 'title') or '').strip()
            namespace = page.findtext(ns + 'ns', default='0')
            raw = page.findtext(ns + 'revision/' + ns + 'text') or ''
            redirect = page.find(ns + 'redirect') is not None or bool(re.match(r'\s*#(?:redirect|転送)', raw, re.I))
            eligible = namespace == '0' and not redirect and len(title) >= 2
            if site == 'jawiki':
                eligible = eligible and not ('一覧' in title or '曖昧さ回避' in title or YEAR.fullmatch(title)
                                             or any(x in title for x in TRIVIA) or DISAMBIG.search(raw))
            if eligible:
                yield site, title, raw
            page.clear()
            root.clear()


def wiki_plain(task):
    import mwparserfromhell
    site, title, raw, max_chars, min_bytes = task
    # 参照節以降は平文にもリンクにも含めない。
    raw = re.split(r'(?m)^={2,}\s*(?:脚注|注釈|出典|参考文献|外部リンク)\s*={2,}\s*$', raw, maxsplit=1)[0]
    code = mwparserfromhell.parse(raw)
    for node in list(code.filter_templates(recursive=True)):
        try:
            code.remove(node, recursive=True)
        except ValueError:
            pass  # 親テンプレートを消すと子も既に消えている。
    for node in list(code.filter_tags(recursive=True)):
        if str(node.tag).strip().lower() in {'ref', 'references', 'table', 'gallery', 'timeline', 'imagemap', 'math', 'noinclude'}:
            try:
                code.remove(node, recursive=True)
            except ValueError:
                pass
    links = []
    for link in code.filter_wikilinks(recursive=True):
        target = str(link.title).strip().lstrip(':').split('#')[0].replace('_', ' ')
        if ':' in target:  # ファイル・カテゴリ等は本文ごと消す。
            try:
                code.remove(link, recursive=True)
            except ValueError:
                pass
        elif len(target) >= 2 and target != title:
            links.append(target)
    body = html.unescape(code.strip_code(normalize=True, collapse=True))
    body = re.sub(r'[ \t\u3000]+', ' ', body)
    body = re.sub(r'\n\s*\n+', '\n\n', body).strip()
    if site == 'jawiki' and len(body.encode('utf-8')) < min_bytes:
        return None
    body = body[:max_chars].strip()
    if not body:
        return None
    url = f'https://{DOMAINS[site]}/wiki/{quote(title.replace(" ", "_"), safe="")} '
    return title, body, SOURCES[site], url.strip(), json.dumps(sorted(set(links)), ensure_ascii=False)


def converted(path, site, args):
    tasks = ((s, t, b, args.max_chars, args.min_wiki_bytes) for s, t, b in wiki_pages(path, site))
    # executor.map 全件投入はメモリを食う。256件ずつ上限をつける。
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        while batch := list(itertools.islice(tasks, 256)):
            yield from pool.map(wiki_plain, batch, chunksize=8)


def aozora_articles(folder, max_chars):
    for path in sorted(Path(folder).rglob('*.txt')):
        raw = path.read_bytes()
        # aozorahack は基本 Shift_JIS。置換文字で壊さず、UTF-8 見本も受ける。
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('cp932')
        lines = [x.strip() for x in text.splitlines()]
        head = [x for x in lines if x][:2]
        if len(head) < 2:
            continue
        title = head[0]
        footer = re.split(r'(?m)^底本[：:]', text, maxsplit=1)[0]
        footer = re.sub(r'(?ms)^[-－]{5,}\s*\n.*?^[-－]{5,}\s*$', '', footer)
        # 題・著者名は出どころのURLと共に残す。ルビ・編集注を落とす。
        body = re.sub(r'《[^》]*》|［＃[^］]*］', '', footer).replace('｜', '').strip()[:max_chars]
        match = re.search(r'/cards/(\d+)/files/(\d+)_', path.as_posix())
        url = (f'https://www.aozora.gr.jp/cards/{match[1]}/card{match[2]}.html' if match
               else 'https://github.com/aozorahack/aozorabunko_text')
        if title and body:
            yield title, body, '青空文庫', url, '[]'


def build(args):
    started = time.monotonic()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage_path = output.with_name(output.name + '.stage')
    partial = output.with_name(output.name + '.partial')
    for path in (output, stage_path, partial):
        if path.exists():
            raise FileExistsError(f'上書きしません: {path}')
    stage = sqlite3.connect(stage_path)
    stage.execute('CREATE TABLE articles(slot INTEGER PRIMARY KEY,title TEXT UNIQUE,text TEXT,source TEXT,url TEXT,links TEXT)')
    rng = random.Random(args.seed)
    stats, eligible, selected = {}, 0, 0
    for site, path in args.wiki:
        seen = kept = 0
        log(f'{site}: {path} を変換')
        for item in converted(path, site, args):
            if item is None:
                continue
            seen += 1
            if stage.execute('SELECT 1 FROM articles WHERE title=?', (item[0],)).fetchone():
                continue
            if site == 'jawiki':
                eligible += 1
                # 一様な reservoir sampling。ダンプ順（古い記事等）への偏りを避ける。
                slot = eligible if eligible <= args.wiki_limit else rng.randrange(eligible) + 1
                if slot > args.wiki_limit:
                    continue
                stage.execute('INSERT OR REPLACE INTO articles VALUES(?,?,?,?,?,?)', (slot, *item))
                selected = min(eligible, args.wiki_limit)
            else:
                stage.execute('INSERT INTO articles(title,text,source,url,links) VALUES(?,?,?,?,?)', item)
            kept += 1
            if seen % 10000 == 0:
                stage.commit()
                log(f'{site}: 有効 {seen:,}件・採用操作 {kept:,}回')
        stage.commit()
        prior = stats.get(site, {'eligible': 0, 'insert_operations': 0})
        stats[site] = {'eligible': prior['eligible'] + seen, 'insert_operations': prior['insert_operations'] + kept}
    if args.aozora:
        n = 0
        for item in aozora_articles(args.aozora, args.max_chars):
            cursor = stage.execute('INSERT OR IGNORE INTO articles(title,text,source,url,links) VALUES(?,?,?,?,?)', item)
            n += cursor.rowcount
        stage.commit()
        stats['aozora'] = {'inserted': n}
    log('FTS5・trigram の箱を作成')
    db = sqlite3.connect(partial)
    db.execute('PRAGMA synchronous=FULL')
    db.execute('PRAGMA cache_size=-65536')
    db.execute('PRAGMA temp_store=FILE')
    ensure_schema(db)
    added = datetime.now(timezone.utc).isoformat()
    for i, (title, body, source, url, links) in enumerate(stage.execute(
            'SELECT title,text,source,url,links FROM articles ORDER BY slot'), 1):
        insert_article(db, title, body, source, url, added)
        db.executemany('INSERT OR IGNORE INTO tsunagari VALUES(?,?,?)',
                       ((title, other, 'リンク') for other in json.loads(links)))
        if i % 2000 == 0:
            db.commit()
            log(f'索引 {i:,}件')
    db.commit()
    log('本文枝を一括照合')
    add_body_edges(db, progress=lambda n: log(f'本文枝 {n:,}件を走査'))
    db.commit()
    for table in ('chishiki', 'chishiki_trigram'):
        db.execute(f"INSERT INTO {table}({table}) VALUES('optimize')")
        db.commit()
    integrity(db)
    db.commit()
    counts = dict(db.execute('SELECT source,count(*) FROM chishiki GROUP BY source'))
    edges = dict(db.execute('SELECT shurui,count(*) FROM tsunagari GROUP BY shurui'))
    db.close()
    stage.close()
    os.replace(partial, output)
    stage_path.unlink()
    with output.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = {'articles': counts, 'edges': edges, 'filters': stats, 'wikipedia_selected': selected,
                'max_chars': args.max_chars, 'seed': args.seed, 'bytes': output.stat().st_size,
                'sha256': sha, 'seconds': round(time.monotonic() - started, 2)}
    output.with_suffix('.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    output.with_suffix('.sha256').write_text(f'{sha}  {output.name}\n')
    log(json.dumps(manifest, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wiki', nargs=2, metavar=('SITE', 'XML_BZ2'), action='append', default=[])
    p.add_argument('--aozora', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--wiki-limit', type=int, default=300000)
    p.add_argument('--min-wiki-bytes', type=int, default=2000)
    p.add_argument('--max-chars', type=int, default=8000)
    p.add_argument('--workers', type=int, default=max(1, min(6, os.cpu_count() or 1)))
    p.add_argument('--seed', type=int, default=20261003)
    args = p.parse_args()
    if not args.wiki and not args.aozora:
        p.error('--wiki または --aozora が必要')
    sites = [s for s, _ in args.wiki]
    if any(s not in SOURCES for s in sites):
        p.error('SITE は jawiki/jawikibooks/jawikisource')
    order = {'jawiki': 0, 'jawikibooks': 1, 'jawikisource': 2}
    if [order[s] for s in sites] != sorted(order[s] for s in sites):
        p.error('jawiki → jawikibooks → jawikisource の順に指定してください（分割版は連続して指定）')
    if not (1 <= args.max_chars <= 8000 and args.wiki_limit >= 1 and args.workers >= 1 and args.min_wiki_bytes >= 2000):
        p.error('max-chars は1〜8000、wiki-limit/workers は正、min-wiki-bytes は2000以上')
    build(args)


if __name__ == '__main__':
    main()
