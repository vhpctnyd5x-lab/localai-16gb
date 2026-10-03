#!/usr/bin/env python3
"""控えを取って1トランザクションで追記。失敗・中断は全体をロールバック。"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time

from db_common import (TitleMatcher, add_body_edges, check_chishiki, ensure_schema,
                       insert_article, integrity, readonly)

DEFAULT_TARGET = Path.home() / 'Library/Application Support/kernel-ai/gakushuu/chishiki.sqlite3'


def report(message):
    print(message, file=sys.stderr, flush=True)


@contextmanager
def read_target(path, dry_run):
    if dry_run:
        with readonly(path) as db:
            yield db
    else:
        # SIGKILL後のhot journalの回復には書込可能な接続が必要。
        # mode=rw にして、競合でファイルが消えても空箱を作らない。
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True, timeout=30)
        try:
            yield db
        finally:
            db.close()


def import_db(source_path, target_path, dry_run=False):
    if source_path.resolve() == target_path.resolve():
        raise ValueError('取り込み元と取り込み先が同じです')
    if not source_path.is_file() or not target_path.is_file():
        raise FileNotFoundError('元と先の既存DBを指定してください（新規の空箱を誤作成しません）')
    with readonly(source_path) as src, read_target(target_path, dry_run) as current:
        check_chishiki(src)
        check_chishiki(current)
        titles = {r[0] for r in current.execute('SELECT title FROM chishiki')}
        existing = len(titles)
        total = new = duplicates = 0
        for (title,) in src.execute('SELECT title FROM chishiki'):
            total += 1
            if title in titles:
                duplicates += 1
            else:
                new += 1
                titles.add(title)
    estimate = {'元': total, '追加': new, '同題で省略': duplicates, '先の題数': existing, 'dry_run': dry_run}
    if dry_run or new == 0:
        return estimate
    # 依存不足は控え・変更の前に発見する。
    TitleMatcher(())
    if shutil.disk_usage(target_path.parent).free < target_path.stat().st_size + source_path.stat().st_size * 2:
        raise OSError('控え＋取り込み＋ジャーナル用の空き容量が足りません')
    lock_path = target_path.with_name(target_path.name + '.import.lock')
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with readonly(source_path) as src:
            # 入力側も1つのスナップショットで読む。
            src.execute('BEGIN')
            check_chishiki(src)
            dst = sqlite3.connect(target_path, timeout=30)
            backup_path = None
            try:
                dst.execute('PRAGMA synchronous=FULL')
                dst.execute('BEGIN IMMEDIATE')  # 他の書き込みを待ち、控えと更新の間の競合を防ぐ。
                check_chishiki(dst)
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                fd, name = tempfile.mkstemp(prefix=target_path.name + f'.backup-{stamp}-',
                                            suffix='.sqlite3.partial', dir=target_path.parent)
                os.close(fd)
                backup_temp = Path(name)
                # ロック中の接続自身で backup すると待ち続けるので、別の読取接続から控える。
                backup = sqlite3.connect(backup_temp)
                try:
                    with readonly(target_path) as snapshot:
                        snapshot.backup(backup)
                        if backup.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                            raise ValueError('控えの検証が失敗しました')
                finally:
                    backup.close()
                backup_path = backup_temp.with_suffix('')
                os.replace(backup_temp, backup_path)
                report(f'控え: {backup_path}')
                ensure_schema(dst)
                old_titles = {r[0] for r in dst.execute('SELECT title FROM chishiki')}
                new_titles = set()
                now = datetime.now(timezone.utc).isoformat()
                for title, body, source, url, added in src.execute('SELECT title,text,source,url,added FROM chishiki'):
                    if title in old_titles or title in new_titles:
                        continue
                    if not isinstance(title, str) or not title or not isinstance(body, str):
                        raise ValueError('入力に不正な題・本文があります')
                    insert_article(dst, title, body, source, url, added or now)
                    new_titles.add(title)
                    if len(new_titles) % 10000 == 0:
                        report(f'追加 {len(new_titles):,}件（未commit）')
                if src.execute("SELECT 1 FROM sqlite_master WHERE name='tsunagari'").fetchone():
                    for moto, saki in src.execute("SELECT moto,saki FROM tsunagari WHERE shurui='リンク'"):
                        if moto in new_titles and isinstance(saki, str) and len(saki.strip()) >= 2 and saki.strip() != moto:
                            dst.execute('INSERT OR IGNORE INTO tsunagari VALUES(?,?,?)', (moto, saki.strip(), 'リンク'))
                done = dst.execute("SELECT v FROM chishiki_meta WHERE k='枝再構築'").fetchone()
                add_body_edges(dst, new_titles if done else None,
                               lambda n: report(f'本文枝 {n:,}件を走査'))
                integrity(dst)
                dst.commit()
                estimate.update({'追加': len(new_titles), '控え': str(backup_path),
                                 '同題で省略': total - len(new_titles),
                                 '本文枝': dst.execute("SELECT count(*) FROM tsunagari WHERE shurui='本文'").fetchone()[0]})
            except BaseException:
                dst.rollback()
                report(f'中断: 取り込みはロールバックしました。控え: {backup_path}')
                raise
            finally:
                dst.close()
    return estimate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--target', type=Path, default=DEFAULT_TARGET)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    started = time.monotonic()
    result = import_db(args.source, args.target, args.dry_run)
    result['秒'] = round(time.monotonic() - started, 2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
