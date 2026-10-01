#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会話を邪魔せず Wikipedia と記録から知識・技の候補を貯める。"""
import json
import fcntl
import hashlib
import os
import re
import socket
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path.home() / "Library" / "Application Support" / "kernel-ai"
STATE_VERSION = 3
# 9/30: 種から1段だけだと 400記事で題が尽きて止まった。3段までたどる（1記事から5つ・同じ絞り）。
MAX_DEPTH = 3
# Wikipedia 日本語版にある、Mac の作業と基本知識に役立つ題。
LEARN_SEEDS = [
    "コンピュータ", "パーソナルコンピュータ", "オペレーティングシステム", "macOS", "Unix", "Linux",
    "ファイルシステム", "ファイル (コンピュータ)", "ディレクトリ", "パス (コンピュータ)",
    "コマンドラインインタプリタ", "シェル", "Bash", "Z shell", "ターミナルエミュレータ",
    "プログラミング言語", "Python", "JavaScript", "プログラミング", "ソフトウェア", "アルゴリズム",
    "データ構造", "バージョン管理", "Git", "正規表現", "テキストエディタ", "統合開発環境",
    "HTML", "CSS", "World Wide Web", "ウェブブラウザ", "インターネット", "HTTP", "電子メール",
    "ドメイン名", "Domain Name System", "コンピュータネットワーク", "暗号", "公開鍵暗号",
    "ハッシュ関数", "データ圧縮", "ZIP (ファイルフォーマット)", "文字コード", "Unicode", "UTF-8",
    "データベース", "SQL", "SQLite", "表計算ソフト", "コンピュータセキュリティ", "バックアップ",
    "人工知能", "機械学習", "自然言語処理", "データ", "情報", "数学", "算数", "代数学",
    "幾何学", "確率", "統計学", "論理学", "物理学", "力学", "電磁気学", "化学", "生物学",
    "人体", "医学", "栄養学", "地理学", "地図", "気象学", "天文学", "地球科学", "環境",
    "日本", "日本の歴史", "世界の歴史", "地理", "経済学", "会計", "法律", "日本国憲法",
    "政治", "社会学", "心理学", "教育", "日本語", "英語", "言語", "文章", "読書", "著作権",
    "単位", "時間", "お金", "交通", "電気", "エネルギー", "食文化", "農業", "医療", "科学"
]
DEFAULT = {"入": False, "上限MB": 2048, "充電中だけ": False,
           "出どころ": {"Wikipedia": True, "振り返り": True},
           "振り返りで外の先生に聞く": True, "会話の言葉から学ぶ題を選ぶ": False}


def folder():
    return Path(os.environ.get("KERNEL_GAKUSHUU_DIR", ROOT / "gakushuu"))


def skills_folder():
    return Path(os.environ.get("KERNEL_SKILLS_DIR", ROOT / "skills"))


_MEMORY_SECRET = re.compile(r"(?:password|passphrase|api[_ -]?key|secret|token|パスワード|暗証番号|秘密鍵|クレジット|カード番号|住所|電話番号|メールアドレス|郵便番号|\b\d{13,19}\b|\b[^\s@]+@[^\s@]+\.[^\s@]+|(?:/Users/|~/|/private/|/tmp/))", re.I)


def _memory_db():
    path = folder() / "oboe.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.execute("CREATE TABLE IF NOT EXISTS oboe (id INTEGER PRIMARY KEY, 文 TEXT NOT NULL, 種類 TEXT NOT NULL, 出どころ TEXT NOT NULL, 作成日時 TEXT NOT NULL, 最終使用日時 TEXT, 消した INTEGER NOT NULL DEFAULT 0)")
    db.execute("CREATE TABLE IF NOT EXISTS oboe_deleted (hash TEXT PRIMARY KEY)")
    return db


def _memory_safe(sentence):
    sentence = re.sub(r"\s+", " ", str(sentence or "")).strip()
    return 8 <= len(sentence) <= 160 and not _MEMORY_SECRET.search(sentence)


def add_memories(items, source):
    if not isinstance(items, list):
        return 0
    made = 0
    with _memory_db() as db:
        for item in items[:3]:
            if not isinstance(item, dict):
                continue
            sentence = re.sub(r"\s+", " ", str(item.get("文", ""))).strip()
            kind = item.get("種類", "その他")
            if not _memory_safe(sentence) or kind not in ("好み", "事実", "仕事", "その他"):
                continue
            digest = hashlib.sha256(sentence.casefold().encode()).hexdigest()
            if db.execute("SELECT 1 FROM oboe_deleted WHERE hash=?", (digest,)).fetchone():
                continue
            existing = [row[0] for row in db.execute("SELECT 文 FROM oboe WHERE 消した=0")]
            if any(sentence.casefold() == old.casefold() or sentence.casefold() in old.casefold()
                   or old.casefold() in sentence.casefold() for old in existing):
                continue
            db.execute("INSERT INTO oboe(文,種類,出どころ,作成日時) VALUES(?,?,?,?)",
                       (sentence, kind, str(source)[:200], time.strftime("%Y-%m-%dT%H:%M:%S%z")))
            made += 1
    return made


def delete_memory(ident):
    with _memory_db() as db:
        row = db.execute("SELECT 文 FROM oboe WHERE id=? AND 消した=0", (int(ident),)).fetchone()
        if not row:
            return False
        digest = hashlib.sha256(row[0].casefold().encode()).hexdigest()
        db.execute("INSERT OR IGNORE INTO oboe_deleted(hash) VALUES(?)", (digest,))
        db.execute("UPDATE oboe SET 消した=1 WHERE id=?", (int(ident),))
        return True


def memories(limit=10):
    with _memory_db() as db:
        total = db.execute("SELECT count(*) FROM oboe WHERE 消した=0").fetchone()[0]
        rows = db.execute("SELECT id,文,種類,出どころ,作成日時,最終使用日時 FROM oboe WHERE 消した=0 ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    keys = ("id", "文", "種類", "出どころ", "作成日時", "最終使用日時")
    return {"数": total, "一覧": [dict(zip(keys, row)) for row in rows]}


def find_memories(request, limit=3):
    sep = re.compile(r"[\s、。，．・:：;；!?！？()（）\[\]【】「」『』\"']+|について|として|とは|では|には|へは|から|まで|より|って|など|された|される|する|した|して|いる|ある|なる|れた|の|は|が|を|に|へ|で|と|も|や|か")
    terms = [x for x in sep.split(str(request or "").strip()) if len(x) >= 2]
    if not terms:
        return []
    if not (folder() / "oboe.sqlite3").is_file():
        return []
    with _memory_db() as db:
        rows = db.execute("SELECT id,文 FROM oboe WHERE 消した=0").fetchall()
        df = {t: sum(t in text for _, text in rows) for t in set(terms)}
        ranked = []
        for ident, sentence in rows:
            hits = [t for t in set(terms) if t in sentence]
            if hits:
                score = sum(1 + len(rows) / (df[t] + 1) for t in hits) / (1 + len(set(terms)))
                ranked.append((score, ident, sentence))
        ranked.sort(reverse=True)
        selected = ranked[:limit]
        if selected:
            db.executemany("UPDATE oboe SET 最終使用日時=? WHERE id=?",
                           [(time.strftime("%Y-%m-%dT%H:%M:%S%z"), ident) for _, ident, _ in selected])
    return [text for _, _, text in selected]


def _local_memories(record):
    if (folder() / "busy").exists():
        return []
    prompt = ("会話記録から次の会話でも役立つ本人の短い事実・好み・続いている仕事を最大3件抽出。"
              "一時的情報、秘密、鍵、パスワード、カード番号、住所、連絡先、ファイル場所は除く。推測しない。"
              '思考なし。JSONだけで {"覚え書き":[{"文":"一文","種類":"好み|事実|仕事|その他"}]} を返す。\n'
              f"会話: {record.get('文', '')[:1600]}")
    payload = {"model": "local:main", "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 220, "stream": False, "temperature": 0,
               "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions",
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        # 頭脳は読む 25〜38・書く 7〜8 トークン/秒。1,600字の会話なら1分前後かかる（45秒では間に合わなかった）。
        with urllib.request.urlopen(req, timeout=150) as response:
            obj = json.load(response)["choices"][0]["message"]["content"]
        # --reasoning-format none なので空の <think></think> が付き、```json で囲むこともある（10/1 題名で同じことが起きた）。
        obj = re.sub(r"<think>.*?</think>", "", str(obj), flags=re.S)
        found = re.search(r"\{.*\}", obj, re.S)
        return json.loads(found.group(0)).get("覚え書き", []) if found else []
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return []


def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _state():
    return _version_state(_read(folder() / "state.json", {}))


def _version_state(state):
    state = dict(state) if isinstance(state, dict) else {}
    version = state.get("版")
    if version != STATE_VERSION:
        if version != 2:
            state["次の題"] = []
            state["見た記録"] = []   # 版1は、記録を「見た」にするだけで何も学んでいなかった
        # 9/30 版3: 版2は種から1段だけで、覚えた記事のリンクを残していない。種以外の記事を「広げる」列に入れ直す。
        state["広げる"] = [{"題": t, "深さ": 1} for t in state.get("見た題", []) if t not in LEARN_SEEDS]
    state["版"] = STATE_VERSION
    return state


def _log(message):
    p = folder() / "log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and p.stat().st_size >= 5 * 1024 * 1024:
        os.replace(p, p.with_suffix(".jsonl.1"))
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"時刻": time.strftime("%Y-%m-%d %H:%M:%S"), "文": str(message)}, ensure_ascii=False) + "\n")


def _status(message, **more):
    s = _state()
    s.update({"いま": message, "更新": time.time(), **more})
    _write(folder() / "state.json", s)


def _db():
    p = folder() / "chishiki.sqlite3"
    p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(p, timeout=5)
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chishiki USING fts5(title, text, source UNINDEXED, url UNINDEXED, added UNINDEXED)")
    db.execute("CREATE TABLE IF NOT EXISTS tsunagari(moto TEXT NOT NULL, saki TEXT NOT NULL, shurui TEXT NOT NULL, UNIQUE(moto,saki,shurui))")
    db.execute("CREATE TABLE IF NOT EXISTS chishiki_meta(k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    _ensure_knowledge_indexes(db)
    return db


def _ensure_knowledge_indexes(db):
    """既存DBの枝・日本語部分一致索引を初回だけ作る。以後の更新は保存時。"""
    trigram = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chishiki_trigram'").fetchone()
    if not trigram:
        try:
            db.execute("CREATE VIRTUAL TABLE chishiki_trigram USING fts5(title,text,source UNINDEXED,tokenize='trigram')")
            db.execute("INSERT INTO chishiki_trigram(rowid,title,text,source) SELECT rowid,title,text,source FROM chishiki")
        except sqlite3.OperationalError:  # SQLite が trigram tokenizer を持たない場合も通常検索は動く。
            pass
    done = db.execute("SELECT v FROM chishiki_meta WHERE k='枝再構築'").fetchone()
    if not done:
        _rebuild_relationships(db)


def _rebuild_relationships(db):
    """本文中の保存済み記事題を1回走査して枝を作る（リンク枝は保持）。"""
    rows = db.execute("SELECT title,text FROM chishiki ORDER BY length(title) DESC").fetchall()
    db.execute("DELETE FROM tsunagari WHERE shurui='本文'")
    names = [(title, title.casefold()) for title, _ in rows if len(title) >= 2]
    for source, body in rows:
        folded = body.casefold()
        edges = [(source, title, "本文") for title, key in names
                 if title != source and key in folded]
        db.executemany("INSERT OR IGNORE INTO tsunagari(moto,saki,shurui) VALUES(?,?,?)", edges)
    db.execute("INSERT OR REPLACE INTO chishiki_meta(k,v) VALUES('枝再構築','1')")
    return db.execute("SELECT count(*) FROM tsunagari").fetchone()[0]


def rebuild_relationships():
    """保存済み全記事の本文枝を作り直す。既存リンク枝は消さない。"""
    with _db() as db:
        db.execute("DELETE FROM chishiki_meta WHERE k='枝再構築'")
        return _rebuild_relationships(db)


def _add_article_edges(db, title, body, links=()):
    current = title.casefold()
    for other, old_body in db.execute("SELECT title,text FROM chishiki WHERE title<>? AND length(title)>=2", (title,)):
        if other.casefold() in body.casefold():
            db.execute("INSERT OR IGNORE INTO tsunagari(moto,saki,shurui) VALUES(?,?,?)", (title, other, "本文"))
        if current in old_body.casefold():
            db.execute("INSERT OR IGNORE INTO tsunagari(moto,saki,shurui) VALUES(?,?,?)", (other, title, "本文"))
    for other in links:
        if isinstance(other, str) and len(other.strip()) >= 2 and other.strip() != title:
            db.execute("INSERT OR IGNORE INTO tsunagari(moto,saki,shurui) VALUES(?,?,?)", (title, other.strip(), "リンク"))


def _add_trigram(db, rowid, title, body, source):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chishiki_trigram'").fetchone():
        db.execute("INSERT INTO chishiki_trigram(rowid,title,text,source) VALUES(?,?,?,?)", (rowid, title, body, source))


def used_bytes():
    total = 0
    for p in folder().rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    for p in skills_folder().glob("*.md"):
        try:
            if (item := _parse_skill(p, "本人")) and item["made_by"] == "カーネル":
                total += p.stat().st_size
        except (OSError, UnicodeError):
            pass
    return total


def charging():
    try:
        result = subprocess.run(["pmset", "-g", "batt"], capture_output=True,
                                text=True, timeout=3, check=True)
        return "AC Power" in result.stdout or "charging" in result.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def _names():
    with _db() as db:
        return {r[0] for r in db.execute("SELECT title FROM chishiki")}


def _recent_topics():
    import kyoudou as gate
    out = []
    dbpath = Path(os.environ.get("KERNEL_CHATS_DB", ROOT / "chats.sqlite3"))
    if dbpath.exists():
        try:
            with sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True, timeout=2) as db:
                out += [r[0] for r in db.execute("SELECT text FROM turns WHERE role='user' ORDER BY id DESC LIMIT 30")]
        except (OSError, sqlite3.Error):
            pass
    out += [x["題"] for x in _records()[:20] if x.get("題")]
    safe = []
    for line in out:
        if (re.search(r'(?:~|/)[^\s、。，]+|\b[^\s/]+\.[A-Za-z0-9]{1,8}\b', line)
                or gate._looks_sensitive_content(line) or gate._contains_secret_value(line)):
            continue
        safe += re.findall(r"[一-龥ァ-ヶー]{2,14}", gate._scrub(line))
    return safe[:100]


def _record_dirs():
    """会話の記録の置き場。10/2: 今の輪（jiyuu・協働）の記録は kernel/kiroku（kyoudou.KIROKU_DIR）にあり、
    ここ（Application Support/kiroku）には 9/17 の操作記録しか無かった。振り返りと活かす役は、その古い頼み1件だけを見ていた。"""
    if os.environ.get("KERNEL_KIROKU_DIR"):
        return [Path(os.environ["KERNEL_KIROKU_DIR"])]
    return [Path(__file__).resolve().parent / "kiroku", ROOT / "kiroku"]


def _records():
    files = [(p, base) for base in _record_dirs() if base.is_dir() for p in base.rglob("*.jsonl")]
    found = []
    for p, base in sorted(files, key=lambda x: x[0].stat().st_mtime, reverse=True)[:80]:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
            request = ""
            for line in reversed(lines[-30:]):
                obj = json.loads(line)
                if "目当て" in obj:  # 現行の操作記録形式
                    stumble = str(obj.get("つまずき") or "").strip()
                    slow = isinstance(obj.get("秒"), (int, float)) and obj["秒"] >= 30
                    if not (stumble or slow):
                        continue
                    topic = str(obj.get("目当て") or "")[:200]
                    actions = obj.get("履歴") if isinstance(obj.get("履歴"), list) else []
                    tools = [str(x.get("手") or x.get("道具") or "") for x in actions if isinstance(x, dict)]
                    action = obj.get("手")
                    if isinstance(action, dict):
                        tools.append(str(action.get("手") or action.get("名前") or ""))
                    detail = {k: obj.get(k) for k in ("目当て", "履歴", "手", "つまずき", "正しい手", "秒") if k in obj}
                    ident = hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]
                    found.append({"題": topic, "文": json.dumps(detail, ensure_ascii=False)[:2500],
                                  "道具": [x for x in tools if x], "成否": "失敗" if stumble else "遅い",
                                  "日時": obj.get("時", ""),
                                  "識別": p.relative_to(base).as_posix() + ":" + ident})
                    break
                if not request:
                    for first in lines[:5]:
                        try:
                            event = json.loads(first)
                        except ValueError:
                            continue
                        if event.get("段階") in ("開始", "依頼"):
                            content = event.get("内容") if isinstance(event.get("内容"), dict) else {}
                            request = str(content.get("依頼") or content.get("文") or "")
                            break
                content = json.dumps(obj, ensure_ascii=False)
                detail = obj.get("内容") if isinstance(obj.get("内容"), dict) else {}
                slow = (any(k in content for k in ("timeout", "時間切れ", "遅い", "遅かった"))
                        or isinstance(detail.get("ミリ秒"), (int, float)) and detail["ミリ秒"] >= 30000)
                bad = (any(k in content for k in ("失敗", "error", "例外", "拒否"))
                       or obj.get("段階") == "結果" and detail.get("ok") is False)
                if not (slow or bad):
                    continue
                topic = str(request or obj.get("入力") or obj.get("質問") or obj.get("題") or detail.get("入力", ""))[:200]
                ident = hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]
                tools = [str(x.get("内容", {}).get("道具", "")) for x in map(json.loads, lines)
                         if isinstance(x.get("内容"), dict) and x.get("段階") == "提案"]
                found.append({"題": topic, "文": content[:2500], "道具": [x for x in tools if x],
                              "成否": "失敗" if bad else "遅い",
                              "識別": p.relative_to(base).as_posix() + ":" + ident})
                break   # 1つの頼みにつき1つ（同じ失敗の行が13あっても、振り返りは1回）
        except (OSError, ValueError, TypeError):
            continue
    return found


def _topic(state, known, use_conversation=False):
    entry = _topic_entry(state, known, use_conversation)
    return entry[0] if entry else None


# リンクの候補は題の言葉で探した記事なので、遊び・芸能の記事が混ざる（9/29「コンピュータ」→ゲーム・RPG・ファミコン）。
_TRIVIA = ("ゲーム", "RPG", "ファミリーコンピュータ", "アニメ", "漫画", "映画", "ドラマ", "番組", "アルバム",
           "シングル", "楽曲", "バンド", "アイドル", "キャラクター", "選手", "声優", "タレント")


def _valid_title(title):
    if not isinstance(title, str):
        return False
    title = title.strip()
    return (len(title) >= 2 and not any(x in title for x in ("(", "（", "一覧", "曖昧さ回避") + _TRIVIA)
            and not re.search(r"\d{3,4}年", title) and "/" not in title)


def _topic_entry(state, known, use_conversation=False):
    state = _version_state(state)
    seen = set(state.get("見た題", []))
    queue = []
    for item in state.get("次の題", []):
        if isinstance(item, dict):
            queue.append((item.get("題"), int(item.get("深さ", 1) or 1)))
        else:
            queue.append((item, 1))
    queue += [(title, 1) for title in (_recent_topics() if use_conversation else [])]
    queue += [(title, 0) for title in LEARN_SEEDS]
    for title, depth in queue:
        # 種は選んで置いた題なので「(」を含んでもよい（例 ファイル (コンピュータ)）。絞るのはリンクから来た題だけ。
        if _valid_title(title) or (depth == 0 and isinstance(title, str) and len(title.strip()) >= 2):
            title = title.strip()[:80]
            if title not in known and title not in seen:
                return title, depth
    return None


def _refetch_one(state, wiki_module):
    """覚えた Wikipedia の記事を1つ、本文（8,000字まで）で取り直す。取り直せたら True。
    取れなかった題も読んだことにする（消えた記事などで、同じ題に止まり続けない）。"""
    # 10/2: wiki.article が 1,200 字で切れていたので、全文で読み直した題は別の名前で数え直す（前の「本文を読んだ題」は使わない）
    read_titles = set(state.get("全文を読んだ題", []))
    with _db() as db:
        old_titles = [r[0] for r in db.execute("SELECT title FROM chishiki WHERE source='Wikipedia' ORDER BY rowid")]
    title = next((t for t in old_titles if t not in read_titles), None)
    if not title or not hasattr(wiki_module, "article"):
        return False
    full = _wiki(wiki_module.article, title, chars=8000)
    body = str((full or {}).get("本文", "")).strip()[:8000]
    state["全文を読んだ題"] = (list(read_titles) + [title])[-5000:]
    state["次は本文取り直し"] = False
    if not body:
        _write(folder() / "state.json", state)
        _log(f"本文を取れず: {title}")
        return False
    with _db() as db:
        row = db.execute("SELECT rowid FROM chishiki WHERE title=?", (title,)).fetchone()
        db.execute("UPDATE chishiki SET text=? WHERE title=?", (body, title))
        db.execute("DELETE FROM chishiki_trigram WHERE rowid=?", (row[0],))
        _add_trigram(db, row[0], title, body, "Wikipedia")
        db.execute("DELETE FROM tsunagari WHERE shurui='本文' AND (moto=? OR saki=?)", (title, title))
        _add_article_edges(db, title, body)
    _write(folder() / "state.json", state)
    _status(f"本文を取り直した: {title}")
    _log(f"本文を取り直し: {title}（{len(body)}字）")
    return True


def learn_once(cfg, *, wiki_module=None):
    """1記事だけ。外部依存は試験時に差し替え可能。"""
    if wiki_module is None:
        import wiki as wiki_module
        # wiki.py の共通キャッシュも学習の置き場に寄せ、本体のフォルダを書き換えない。
        wiki_module.CACHE = str(folder() / "wiki_cache.json")
    opts = cfg.get("事前学習", DEFAULT)
    if (folder() / "busy").exists():
        _status("会話中なので休み")
        return False
    if opts.get("充電中だけ", False) and not charging():
        _status("充電を待っています")
        return False
    limit = opts.get("上限MB", 2048) * 1024 * 1024
    if used_bytes() >= limit:
        _status("容量の上限で休み")
        return False
    known = _names()
    state = _state()
    if state.get("次は本文取り直し") and _refetch_one(state, wiki_module):
        return True
    entry = _topic_entry(state, known, opts.get("会話の言葉から学ぶ題を選ぶ", False))
    if not entry:
        # 題が尽きたら、覚えた記事を引き直してリンクを広げる（wiki.py の手元のしまい場所を使うので軽い）。
        grow = [x for x in state.get("広げる", []) if isinstance(x, dict) and int(x.get("深さ", 1) or 1) < MAX_DEPTH]
        if not grow:
            # 10/2: 題もリンクを広げる先も尽きたら、覚えた記事の本文を取り直す。0:08 に題が尽き、新しい記事を覚えないので
            # 交互の取り直しも始まらず、2,332 記事が要約（中央 189 字）のまま止まっていた。
            if _refetch_one(state, wiki_module):
                return True
            _status("次の題を待っています")
            return False
        item = grow[0]
        article = _wiki(wiki_module.ask, item["題"], chars=5000) or {}
        queued = {x.get("題") if isinstance(x, dict) else x for x in state.get("次の題", [])}
        additions = []
        for candidate in article.get("ほかの候補", []):
            if (_valid_title(candidate) and candidate not in known and candidate not in queued
                    and candidate not in state.get("見た題", [])):
                additions.append({"題": candidate.strip()[:80], "深さ": int(item.get("深さ", 1)) + 1})
                queued.add(candidate)
                if len(additions) == 5:
                    break
        _status(f"リンクを広げた: {item['題']}（{len(additions)}題）", 広げる=grow[1:],
                次の題=(state.get("次の題", []) + additions)[:100])
        return False
    title, depth = entry
    # wiki.py が User-Agent と2秒以上の間隔を管理する。
    article = _wiki(wiki_module.ask, title, chars=5000)
    if not article or not article.get("本文"):
        _status("記事が見つかりません", 最後の題=title,
                見た題=(state.get("見た題", []) + [title])[-500:])
        _log(f"記事なし: {title}")
        return False
    actual = article.get("題", title)
    full = _wiki(wiki_module.article, actual, chars=8000) if hasattr(wiki_module, "article") else None
    body = str((full or {}).get("本文") or article["本文"]).strip()[:8000]
    if actual in known:
        _status("既に覚えた記事", 見た題=(state.get("見た題", []) + [title])[-500:])
        return False
    if used_bytes() + len(body.encode("utf-8")) + 8192 > limit:
        _status("容量の上限で休み")
        return False
    with _db() as db:
        if db.execute("SELECT 1 FROM chishiki WHERE title=? LIMIT 1", (actual,)).fetchone():
            return False
        cursor = db.execute("INSERT INTO chishiki(title,text,source,url,added) VALUES(?,?,?,?,?)",
                            (actual, body, "Wikipedia", article.get("url", ""), time.strftime("%Y-%m-%d %H:%M:%S")))
        _add_trigram(db, cursor.lastrowid, actual, body, "Wikipedia")
        _add_article_edges(db, actual, body, article.get("ほかの候補", []))
    remaining = [x for x in state.get("次の題", [])
                 if (x.get("題") if isinstance(x, dict) else x) != title]
    if depth < MAX_DEPTH:
        additions = []
        queued = {x.get("題") if isinstance(x, dict) else x for x in remaining}
        for candidate in article.get("ほかの候補", []):
            if (not _valid_title(candidate) or candidate in known or candidate in queued
                    or candidate in state.get("見た題", [])):
                continue
            additions.append({"題": candidate.strip()[:80], "深さ": depth + 1})
            queued.add(candidate)
            if len(additions) == 5:
                break
        remaining += additions
    state["次は本文取り直し"] = True
    state["全文を読んだ題"] = list(state.get("全文を読んだ題", []))
    _log(f"Wikipedia: {actual}（{len(body)}字）")
    _status(f"記事を覚えた: {actual}", 最後の題=actual, 次の題=remaining[:100],
            次は本文取り直し=True, 全文を読んだ題=state.get("全文を読んだ題", []),
            見た題=(state.get("見た題", []) + [title])[-500:])
    return True


def _skill_name(name):
    if (not isinstance(name, str) or not name.strip() or len(name) > 40
            or "/" in name or "\\" in name or ".." in name
            or any(ord(c) < 32 for c in name)):
        raise ValueError("名前は40字以内で、/ や .. を含めないでください")
    return name.strip()


def _parse_skill(path, place):
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"\A---\n(.*?)\n---\n?(.*)\Z", raw, re.S)
    if not m:
        return None
    meta = dict(line.split(":", 1) for line in m[1].splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    if meta.get("name", path.stem) != path.stem:
        return None
    return {"name": meta.get("name", path.stem), "description": meta.get("description", ""),
            "on": meta.get("on") == "true", "made_by": meta.get("made_by", "最初から"),
            "body": m[2], "場所": place}


def skills():
    out = {}
    for base, place in ((HERE / "skills", "最初から"), (skills_folder(), "本人")):
        if base.is_dir():
            for p in sorted(base.glob("*.md")):
                try:
                    item = _parse_skill(p, place)
                    if item:
                        out[p.stem] = item
                except (OSError, UnicodeError):
                    pass
    return list(out.values())


def _skill_text(name, description, on, made_by, body):
    if not isinstance(description, str) or "\n" in description or "\r" in description or len(description) > 60:
        raise ValueError("説明は1行60字以内です")
    if not isinstance(body, str):
        raise ValueError("本文は文字にしてください")
    return f"---\nname: {name}\ndescription: {description}\non: {str(on).lower()}\nmade_by: {made_by}\n---\n{body}"


def change_skill(body):
    action = body.get("動き")
    name = _skill_name(body.get("name"))
    original = next((s for s in skills() if s["name"] == name), None)
    user_path = skills_folder() / (name + ".md")
    if action == "保存":
        description = body.get("description", original["description"] if original else "")
        text = body.get("body", original["body"] if original else "")
        on = body.get("on", original["on"] if original else True)
        if not isinstance(on, bool):
            raise ValueError("on は真偽値にしてください")
        made_by = original["made_by"] if original and original["made_by"] == "カーネル" else "本人"
    elif action in ("切替", "ゴミ箱"):
        if not original:
            raise ValueError("そのスキルはありません")
        description, text, made_by = original["description"], original["body"], original["made_by"]
        on = body.get("on", not original["on"]) if action == "切替" else False
        if not isinstance(on, bool):
            raise ValueError("on は真偽値にしてください")
        if action == "ゴミ箱" and user_path.exists():
            trash = Path(os.environ.get("KERNEL_TRASH_DIR", Path.home() / ".Trash"))
            trash.mkdir(parents=True, exist_ok=True)
            target = trash / user_path.name
            i = 1
            while target.exists():
                target = trash / f"{name}-{i}.md"
                i += 1
            shutil.move(str(user_path), str(target))
            return {"ok": True, "スキル": skills()}
    else:
        raise ValueError("動きが違います")
    user_path.parent.mkdir(parents=True, exist_ok=True)
    user_path.write_text(_skill_text(name, description, on, made_by, text), encoding="utf-8")
    return {"ok": True, "スキル": skills()}


_WAIT_LOGGED = False


def _stem(title):
    return re.sub(r"[^一-龥ぁ-んァ-ヶー\w-]", "", str(title))[:28] or "振り返り"


def _local_reflect(record):
    """8080で動作中の手元Qwen3.6だけに、思考なしで聞く。"""
    busy = folder() / "busy"
    if busy.exists():
        return None, True
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2) as health:
            if json.load(health).get("status") != "ok":
                return None, False
        if busy.exists():
            return None, True
        prompt = ("次に同じ頼みが来た時の具体的な手順を日本語で短く提案してください。\n"
                  f"依頼: {record.get('題', '')}\n"
                  f"道具: {', '.join(record.get('道具', []))}\n"
                  f"成否: {record.get('成否', '不明')}\n"
                  f"記録: {record.get('文', '')[:800]}")
        payload = {"model": "local:main", "messages": [{"role": "user", "content": prompt}],
                   "max_tokens": 300, "stream": True, "temperature": 0,
                   "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions",
                                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        parts = []
        # busy は語が届くたびに見る。会話を優先して途中の答えを捨てる。
        with urllib.request.urlopen(req, timeout=90) as stream:
            while True:
                if busy.exists():
                    return None, True
                line = stream.readline()
                if busy.exists():
                    return None, True
                if not line:
                    break
                if not line.startswith(b"data: "):
                    continue
                data = line[6:].strip()
                if data == b"[DONE]":
                    break
                chunk = json.loads(data)
                parts.append(chunk.get("choices", [{}])[0].get("delta", {}).get("content") or "")
        return "".join(parts).strip() or None, False
    except (OSError, ValueError, KeyError, IndexError):
        return None, busy.exists()


def _safe_for_teacher(value):
    import kyoudou as gate
    value = str(value)
    gate._register_secret_values(value)
    value = re.sub(r'(?:~|/)[^\s、。，]+|\b[^\s/]+\.[A-Za-z0-9]{1,8}\b', "[ファイル]", value)
    return gate._scrub(value)


def _teian_db():
    db = _db()
    db.execute("""CREATE TABLE IF NOT EXISTS teian (
        id INTEGER PRIMARY KEY, 題 TEXT NOT NULL, 中身 TEXT NOT NULL,
        根拠の記事 TEXT NOT NULL, 用件の識別 TEXT NOT NULL, 用件の題 TEXT NOT NULL DEFAULT '', 状態 TEXT NOT NULL DEFAULT '提案中',
        不要の理由 TEXT NOT NULL DEFAULT '', 作った日時 TEXT NOT NULL, 選んだ日時 TEXT NOT NULL DEFAULT ''
    )""")
    columns = {r[1] for r in db.execute("PRAGMA table_info(teian)")}
    if "用件の題" not in columns:
        db.execute("ALTER TABLE teian ADD COLUMN 用件の題 TEXT NOT NULL DEFAULT ''")
    db.execute("CREATE INDEX IF NOT EXISTS teian_day ON teian(作った日時)")
    return db


def teian_list():
    with _teian_db() as db:
        rows = db.execute("SELECT id,題,中身,根拠の記事,状態,不要の理由,作った日時,選んだ日時 FROM teian ORDER BY id DESC LIMIT 30").fetchall()
    result = []
    for ident, title, content, article, status, reason, made, chosen in rows:
        try:
            content = json.loads(content)
        except ValueError:
            continue
        result.append({"id": ident, "題": title, "中身": content, "根拠の記事": article,
                       "状態": status, "不要の理由": reason, "作った日時": made, "選んだ日時": chosen})
    return result


def _teian_to_skill(title, card):
    """10/2 本人: 活用カードを試した後に採用したら、技（スキル）として残し、次から頭脳が使えるようにする。"""
    name = re.sub(r"[/\\\x00-\x1f]|\.\.", "", str(title or "")).strip()[:40] or "活用の技"
    steps = "\n".join(f"{i}. {step}" for i, step in enumerate(card.get("手順") or [], 1))
    grounds = "；".join(f"{g.get('記事', '')}（{g.get('事実') or g.get('一文', '')}）" for g in card.get("根拠") or [] if isinstance(g, dict))
    body = (f"目的: {card.get('目的', '')}\n適用条件: {card.get('適用条件', '')}\n手順:\n{steps}\n確かめ方: {card.get('確かめ方', '')}\n"
            f"根拠: {grounds}\n出どころ: 活かす役（Qwen3.6）の提案を本人が採用\n")
    return change_skill({"動き": "保存", "name": name, "description": str(card.get("目的", "") or "活用の提案から")[:60],
                         "body": body, "on": True})


def teian_action(body):
    ident, status, reason = body.get("id"), body.get("状態"), body.get("不要の理由", "")
    if isinstance(ident, bool) or not isinstance(ident, int) or status not in ("試す", "後で", "不要", "採用"):
        raise ValueError("活用カードの選択が違います")
    if status == "不要" and reason not in ("用件に合わない", "もうできる", "手順が違う"):
        raise ValueError("不要の理由を選んでください")
    if status != "不要":
        reason = ""
    if status == "採用":
        with _teian_db() as db:
            row = db.execute("SELECT 題,中身 FROM teian WHERE id=?", (ident,)).fetchone()
        if not row:
            raise ValueError("活用カードが見つかりません")
        _teian_to_skill(row[0], json.loads(row[1]))
    with _teian_db() as db:
        cur = db.execute("UPDATE teian SET 状態=?,不要の理由=?,選んだ日時=? WHERE id=?",
                         (status, reason, time.strftime("%Y-%m-%d %H:%M:%S"), ident))
        if not cur.rowcount:
            raise ValueError("活用カードが見つかりません")
    return {"ok": True, "提案": teian_list()}


def _teian_terms(text):
    words = re.findall(r"[一-龥ぁ-んァ-ヶーA-Za-z0-9]{2,}", str(text or ""))
    terms = list(dict.fromkeys(words))
    for word in words:
        if len(word) > 3:
            terms.extend(word[i:i + 2] for i in range(len(word) - 1))
    return list(dict.fromkeys(terms))[:30]


def _teian_evidence(request, *, search=None):
    """依頼の語をIDFで順位付けし、上位記事と枝の隣2本までの根拠を返す。"""
    terms = _teian_terms(request)
    if search is not None:
        return search(request, terms)
    scored = {}
    try:
        with _db() as db:
            total = db.execute("SELECT count(*) FROM chishiki").fetchone()[0] or 1
            for term in terms:
                rows = db.execute("SELECT rowid,title,text FROM chishiki WHERE title LIKE ? OR text LIKE ? LIMIT 100",
                                  (f"%{term}%", f"%{term}%")).fetchall()
                if not rows:
                    continue
                weight = 0.1 + __import__("math").log(total / len(rows))
                for rowid, title, text in rows:
                    old = scored.get(rowid, (0, title, text))
                    scored[rowid] = (old[0] + weight * (3 * title.count(term) + text.count(term)), title, text)
            ranked = sorted(scored.values(), reverse=True)
            if not ranked:
                return []
            maximum = sum(0.1 + __import__("math").log(total + 1) for _ in terms) or 1
            if ranked[0][0] / maximum < 0.08:
                return []
            selected = [ranked[0]]
            title = ranked[0][1]
            neighbors = [r[0] for r in db.execute(
                "SELECT saki FROM tsunagari WHERE moto=? UNION SELECT moto FROM tsunagari WHERE saki=?", (title, title))]
            for neighbor in neighbors:
                hit = next((row for row in ranked if row[1] == neighbor), None)
                if hit:
                    selected.append(hit)
                if len(selected) == 3:
                    break
            result = []
            for _score, title, body in selected:
                sentences = re.split(r"(?<=[。！？])\s*|\n+", body)
                sentence = max(sentences, key=lambda s: sum(s.count(t) for t in terms), default="").strip()
                if sentence:
                    result.append({"記事": title, "一文": sentence[:500]})
            return result
    except (OSError, sqlite3.Error):
        return []


def _local_teian(record, evidence):
    if (folder() / "busy").exists():
        return None, True
    prompt = ("本人の用件に合う実行可能な提案カードをJSONだけで作る。根拠の事実とAIの考えを分ける。"
              "本人名・他者名・会社名など固有名詞は出力せず『対象A』などの仮名にする。"
              "無関係・危険・根拠不足なら {}。手順は3〜5個、道具名でなく本人に分かる言葉。"
              "形式: {\"題\":\"\",\"目的\":\"\",\"適用条件\":\"\",\"根拠\":[{\"記事\":\"\",\"事実\":\"\",\"考え\":\"\"}],"
              "\"手順\":[\"\"],\"確かめ方\":\"\",\"まだ分からない点\":\"\"}\n本人の用件: "
              + record.get("題", "") + "\n根拠段落: " + json.dumps(evidence, ensure_ascii=False))
    payload = {"model": "local:main", "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 600, "stream": True, "temperature": 0,   # 10/1 Claude: 日本語のカード JSON は 300〜500 トークン。240 では切れて読めない
               "chat_template_kwargs": {"enable_thinking": False}}
    try:
        if (folder() / "busy").exists():
            return None, True
        req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
        parts = []
        with urllib.request.urlopen(req, timeout=240) as response:   # 読む 1,000 トークン＋書く 600 で2分前後（この Mac）
            while True:
                if (folder() / "busy").exists():
                    return None, True
                line = response.readline()
                if (folder() / "busy").exists():
                    return None, True
                if not line:
                    break
                if not line.startswith(b"data: "):
                    continue
                data = line[6:].strip()
                if data == b"[DONE]":
                    break
                chunk = json.loads(data)
                parts.append(chunk.get("choices", [{}])[0].get("delta", {}).get("content") or "")
        return "".join(parts).strip() or None, False
    except (OSError, ValueError, KeyError, IndexError):
        return None, (folder() / "busy").exists()


def _parse_teian(raw):
    raw = re.sub(r"<think>.*?</think>", "", str(raw or ""), flags=re.S).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I).strip()
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return None
    required = ("題", "目的", "適用条件", "確かめ方", "まだ分からない点")
    if not isinstance(value, dict) or not all(isinstance(value.get(k), str) for k in required):
        return None
    evidence, steps = value.get("根拠"), value.get("手順")
    if not isinstance(evidence, list) or not evidence or not isinstance(steps, list) or not 3 <= len(steps) <= 5:
        return None
    if any(not isinstance(s, str) or not s.strip() for s in steps):
        return None
    return {"題": value["題"][:100], "目的": value["目的"][:300], "適用条件": value["適用条件"][:300],
            "根拠": evidence[:3], "手順": [s[:180] for s in steps], "確かめ方": value["確かめ方"][:300],
            "まだ分からない点": value["まだ分からない点"][:300]}


def _teian_teacher_text(card, record):
    text = json.dumps(card, ensure_ascii=False)
    source = str(record.get("題", ""))
    # 「○○さん/様/氏」等は先生へ出す前に、依頼に含まれた呼び名ごと仮名へ置換する。
    names = set(re.findall(r"[一-龥ぁ-ん]{2,8}(?=(?:さん|様|氏|くん|ちゃん))", source))
    for name in sorted(names, key=len, reverse=True):
        text = text.replace(name, "対象A")
    return _safe_for_teacher(text)


def make_teian_once(cfg, *, local=None, search=None, ask=None):
    opts = cfg.get("事前学習", DEFAULT)
    if not opts.get("出どころ", {}).get("振り返り") or (folder() / "busy").exists():
        return False
    state = _state()
    if time.time() - state.get("最後の活用試行時刻", 0) < 600:
        return False
    state["最後の活用試行時刻"] = time.time()
    _write(folder() / "state.json", state)
    today = time.strftime("%Y-%m-%d")
    with _teian_db() as db:
        if db.execute("SELECT count(*) FROM teian WHERE 作った日時 LIKE ?", (today + "%",)).fetchone()[0] >= 3:
            return False
        done = {r[0] for r in db.execute("SELECT 用件の識別 FROM teian")}
        done_pairs = set(db.execute("SELECT 用件の題,根拠の記事 FROM teian"))
        tried_topics = {r[0]: r[1] for r in db.execute(
            "SELECT 用件の題,count(*) FROM teian WHERE 状態='試す' GROUP BY 用件の題") if r[0]}
        tried_articles = {r[0]: r[1] for r in db.execute(
            "SELECT 根拠の記事,count(*) FROM teian WHERE 状態='試す' GROUP BY 根拠の記事")}
    records = [r for r in _records() if r.get("識別") not in done and r.get("道具")]
    if not records:
        return False
    counts = {}
    for r in _records():
        key = _stem(r.get("題", ""))
        counts[key] = counts.get(key, 0) + 1
    records.sort(key=lambda r: (r.get("成否") == "失敗", r.get("成否") == "遅い",
                                counts.get(_stem(r.get("題", "")), 0),
                                tried_topics.get(_stem(r.get("題", "")), 0)), reverse=True)
    record = evidence = None
    for candidate in records:
        found = _teian_evidence(candidate.get("題", ""), search=search)
        if not found:
            continue
        if len(found) > 1:
            found.sort(key=lambda item: tried_articles.get(item.get("記事", ""), 0), reverse=True)
        pair = (_stem(candidate.get("題", "")), found[0].get("記事", ""))
        if pair in done_pairs:
            continue
        record, evidence = candidate, found
        break
    if not evidence:
        return False
    raw, interrupted = _local_teian(record, evidence) if local is None else local(record, evidence)
    if interrupted or (folder() / "busy").exists():
        return False
    card = _parse_teian(raw)
    if not card:
        return False
    facts = {item.get("記事"): item.get("一文", "") for item in evidence if item.get("記事") and item.get("一文")}
    grounded = []
    for claim in card["根拠"]:
        if not isinstance(claim, dict):
            continue
        title = claim.get("記事")
        thought = claim.get("考え")
        if title in facts and isinstance(thought, str) and thought.strip():
            grounded.append({"記事": title, "事実": facts[title], "考え": thought[:300]})
    if not grounded:
        return False
    card["根拠"] = grounded
    external = [x for x in (cfg.get("先生") or []) if isinstance(x, str) and not x.startswith(("local:", "ollama:"))]
    if opts.get("振り返りで外の先生に聞く") and cfg.get("先生を使う") and external and not (folder() / "busy").exists():
        question = ("対象A。人名・固有名詞は対象Aなどの仮名に置き換え済みです。"
                    "『根拠に合っているか』『危ない手順はないか』だけ確認してください。\n" +
                    _teian_teacher_text(card, record))
        try:
            if ask is None:
                import sensei
                ask = sensei.kiku
            response = ask(question, {**cfg, "先生": external, "先生の深さ": "high"}, timeout=60)
            review = str(response.get("答え", "")).strip()
            if review and not response.get("error"):
                card["先生の確かめ"] = _safe_for_teacher(review)[:500]
                _log("先生の確かめ: " + card["先生の確かめ"])
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    if (folder() / "busy").exists():
        return False
    made = time.strftime("%Y-%m-%d %H:%M:%S")
    with _teian_db() as db:
        db.execute("INSERT INTO teian(題,中身,根拠の記事,用件の識別,用件の題,状態,作った日時) VALUES(?,?,?,?,?,?,?)",
                   (card["題"], json.dumps(card, ensure_ascii=False), evidence[0]["記事"], record["識別"],
                    _stem(record.get("題", "")), "提案中", made))
    _log(f"活用カード: {card['題']}")
    _status(f"活用カード: {card['題']}")
    return True


def reflect_once(cfg, *, ask=None, network=None):
    global _WAIT_LOGGED
    opts = cfg.get("事前学習", DEFAULT)
    if not opts.get("出どころ", {}).get("振り返り"):
        return False
    state = _state()
    if time.time() - state.get("最後の提案時刻", 0) < 600:
        return False
    if time.time() - state.get("最後の振り返り試行時刻", 0) < 600:
        return False
    seen = set(state.get("見た記録", []))
    # 9/30: 道具を使わなかった雑談（「ほんとに？」など）は技にならない。同じ頼みは1回だけ（-2・-3 が並んだ）。
    proposed = {re.sub(r"-\d+$", "", s["name"]) for s in skills() if s.get("made_by") == "カーネル"}
    record = next((r for r in _records() if r["識別"] not in seen and r.get("道具")
                   and _stem(r.get("題", "")) not in proposed), None)
    if not record:
        return False
    state["最後の振り返り試行時刻"] = time.time()
    _write(folder() / "state.json", state)
    _status(f"振り返り中: {record.get('題', '記録')}")
    _log(f"振り返り: 手元Qwen3.6で確認中: {record.get('題', '記録')}")
    local_answer, interrupted = _local_reflect(record)
    if interrupted:
        return False
    answer = local_answer
    source = "Qwen3.6"
    external = [x for x in (cfg.get("先生") or [])
                if isinstance(x, str) and not x.startswith(("local:", "ollama:"))]
    if opts.get("振り返りで外の先生に聞く", False) and cfg.get("先生を使う") and external:
        if network is None:
            try:
                socket.create_connection(("ja.wikipedia.org", 443), timeout=3).close()
                network = True
            except OSError:
                network = False
        if network:
            if ask is None:
                import sensei
                ask = sensei.kiku
            question = ("次に同じ頼みが来た時の具体的な手順を日本語で短く直してください。\n"
                        + "依頼: " + _safe_for_teacher(record.get("題", ""))
                        + "\n道具: " + _safe_for_teacher(", ".join(record.get("道具", [])))
                        + "\n成否: " + _safe_for_teacher(record.get("成否", "不明"))
                        + "\nQwen3.6の提案: " + _safe_for_teacher(local_answer or "（なし）"))
            try:
                _log(f"先生に聞いた: {external[0]}（考える深さ high）")
                response = ask(question, {**cfg, "先生": external, "先生の深さ": "high"}, timeout=60)   # 10/1: 裏の振り返りは深く
                teacher_answer = str(response.get("答え", "")).strip()
                if teacher_answer and not response.get("error"):
                    answer = teacher_answer
                    source = "Qwen3.6＋先生" if local_answer else "先生"
            except (OSError, ValueError, TypeError):
                pass
    if not answer:
        if not _WAIT_LOGGED:
            _log("振り返り: 手元Qwen3.6を待っています")
            _WAIT_LOGGED = True
        return False
    _WAIT_LOGGED = False
    remembered = add_memories(_local_memories(record), record.get("識別", "") + " " + str(record.get("日時", "")))
    if remembered:
        _log(f"覚え書き: {remembered}件")
    # 同じ本文の提案はファイル名が違っても重ねない。
    existing_skills = skills()
    if any(re.sub(r"\n出どころ: (?:Qwen3\.6|Qwen3\.6＋先生|先生|30B|30B＋先生)\s*$", "", s["body"].strip()) == answer
           for s in existing_skills):
        state["見た記録"] = (list(seen) + [record["識別"]])[-100:]
        _write(folder() / "state.json", state)
        return False
    stem = _stem(record["題"])
    existing = {s["name"] for s in existing_skills}
    name = stem
    i = 2
    while name in existing:
        name = f"{stem}-{i}"
        i += 1
    path = skills_folder() / (name + ".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    skill_text = _skill_text(name, "次に同じ頼みを進める手順", False, "カーネル",
                             answer + "\n出どころ: " + source)
    if used_bytes() + len(skill_text.encode("utf-8")) > opts.get("上限MB", 2048) * 1024 * 1024:
        return False
    path.write_text(skill_text, encoding="utf-8")
    state["見た記録"] = (list(seen) + [record["識別"]])[-100:]
    _write(folder() / "state.json", state)
    _log(f"振り返り: {stem} → 技を提案: {name}")
    _status(f"技を提案: {name}", 最後の提案時刻=time.time())
    return True


def overview(cfg, running=False):
    opts = {**DEFAULT, **cfg.get("事前学習", {})}
    try:
        with _db() as db:
            count = db.execute("SELECT count(*) FROM chishiki").fetchone()[0]
            recent = db.execute("SELECT title FROM chishiki ORDER BY rowid DESC LIMIT 5").fetchall()
            branches = [{"題": title, "関連": [r[0] for r in db.execute(
                "SELECT saki FROM tsunagari WHERE moto=? GROUP BY saki ORDER BY max(shurui='リンク') DESC, length(saki) DESC, saki LIMIT 3", (title,))]} for (title,) in recent]
            branch_count = db.execute("SELECT count(*) FROM tsunagari").fetchone()[0]
    except sqlite3.Error:
        count = 0
        branches, branch_count = [], 0
    try:
        lines = _tail_lines(folder() / "log.jsonl", 1000)
        events = [json.loads(line) for line in lines]
        today = time.strftime("%Y-%m-%d")
        recent = [{"時刻": e.get("時刻", ""), "種類": _activity_kind(e.get("文", "")),
                   "中身": e.get("文", "")} for e in events[-20:]]
        today_events = [e.get("文", "") for e in events if str(e.get("時刻", "")).startswith(today)]
        counts = {
            "読んだ記事": sum(x.startswith("Wikipedia:") for x in today_events),
            "本文を取り直した記事": sum(x.startswith("本文を取り直し:") for x in today_events),
            "振り返り": sum(x.startswith("振り返り:") for x in today_events),
            "先生に聞いた": sum(x.startswith("先生に聞いた:") for x in today_events),
            "技の提案": sum("技を提案:" in x for x in today_events),
            "活用カード": sum(x.startswith("活用カード:") for x in today_events),
            "覚え書き": sum(x.startswith("覚え書き:") for x in today_events),
        }
    except (OSError, ValueError, TypeError):
        recent, counts = [], {}
    memory = memories()
    external = [x for x in (cfg.get("先生") or []) if isinstance(x, str) and not x.startswith(("local:", "ollama:"))]
    ai = {"記事を読む": {"モデル": "なし（Wikipedia API）", "思考": "なし"},
          "振り返り": {"モデル": "手元 Qwen3.6", "思考": "なし", "上限トークン": 300},
          "活かす役": {"モデル": "手元 Qwen3.6", "思考": "なし", "上限トークン": 600},
          "確かめ": {"モデル": external, "思考の深さ": "high（外の先生）"}}
    return {"入": opts["入"], "動いている": running, "いま": _state().get("いま", "待機中"),
            "数": {"記事": count, "技の提案": sum(s["made_by"] == "カーネル" for s in skills()), "枝": branch_count, "覚え書き": memory["数"]},
            "覚え書き": memory["一覧"],
            "つながり": branches,
            "使った容量MB": round(used_bytes() / 1024 / 1024, 2), "上限MB": opts["上限MB"],
            "充電中だけ": opts["充電中だけ"], "出どころ": opts["出どころ"],
            "振り返りで外の先生に聞く": opts["振り返りで外の先生に聞く"],
            "会話の言葉から学ぶ題を選ぶ": opts["会話の言葉から学ぶ題を選ぶ"],
            "AI": ai, "今日の数": counts, "活動": recent, "記録": recent, "活用提案": teian_list()}



def _wiki(fn, *args, **kwargs):
    """10/1: 事前学習は控え（wiki_cache.json、7MB を1件ごとに丸ごと書き直していた）を使わない。試験の偽物は cache を知らなくてよい。"""
    try:
        return fn(*args, cache=False, **kwargs)
    except TypeError:
        return fn(*args, **kwargs)

def _activity_kind(message):
    if message.startswith("活用カード:"): return "活用カード"
    if message.startswith("先生の確かめ:"): return "先生の確かめ"
    if message.startswith("Wikipedia:"): return "記事"
    if message.startswith("本文を取り直し:"): return "本文を取り直し"
    if message.startswith("先生に聞いた:"): return "先生"
    if message.startswith("振り返り:"): return "振り返り"
    if message.startswith("覚え書き:"): return "覚え書き"
    return "状態"


def _tail_lines(path, count):
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        end = stream.tell()
        data = b""
        while end > 0 and data.count(b"\n") <= count:
            size = min(4096, end)
            end -= size
            stream.seek(end)
            data = stream.read(size) + data
    return data.decode("utf-8", errors="replace").splitlines()[-count:]


def _read_line(line):
    try:
        obj = json.loads(line)
        return obj.get("文", line)
    except ValueError:
        return line


def validate(current, patch):
    if not isinstance(patch, dict) or any(k not in DEFAULT for k in patch):
        raise ValueError("設定の項目が違います")
    value = {**DEFAULT, **current}
    for key in ("入", "充電中だけ", "振り返りで外の先生に聞く", "会話の言葉から学ぶ題を選ぶ"):
        if key in patch and not isinstance(patch[key], bool):
            raise ValueError(f"{key} は真偽値にしてください")
    if "上限MB" in patch and (isinstance(patch["上限MB"], bool) or not isinstance(patch["上限MB"], int) or not 1 <= patch["上限MB"] <= 102400):
        raise ValueError("上限MB は1〜102400にしてください")
    if "出どころ" in patch:
        src = patch["出どころ"]
        if not isinstance(src, dict) or any(k not in DEFAULT["出どころ"] or not isinstance(v, bool) for k, v in src.items()):
            raise ValueError("出どころの値が違います")
        value["出どころ"] = {**value.get("出どころ", {}), **src}
    value.update({k: v for k, v in patch.items() if k != "出どころ"})
    return value


def run():
    directory = folder()
    directory.mkdir(parents=True, exist_ok=True)
    lock = (directory / "worker.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    (directory / "worker.pid").write_text(str(os.getpid()), encoding="ascii")
    try:
        os.nice(10)
    except OSError:
        pass
    def stop(_signal, _frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    import settings
    try:
        while True:
            started = time.monotonic()
            try:
                cfg = settings.load()
                if not cfg.get("事前学習", {}).get("入"):
                    break
                opts = cfg["事前学習"]
                if (folder() / "busy").exists():
                    _status("会話中なので休み")
                elif opts.get("充電中だけ", False) and not charging():
                    _status("充電を待っています")
                elif used_bytes() >= opts.get("上限MB", 2048) * 1024 * 1024:
                    _status("容量の上限で休み")
                else:
                    if opts.get("出どころ", {}).get("Wikipedia", True):
                        learn_once(cfg)
                    reflect_once(cfg)
                    make_teian_once(cfg)
            except Exception as e:
                _log(f"例外: {type(e).__name__}: {e}")
                _status("失敗を記録し、次を待っています")
            time.sleep(max(1, 2 - (time.monotonic() - started)))
    finally:
        _status("停止中")
        (directory / "worker.pid").unlink(missing_ok=True)
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    run()
