"""kernel/gakushuu.py の箱・本文枝の条件。kernel を import/変更しない。"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
    try:
        yield db
    finally:
        db.close()


def check_chishiki(db):
    sql = db.execute("SELECT sql FROM sqlite_master WHERE name='chishiki'").fetchone()
    cols = [r[1] for r in db.execute('PRAGMA table_info(chishiki)')]
    if not sql or 'fts5' not in sql[0].lower() or cols != ['title', 'text', 'source', 'url', 'added']:
        raise ValueError('chishiki の形が違います（FTS5・title,text,source,url,added が必要）')


def ensure_schema(db):
    db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS chishiki USING fts5('
               'title,text,source UNINDEXED,url UNINDEXED,added UNINDEXED)')
    check_chishiki(db)
    db.execute('CREATE TABLE IF NOT EXISTS tsunagari(moto TEXT NOT NULL,saki TEXT NOT NULL,'
               'shurui TEXT NOT NULL,UNIQUE(moto,saki,shurui))')
    db.execute('CREATE TABLE IF NOT EXISTS chishiki_meta(k TEXT PRIMARY KEY,v TEXT NOT NULL)')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='chishiki_trigram'").fetchone():
        # 大量の日本語検索が目的なので、trigram 非対応を黙って無視しない。
        db.execute("CREATE VIRTUAL TABLE chishiki_trigram USING fts5("
                   "title,text,source UNINDEXED,tokenize='trigram')")
        db.execute('INSERT INTO chishiki_trigram(rowid,title,text,source) '
                   'SELECT rowid,title,text,source FROM chishiki')


def insert_article(db, title, body, source, url, added):
    rowid = db.execute('INSERT INTO chishiki(title,text,source,url,added) VALUES(?,?,?,?,?)',
                       (title, body, source, url, added)).lastrowid
    db.execute('INSERT INTO chishiki_trigram(rowid,title,text,source) VALUES(?,?,?,?)',
               (rowid, title, body, source))


class TitleMatcher:
    """casefold 部分一致。重なった題・同じcasefoldの別題も落とさない。"""
    def __init__(self, titles):
        try:
            import ahocorasick
        except ImportError as e:
            raise RuntimeError('先に requirements.txt を pip install してください') from e
        groups = {}
        for title in titles:
            if len(title) >= 2:
                groups.setdefault(title.casefold(), []).append(title)
        self.automaton = ahocorasick.Automaton()
        for key, values in groups.items():
            self.automaton.add_word(key, tuple(values))
        self.empty = not groups
        if groups:
            self.automaton.make_automaton()

    def matches(self, text):
        if self.empty:
            return set()
        return {title for _, group in self.automaton.iter(text.casefold()) for title in group}


def add_body_edges(db, new_titles=None, progress=None):
    """総当たりと同じ枝を一括照合。新旧間の両向きも保存する。"""
    matcher = TitleMatcher(r[0] for r in db.execute('SELECT title FROM chishiki'))
    pending, count = [], 0
    for count, (title, body) in enumerate(db.execute('SELECT title,text FROM chishiki'), 1):
        for other in matcher.matches(body or ''):
            if other != title and (new_titles is None or title in new_titles or other in new_titles):
                pending.append((title, other, '本文'))
        if len(pending) >= 5000:
            db.executemany('INSERT OR IGNORE INTO tsunagari VALUES(?,?,?)', pending)
            pending.clear()
        if progress and count % 10000 == 0:
            progress(count)
    db.executemany('INSERT OR IGNORE INTO tsunagari VALUES(?,?,?)', pending)
    db.execute("INSERT OR REPLACE INTO chishiki_meta VALUES('枝再構築','1')")
    return count


def integrity(db):
    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
        raise ValueError('SQLite quick_check が失敗しました')
    for name in ('chishiki', 'chishiki_trigram'):
        db.execute(f"INSERT INTO {name}({name}) VALUES('integrity-check')")
    mismatch = db.execute('SELECT count(*) FROM chishiki c LEFT JOIN chishiki_trigram t '
                          'ON c.rowid=t.rowid WHERE t.rowid IS NULL OR c.title<>t.title '
                          'OR c.text<>t.text OR c.source<>t.source').fetchone()[0]
    if mismatch or db.execute('SELECT count(*) FROM chishiki').fetchone()[0] != db.execute(
            'SELECT count(*) FROM chishiki_trigram').fetchone()[0]:
        raise ValueError('trigram と本文の対応が壊れています')
