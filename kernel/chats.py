#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chats.py -- 会話を SQLite で分けて持つ。

古い版は会話ごとに JSON を1枚ずつ保存していた。初回だけその JSON を
読み込むが、元ファイルは安全な読み取り専用バックアップとして残す。
新しい会話・発話・削除状態は ``chats.sqlite3`` の行だけを更新する。
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
import time
import uuid


ROOT = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "kernel-ai")
# 旧版の JSON は移行元兼バックアップ。新規保存には使わない。
DIR = os.path.join(ROOT, "chats")
DB = os.path.join(ROOT, "chats.sqlite3")

_INIT_LOCK = threading.RLock()
_READY = False


def _now():
    return time.time()


def _safe_id(cid):
    """自分で作った ID だけを SQLite の照会に渡す。"""
    safe = "".join(c for c in str(cid) if c.isalnum() or c in "-_")[:64]
    if not safe:
        raise ValueError("会話の番号がおかしい")
    return safe


def _path(cid):
    """旧 JSON の場所。互換用であり、新規保存には使わない。"""
    os.makedirs(DIR, exist_ok=True)
    return os.path.join(DIR, _safe_id(cid) + ".json")


def _float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _title(value):
    return str(value or "").strip()[:60] or "（無題）"


def _group(value):
    return str(value or "").strip()[:120]


def _open():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _create_schema(conn):
    # WAL は画面の読み取りと、生成が終わった瞬間の保存をぶつけにくくする。
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            created     REAL NOT NULL,
            updated     REAL NOT NULL,
            archived    INTEGER NOT NULL DEFAULT 0,
            group_name  TEXT NOT NULL DEFAULT '',
            deleted_at  REAL
        );

        CREATE TABLE IF NOT EXISTS turns (
            id              INTEGER PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            position        INTEGER NOT NULL,
            role            TEXT NOT NULL,
            text            TEXT NOT NULL,
            trace           TEXT NOT NULL DEFAULT '',
            ms              INTEGER NOT NULL DEFAULT 0,
            created         REAL NOT NULL,
            UNIQUE(conversation_id, position)
        );

        CREATE INDEX IF NOT EXISTS conversations_visible_updated
            ON conversations(deleted_at, archived, updated DESC);
        CREATE INDEX IF NOT EXISTS turns_conversation_position
            ON turns(conversation_id, position);
        """
    )


def _replace_turns(conn, cid, turns):
    conn.execute("DELETE FROM turns WHERE conversation_id = ?", (cid,))
    for position, turn in enumerate(turns):
        if not isinstance(turn, dict):
            continue
        conn.execute(
            """INSERT INTO turns
                 (conversation_id, position, role, text, trace, ms, created)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                cid,
                position,
                str(turn.get("役", "bot")),
                str(turn.get("文", "")),
                str(turn.get("経過", "")),
                _int(turn.get("ミリ秒")),
                _float(turn.get("時刻"), _now()),
            ),
        )


def _migrate_legacy(conn):
    """旧 JSON を一度だけ安全に複製する。

    JSON を削除・移動しないため、移行が途中で失敗しても元の会話を失わない。
    すでにゴミ箱へ入れた SQLite 行は、旧 JSON から復活させない。
    """
    if not os.path.isdir(DIR):
        return
    for filename in sorted(os.listdir(DIR)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(DIR, filename)
        try:
            with open(path, encoding="utf-8") as handle:
                legacy = json.load(handle)
            if not isinstance(legacy, dict):
                continue
            cid = _safe_id(legacy.get("id") or filename[:-5])
        except (OSError, ValueError, json.JSONDecodeError):
            continue

        now = _now()
        created = _float(legacy.get("作った"), now)
        updated = _float(legacy.get("更新"), created)
        old = conn.execute(
            "SELECT updated, deleted_at FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
        if old and old["deleted_at"] is not None:
            continue
        # 新しい SQLite 側の更新を、古い JSON で巻き戻さない。
        if old and _float(old["updated"], 0) >= updated:
            continue

        values = (
            _title(legacy.get("題", "新しい会話")),
            created,
            updated,
            int(bool(legacy.get("しまった", False))),
            _group(legacy.get("組", "")),
            cid,
        )
        if old:
            conn.execute(
                """UPDATE conversations
                   SET title = ?, created = ?, updated = ?, archived = ?, group_name = ?
                   WHERE id = ?""",
                values,
            )
        else:
            conn.execute(
                """INSERT INTO conversations
                   (title, created, updated, archived, group_name, id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                values,
            )
        _replace_turns(conn, cid, legacy.get("やりとり", []))


def _ensure():
    global _READY
    with _INIT_LOCK:
        os.makedirs(os.path.dirname(DB), exist_ok=True)
        os.makedirs(DIR, exist_ok=True)
        conn = _open()
        try:
            _create_schema(conn)
            if not _READY:
                _migrate_legacy(conn)
                _READY = True
            conn.commit()
        finally:
            conn.close()
    return DIR


@contextlib.contextmanager
def _db():
    _ensure()
    conn = _open()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _load(conn, cid, include_deleted=False):
    clauses = ["id = ?"]
    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    row = conn.execute(
        "SELECT * FROM conversations WHERE " + " AND ".join(clauses), (cid,)
    ).fetchone()
    if not row:
        return None
    turns = conn.execute(
        """SELECT role, text, trace, ms, created FROM turns
           WHERE conversation_id = ? ORDER BY position""",
        (cid,),
    ).fetchall()
    return {
        "id": row["id"],
        "題": row["title"],
        "作った": row["created"],
        "更新": row["updated"],
        "しまった": bool(row["archived"]),
        "組": row["group_name"],
        "削除日時": row["deleted_at"],
        "やりとり": [
            {"役": turn["role"], "文": turn["text"], "経過": turn["trace"],
             "ミリ秒": turn["ms"], "時刻": turn["created"]}
            for turn in turns
        ],
    }


def create(title="新しい会話"):
    cid, now = uuid.uuid4().hex[:12], _now()
    with _db() as conn:
        conn.execute(
            """INSERT INTO conversations (id, title, created, updated, archived, group_name)
               VALUES (?, ?, ?, ?, 0, '')""",
            (cid, _title(title), now, now),
        )
        return _load(conn, cid)


def save(conversation):
    """従来 API との互換用。渡された会話全体を1トランザクションで保存する。"""
    cid = _safe_id(conversation["id"])
    now = _now()
    with _db() as conn:
        old = conn.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()
        created = _float(conversation.get("作った"), old["created"] if old else now)
        deleted_at = (
            conversation.get("削除日時")
            if "削除日時" in conversation
            else (old["deleted_at"] if old else None)
        )
        values = (
            _title(conversation.get("題", "新しい会話")),
            created,
            now,
            int(bool(conversation.get("しまった", False))),
            _group(conversation.get("組", "")),
            deleted_at,
            cid,
        )
        if old:
            conn.execute(
                """UPDATE conversations
                   SET title = ?, created = ?, updated = ?, archived = ?, group_name = ?, deleted_at = ?
                   WHERE id = ?""",
                values,
            )
        else:
            conn.execute(
                """INSERT INTO conversations
                   (title, created, updated, archived, group_name, deleted_at, id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
        if "やりとり" in conversation:
            _replace_turns(conn, cid, conversation.get("やりとり") or [])
        return _load(conn, cid, include_deleted=True)


def load(cid, include_deleted=False):
    with _db() as conn:
        return _load(conn, _safe_id(cid), include_deleted)


def listing(include_archived=False, include_deleted=False):
    """新しい順に、会話一覧の見出しだけを返す。"""
    clauses = []
    if not include_deleted:
        clauses.append("c.deleted_at IS NULL")
    if not include_archived:
        clauses.append("c.archived = 0")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _db() as conn:
        rows = conn.execute(
            """SELECT c.id, c.title, c.updated, c.archived, c.group_name, c.deleted_at,
                      COUNT(t.id) AS count
               FROM conversations c
               LEFT JOIN turns t ON t.conversation_id = c.id"""
            + where
            + " GROUP BY c.id ORDER BY c.updated DESC"
        ).fetchall()
    return [
        {"id": row["id"], "題": row["title"], "更新": row["updated"],
         "しまった": bool(row["archived"]), "組": row["group_name"],
         "件数": row["count"], "削除日時": row["deleted_at"]}
        for row in rows
    ]


def add_turn(cid, role, text, trace="", ms=0):
    cid = _safe_id(cid)
    now = _now()
    with _db() as conn:
        conversation = conn.execute(
            "SELECT title FROM conversations WHERE id = ? AND deleted_at IS NULL", (cid,)
        ).fetchone()
        if not conversation:
            return None
        position = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM turns WHERE conversation_id = ?", (cid,)
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO turns (conversation_id, position, role, text, trace, ms, created)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (cid, position, str(role), str(text), str(trace), _int(ms), now),
        )
        title = conversation["title"]
        if title in ("", "新しい会話") and role == "user":
            title = _title(str(text)[:28])
        conn.execute("UPDATE conversations SET title = ?, updated = ? WHERE id = ?", (title, now, cid))
        return _load(conn, cid)


def rename(cid, title):
    cid = _safe_id(cid)
    with _db() as conn:
        conn.execute(
            "UPDATE conversations SET title = ?, updated = ? WHERE id = ? AND deleted_at IS NULL",
            (_title(title), _now(), cid),
        )
        return _load(conn, cid)


def archive(cid, on=True):
    cid = _safe_id(cid)
    with _db() as conn:
        conn.execute(
            "UPDATE conversations SET archived = ?, updated = ? WHERE id = ? AND deleted_at IS NULL",
            (int(bool(on)), _now(), cid),
        )
        return _load(conn, cid)


def fork(cid, upto=None):
    source = load(cid)
    if not source:
        return None
    turns = source.get("やりとり", [])
    if upto is not None:
        turns = turns[:max(0, _int(upto))]
    duplicate = create((source.get("題", "会話") + " の枝")[:60])
    with _db() as conn:
        _replace_turns(conn, duplicate["id"], turns)
        conn.execute(
            "UPDATE conversations SET updated = ? WHERE id = ?", (_now(), duplicate["id"])
        )
        return _load(conn, duplicate["id"])


def remove(cid):
    """会話をゴミ箱へ移す。発話を含む SQLite 行は残るので復元できる。"""
    cid = _safe_id(cid)
    with _db() as conn:
        changed = conn.execute(
            """UPDATE conversations SET deleted_at = ?, updated = ?
               WHERE id = ? AND deleted_at IS NULL""",
            (_now(), _now(), cid),
        ).rowcount
        return bool(changed)


def restore(cid):
    """``remove`` でゴミ箱へ移した会話を戻す。"""
    cid = _safe_id(cid)
    with _db() as conn:
        changed = conn.execute(
            "UPDATE conversations SET deleted_at = NULL, updated = ? WHERE id = ? AND deleted_at IS NOT NULL",
            (_now(), cid),
        ).rowcount
        return bool(changed)


def purge(cid):
    """ゴミ箱の会話を **完全に消す**（戻せない）。ゴミ箱に入っているものだけ消せる。発話は CASCADE で消える。"""
    cid = _safe_id(cid)
    with _db() as conn:
        changed = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND deleted_at IS NOT NULL", (cid,)
        ).rowcount
        return bool(changed)


def empty_trash(older_than_days=None):
    """ゴミ箱を空にする。older_than_days を渡すと、それより前に捨てたものだけ。消した件数を返す。"""
    with _db() as conn:
        if older_than_days is None:
            return conn.execute("DELETE FROM conversations WHERE deleted_at IS NOT NULL").rowcount
        kijun = _now() - float(older_than_days) * 86400
        return conn.execute(
            "DELETE FROM conversations WHERE deleted_at IS NOT NULL AND deleted_at < ?", (kijun,)
        ).rowcount


def matomete(ids, nani, group_name=""):
    """まとめて: nani = ゴミ箱へ / 戻す / しまう / 出す / 組 。できた件数を返す。"""
    n = 0
    for cid in ids or []:
        try:
            if nani == "ゴミ箱へ":
                n += bool(remove(cid))
            elif nani == "戻す":
                n += bool(restore(cid))
            elif nani == "しまう":
                n += bool(archive(cid, True))
            elif nani == "出す":
                n += bool(archive(cid, False))
            elif nani == "組":
                n += bool(set_group(cid, group_name))
            elif nani == "完全に消す":
                n += bool(purge(cid))
        except Exception:
            continue
    return n


def transcript(cid):
    conversation = load(cid)
    if not conversation:
        return ""
    out = [
        f"# {conversation.get('題', '（無題）')}",
        time.strftime("%Y-%m-%d %H:%M", time.localtime(conversation.get("作った", _now()))),
        "",
    ]
    for turn in conversation.get("やりとり", []):
        who = "あなた" if turn["役"] == "user" else "カーネル"
        out.append(f"## {who}")
        out.append(turn.get("文", ""))
        if turn.get("経過"):
            out.extend(["```", turn["経過"], "```"])
        out.append("")
    return "\n".join(out)


# ---- 組（会話のまとまり）----

def set_group(cid, name):
    cid, name = _safe_id(cid), _group(name)
    with _db() as conn:
        changed = conn.execute(
            """UPDATE conversations SET group_name = ?, updated = ?
               WHERE id = ? AND deleted_at IS NULL""",
            (name, _now(), cid),
        ).rowcount
        return name if changed else None


def groups(include_archived=False):
    tally, latest = {}, {}
    for item in listing(include_archived=include_archived):
        name = item.get("組", "")
        tally[name] = tally.get(name, 0) + 1
        latest[name] = max(latest.get(name, 0), item.get("更新", 0))
    return [
        {"名": name, "件数": count, "更新": latest.get(name, 0)}
        for name, count in sorted(tally.items(), key=lambda item: -latest.get(item[0], 0))
    ]


def rename_group(old, new):
    with _db() as conn:
        return conn.execute(
            """UPDATE conversations SET group_name = ?, updated = ?
               WHERE group_name = ? AND deleted_at IS NULL""",
            (_group(new), _now(), _group(old)),
        ).rowcount
