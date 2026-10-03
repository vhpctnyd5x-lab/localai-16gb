#!/usr/bin/env python3
"""数記事の自作ダンプで変換、実DBの一時コピーで取り込み・故障耐性を確認。"""
import bz2
from contextlib import redirect_stderr
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import xml.etree.ElementTree as ET

from db_common import ensure_schema, insert_article, integrity, readonly
from fetch import plan
from henkan import TRIVIA
from torikomu import DEFAULT_TARGET, import_db

HERE = Path(__file__).resolve().parent
A, B, OLD = '知識ダンプ試験甲', '知識ダンプ試験乙', '知識ダンプ試験既存'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_xml(path, pages):
    root = ET.Element('mediawiki', xmlns='http://www.mediawiki.org/xml/export-0.11/')
    for title, body, ns, redirect in pages:
        page = ET.SubElement(root, 'page')
        ET.SubElement(page, 'title').text = title
        ET.SubElement(page, 'ns').text = str(ns)
        if redirect:
            ET.SubElement(page, 'redirect', title=A)
        rev = ET.SubElement(page, 'revision')
        ET.SubElement(rev, 'text').text = body
    with bz2.open(path, 'wb') as stream:
        stream.write(ET.tostring(root, encoding='utf-8', xml_declaration=True))


def snapshot(path):
    with readonly(path) as db:
        return {t: db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                for t in ('chishiki', 'chishiki_trigram', 'tsunagari')}


def run():
    started = time.monotonic()
    assertions = 0

    def check(condition, note):
        nonlocal assertions
        if not condition:
            raise AssertionError(note)
        assertions += 1

    # _TRIVIA が読んだ版と一致することを、importせずASTで確認。
    import ast
    tree = ast.parse((HERE.parents[1] / 'kernel/gakushuu.py').read_text())
    value = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == '_TRIVIA' for t in n.targets))
    check(tuple(ast.literal_eval(value)) == TRIVIA, '_TRIVIA の写しが違う')
    f = lambda n: {'size': 10, 'sha1': 'a'*40, 'url': '/jawiki/20261001/' + n}
    combined = 'jawiki-20261001-pages-articles.xml.bz2'
    part = 'jawiki-20261001-pages-articles1.xml-p1p100.bz2'
    status = {'jobs': {'articlesdump': {'status': 'done', 'files': {part: f(part)}},
                       'articlesdumprecombine': {'status': 'done', 'files': {combined: f(combined)}}}}
    check(plan('jawiki', status)[0][0] == combined, '結合済みダンプを優先')
    del status['jobs']['articlesdumprecombine']
    check(plan('jawiki', status)[0][0] == part, '分割ダンプを扱う')
    status['jobs']['articlesdump']['status'] = 'in-progress'
    try:
        plan('jawiki', status)
    except ValueError:
        assertions += 1
    else:
        raise AssertionError('未完成ダンプを拒否しなかった')

    with tempfile.TemporaryDirectory(prefix='chishiki-test-') as name:
        temp = Path(name)
        body = ('基礎知識を広く学ぶための本文です。' * 80)
        markup = '{{Infobox|x=消すテンプレ秘文}}<ref>消す参照秘文</ref>\n{|\n| 消す表秘文\n|}\n'
        pages = [(A, markup + f'[[{B}]]と{OLD}。' + body * 8, 0, False),
                 ('映画の試験', body, 0, False), ('試験一覧', body, 0, False),
                 ('2026年', body, 0, False), ('試験曖昧', '{{曖昧さ回避}}' + body, 0, False),
                 ('短い試験', '短文', 0, False), ('転送試験', body, 0, True),
                 ('分類試験', body, 14, False)]
        write_xml(temp / 'wiki1.xml.bz2', pages)
        write_xml(temp / 'wiki2.xml.bz2', [(B, A + body, 0, False)])
        write_xml(temp / 'books.xml.bz2', [(A, '重複なので使わない' + body, 0, False),
                                         ('知識ダンプ試験教科書', markup + body, 0, False)])
        write_xml(temp / 'source.xml.bz2', [('知識ダンプ試験原典', markup + body, 0, False)])
        aozora = temp / 'aozora/cards/000001/files/100_txt_1'
        aozora.mkdir(parents=True)
        aozora.joinpath('100.txt').write_bytes(('知識ダンプ試験文学\n試験著者\n\n'
            '-----\nルビの説明\n-----\n｜漢字《かんじ》［＃編集注］\n' + body + '\n底本：捨てる書誌').encode('cp932'))
        aozora.joinpath('101.txt').write_text('知識ダンプ試験文学\n試験著者\n重複の本です。', encoding='utf-8')
        source = temp / 'cloud.sqlite3'
        cmd = [sys.executable, str(HERE / 'henkan.py'), '--output', str(source), '--workers', '2',
               '--wiki', 'jawiki', str(temp/'wiki1.xml.bz2'), '--wiki', 'jawiki', str(temp/'wiki2.xml.bz2'),
               '--wiki', 'jawikibooks', str(temp/'books.xml.bz2'), '--wiki', 'jawikisource', str(temp/'source.xml.bz2'),
               '--aozora', str(temp/'aozora')]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        with readonly(source) as db:
            rows = list(db.execute('SELECT title,text,source FROM chishiki'))
            check(len(rows) == 5, 'フィルタ・同題排除で5件になる')
            check({r[2] for r in rows} == {'Wikipedia(ダンプ)', 'Wikibooks', 'Wikisource', '青空文庫'}, '4つの出どころ')
            check(all(len(r[1]) <= 8000 for r in rows), '8000字上限')
            check(len(next(r[1] for r in rows if r[0] == A)) == 8000, '長い本文を切る')
            check(not any('秘文' in r[1] for r in rows), 'テンプレート・表・参照を除去')
            literature = next(r[1] for r in rows if r[2] == '青空文庫')
            check('漢字' in literature and not any(x in literature for x in ('《', '編集注', '捨てる書誌', 'ルビの説明')), 'cp932・ルビ・注・書誌')
            check(db.execute('SELECT 1 FROM chishiki_trigram WHERE chishiki_trigram MATCH ?', (B,)).fetchone(), '日本語trigram検索')
            check(db.execute("SELECT 1 FROM tsunagari WHERE moto=? AND saki=? AND shurui='リンク'", (A, B)).fetchone(), 'リンク枝')
        manifest = json.loads(source.with_suffix('.json').read_text())
        check(manifest['sha256'] == digest(source), '完成品SHA256')
        check(manifest['wikipedia_selected'] == 2, '分割版の抽出件数')

        target = temp / 'local.sqlite3'
        if DEFAULT_TARGET.is_file():
            with readonly(DEFAULT_TARGET) as live, sqlite3.connect(target) as copy:
                live.backup(copy)
            base = snapshot(target)['chishiki']
        else:
            base = 0
        with sqlite3.connect(target) as db:
            ensure_schema(db)
            insert_article(db, OLD, A + 'を説明します。', '既存試験', 'https://example.invalid/', '元の日時')
            insert_article(db, '知識ダンプ試験教科書', '手元の本文を守る', '既存試験', '', '元の日時')
            db.execute("INSERT OR REPLACE INTO chishiki_meta VALUES('枝再構築','1')")
        before_hash = digest(target)
        dry = import_db(source, target, True)
        check(dry['追加'] == 4 and dry['同題で省略'] == 1, 'dry-run件数')
        check(before_hash == digest(target), 'dry-runは無変更')
        before = snapshot(target)
        original_insert = __import__('torikomu').insert_article
        inserted = 0

        def broken(*a, **kw):
            nonlocal inserted
            original_insert(*a, **kw)
            inserted += 1
            if inserted == 2:
                raise KeyboardInterrupt('試験中断')

        with patch('torikomu.insert_article', broken), redirect_stderr(io.StringIO()):
            try:
                import_db(source, target)
            except KeyboardInterrupt:
                pass
        check(snapshot(target) == before, '中断時に本文・索引・枝を全てロールバック')
        backup = sorted(temp.glob('local.sqlite3.backup-*.sqlite3'))[0]
        check(snapshot(backup) == before, '控えが取り込み前と同じ')
        # プロセスが強制終了してもSQLiteのjournalから回復する。
        kill_script = '''import os, signal, sys
sys.path.insert(0, sys.argv[1])
import torikomu
original = torikomu.insert_article
def kill(*args, **kw):
    args[0].execute('PRAGMA cache_size=1')
    original(*args, **kw)
    os.kill(os.getpid(), signal.SIGKILL)
torikomu.insert_article = kill
from pathlib import Path
torikomu.import_db(Path(sys.argv[2]), Path(sys.argv[3]))
'''
        killed = subprocess.run([sys.executable, '-c', kill_script, str(HERE), str(source), str(target)],
                                capture_output=True, text=True)
        check(killed.returncode == -signal.SIGKILL, '強制終了を実行')
        # 通常取込の最初の読み込みでhot journalを回復する。更新前の状態を検証。
        from torikomu import read_target
        with read_target(target, False) as recovered:
            state = {t: recovered.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                     for t in ('chishiki', 'chishiki_trigram', 'tsunagari')}
        check(state == before, '強制終了後も箱が回復')
        with redirect_stderr(io.StringIO()):
            merged = import_db(source, target)
        check(merged['追加'] == 4, '取り込み4件')
        with sqlite3.connect(target) as db:
            check(db.execute('SELECT count(*) FROM chishiki').fetchone()[0] == base + 6, '既存箱コピーへ追加')
            check(db.execute('SELECT text FROM chishiki WHERE title=?', ('知識ダンプ試験教科書',)).fetchone()[0] == '手元の本文を守る', '同題は上書きしない')
            for moto, saki in ((A, OLD), (OLD, A)):
                check(db.execute("SELECT 1 FROM tsunagari WHERE moto=? AND saki=? AND shurui='本文'", (moto, saki)).fetchone(), '新旧間の両向き本文枝')
            check(db.execute("SELECT 1 FROM tsunagari WHERE moto=? AND saki=? AND shurui='リンク'", (A, B)).fetchone(), '取り込みリンク枝')
            integrity(db)
            assertions += 1
        check(import_db(source, target)['追加'] == 0, '再実行は0件')
        # reservoir samplingの件数と再現性（同じseedで題集合が同じ）。
        small_cmd = [sys.executable, str(HERE/'henkan.py'), '--workers', '1', '--wiki-limit', '1',
                     '--wiki', 'jawiki', str(temp/'wiki1.xml.bz2'), '--wiki', 'jawiki', str(temp/'wiki2.xml.bz2')]
        picked = []
        for n in (1, 2):
            p = temp/f'sampled{n}.sqlite3'
            subprocess.run(small_cmd + ['--output', str(p)], capture_output=True, text=True, check=True)
            with readonly(p) as db:
                picked.append(list(db.execute('SELECT title FROM chishiki')))
        check(len(picked[0]) == 1 and picked[0] == picked[1], '抽出上限と再現性')
        print(json.dumps({'確認': assertions, '自作ダンプから': 5, '一時コピーへ追加': 4,
                          '元の箱': base, '秒': round(time.monotonic()-started, 2),
                          'Cloud操作': 0, '本番変更': 0}, ensure_ascii=False))


if __name__ == '__main__':
    run()
