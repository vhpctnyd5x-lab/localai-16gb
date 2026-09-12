#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shounin.py -- 「承認」の通り道。道具が **人に聞いてから** 動くための、たった1つの入口。

  ★ 決めごと（2026-09-12 方針: パソコンの操作は手元で、確認つき）
    ・押す・打つ・アプリを前に出す・消す・動かす・送る は、実行の前に必ず kiku() を通る。
    ・答えは 3つ: 「する」「全部」「やめる」。「全部」はこの仕事の間だけ全部許す（hajimeru〜owaru の間）。
    ・画面（ui.html）で動いているときは、server.py が TOIKAKE を差し込み、{"承認": …} を流して /approve を待つ。
      端末（cli）で動いているときは input() で聞く。
    ・答えが 180秒来なければ「やめる」。黙って進めない。
"""
from __future__ import annotations
import threading, secrets, time

MATSU_BYOU = 180
JIDOU = False             # 試験専用。本人が「やっていい」と言った無人の試験だけ True にする（アプリからは絶対に立てない）
TOIKAKE = None            # server が差し込む: TOIKAKE({"承認": {"id":…, "文":…}})
_MACHI: dict[str, dict] = {}
_LOCK = threading.Lock()
_ZENBU = threading.local()   # この仕事の間「全部」と言われたか


def hajimeru():
    """1つの仕事の始まり。「全部」の効きめをここでリセットする"""
    _ZENBU.ok = False


def owaru():
    _ZENBU.ok = False


def kotaeru(ident: str, kotae: str) -> bool:
    """画面から答えが来た（/approve）。"""
    with _LOCK:
        m = _MACHI.get(ident)
        if not m:
            return False
        m["答え"] = kotae
        m["event"].set()
        return True


def kiku(bun: str, iu=None) -> bool:
    """「bun をしていい？」と聞く。True=する。"""
    if JIDOU:
        if iu: iu("  ▶ %s（試験: 自動で許可）" % bun)
        return True
    if getattr(_ZENBU, "ok", False):
        if iu: iu("  ▶ %s（全部許す、と言われている）" % bun)
        return True
    if TOIKAKE is None:
        # 端末
        try:
            a = input("  ▶ %s  [y=する / a=この仕事は全部する / n=やめる] " % bun).strip().lower()
        except EOFError:
            a = "n"
        if a == "a":
            _ZENBU.ok = True
            return True
        return a in ("y", "yes", "する")
    ident = secrets.token_urlsafe(12)
    ev = threading.Event()
    with _LOCK:
        _MACHI[ident] = {"event": ev, "答え": None, "文": bun, "時": time.time()}
    try:
        TOIKAKE({"承認": {"id": ident, "文": bun}})
        ok = ev.wait(MATSU_BYOU)
        with _LOCK:
            m = _MACHI.pop(ident, {})
        a = (m.get("答え") or "やめる") if ok else "やめる"
        if a == "全部":
            _ZENBU.ok = True
            return True
        return a == "する"
    except Exception:
        with _LOCK:
            _MACHI.pop(ident, None)
        return False
