#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent.py -- 手元モデルと、読み取り専用の道具をつなぐ小さな実行ループ。

書き込み・シェル実行・アプリ操作はここでは扱わない。モデルが道具を
呼んでも、見られる場所は Desktop / Downloads / Documents / このアプリの
記録置き場に限る。変更が必要な依頼は、既存の kernel.py の確認付き経路へ
戻すための材料だけを返す。
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import json
import os
import time
import urllib.request


_HOME = os.path.expanduser("~")
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOTS = tuple(os.path.realpath(os.path.join(_HOME, p)) for p in (
    "Desktop", "Downloads", "Documents",
    os.path.join("Library", "Application Support", "kernel-ai"),
)) + (os.path.realpath(_HERE),)
_ALIASES = {
    "Desktop": os.path.join(_HOME, "Desktop"),
    "デスクトップ": os.path.join(_HOME, "Desktop"),
    "Downloads": os.path.join(_HOME, "Downloads"),
    "ダウンロード": os.path.join(_HOME, "Downloads"),
    "Documents": os.path.join(_HOME, "Documents"),
    "書類": os.path.join(_HOME, "Documents"),
}


def _safe_path(path: str, want_dir: bool | None = None) -> str:
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        raise ValueError("場所が空です")
    raw = _ALIASES.get(path.strip(), path.strip())
    if not os.path.isabs(raw):
        raise ValueError("絶対パスか Desktop / Downloads / Documents を指定してください")
    ap = os.path.realpath(os.path.expanduser(raw))
    if not any(ap == root or ap.startswith(root + os.sep) for root in _ROOTS):
        raise PermissionError("許可された場所の外です")
    if not os.path.exists(ap):
        raise FileNotFoundError(ap)
    if want_dir is True and not os.path.isdir(ap):
        raise NotADirectoryError(ap)
    if want_dir is False and not os.path.isfile(ap):
        raise IsADirectoryError(ap)
    return ap


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def get_current_time(_args: dict) -> str:
    return _json({"日時": _dt.datetime.now().astimezone().isoformat(),
                  "曜日": "月火水木金土日"[_dt.datetime.now().weekday()]})


def list_directory(args: dict) -> str:
    path = _safe_path(args.get("path", "Desktop"), want_dir=True)
    pattern = args.get("pattern", "")
    if not isinstance(pattern, str):
        pattern = ""
    try:
        limit = max(1, min(100, int(args.get("limit", 40))))
    except (TypeError, ValueError):
        limit = 40
    rows = []
    with os.scandir(path) as it:
        for ent in sorted(it, key=lambda e: e.name.casefold()):
            if pattern and not fnmatch.fnmatch(ent.name, pattern):
                continue
            try:
                st = ent.stat(follow_symlinks=False)
                rows.append({"名前": ent.name,
                             "種類": "フォルダ" if ent.is_dir(follow_symlinks=False) else "ファイル",
                             "バイト": st.st_size,
                             "更新": _dt.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat()})
            except OSError:
                continue
            if len(rows) >= limit:
                break
    return _json({"場所": path, "件数": len(rows), "一覧": rows})


def read_text_file(args: dict) -> str:
    path = _safe_path(args.get("path", ""), want_dir=False)
    try:
        limit = max(200, min(20000, int(args.get("max_chars", 12000))))
    except (TypeError, ValueError):
        limit = 12000
    if os.path.getsize(path) > 2_000_000:
        raise ValueError("大きすぎるファイルです（2MB以下だけ読めます）")
    with open(path, "rb") as f:
        raw = f.read(limit * 4 + 1)
    text = raw.decode("utf-8", "replace")
    clipped = len(text) > limit
    return _json({"パス": path, "内容": text[:limit], "省略": clipped})


def find_files(args: dict) -> str:
    root = _safe_path(args.get("root", "Desktop"), want_dir=True)
    pattern = args.get("pattern", "*")
    if not isinstance(pattern, str) or not pattern or len(pattern) > 120:
        raise ValueError("検索パターンが不正です")
    try:
        limit = max(1, min(100, int(args.get("limit", 40))))
    except (TypeError, ValueError):
        limit = 40
    rows = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                p = os.path.join(base, name)
                try:
                    rows.append({"名前": name, "パス": p, "バイト": os.path.getsize(p)})
                except OSError:
                    pass
                if len(rows) >= limit:
                    return _json({"場所": root, "件数": len(rows), "一覧": rows,
                                  "省略": True})
    return _json({"場所": root, "件数": len(rows), "一覧": rows, "省略": False})


TOOLS = [
    {"type": "function", "function": {
        "name": "get_current_time", "description": "現在の日時を返す。",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "list_directory", "description": "許可されたフォルダの中身を一覧する。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Desktop / Downloads / Documents または許可範囲の絶対パス"},
            "pattern": {"type": "string", "description": "任意のファイル名パターン。例: *.pdf"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "read_text_file", "description": "許可された範囲の小さなUTF-8テキストを読む。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "minimum": 200, "maximum": 20000}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "find_files", "description": "許可されたフォルダ以下からファイル名を探す。",
        "parameters": {"type": "object", "properties": {
            "root": {"type": "string"},
            "pattern": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            "required": ["root", "pattern"]}}},
]
_FUNCS = {"get_current_time": get_current_time,
          "list_directory": list_directory,
          "read_text_file": read_text_file,
          "find_files": find_files}


def _call(url: str, payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions",
                                 data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.loads(f.read().decode("utf-8"))


def run(text: str, url: str, model: str = "qwen3.5-35b", max_steps: int = 3,
        timeout: int = 240) -> dict:
    """読み取り専用ツールを最大 max_steps 回だけ実行して答える。"""
    t0 = time.monotonic()
    messages = [
        {"role": "system", "content": (
            "あなたはこのMacの読み取り専用アシスタントです。"
            "必要なら提供された道具を呼び、結果にないことは推測しないでください。"
            "書き込み・削除・実行・送信はできません。日本語で簡潔に答えてください。")},
        {"role": "user", "content": text},
    ]
    trace = []
    for step in range(max(1, min(4, int(max_steps)))):
        left = max(10, int(timeout - (time.monotonic() - t0)))
        try:
            body = _call(url, {"model": model, "messages": messages,
                               "tools": TOOLS, "tool_choice": "auto",
                               "temperature": 0, "max_tokens": 384,
                               "stream": False,
                               "chat_template_kwargs": {"enable_thinking": False}}, left)
        except Exception as e:
            return {"text": "", "error": "%s: %s" % (type(e).__name__, e),
                    "steps": step, "tools": trace,
                    "ms": int((time.monotonic() - t0) * 1000)}
        choices = body.get("choices") or []
        if not choices:
            return {"text": "", "error": "モデルから選択肢が返りませんでした",
                    "steps": step + 1, "tools": trace,
                    "ms": int((time.monotonic() - t0) * 1000)}
        msg = choices[0].get("message") or {}
        calls = msg.get("tool_calls") or []
        if not calls:
            answer = (msg.get("content") or "").strip()
            return {"text": answer, "error": None if answer else "空応答",
                    "steps": step + 1, "tools": trace,
                    "ms": int((time.monotonic() - t0) * 1000)}
        assistant = {"role": "assistant", "content": msg.get("content") or "",
                     "tool_calls": calls}
        messages.append(assistant)
        for call in calls[:4]:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(args, dict):
                    raise ValueError("引数はJSONオブジェクトで指定してください")
                if name not in _FUNCS:
                    raise ValueError("許可されていない道具です")
                result = _FUNCS[name](args)
                ok = True
            except Exception as e:
                result = _json({"error": str(e)})
                ok = False
            call_id = call.get("id") or ("tool-%d" % len(trace))
            messages.append({"role": "tool", "tool_call_id": call_id,
                             "content": result})
            trace.append({"name": name, "ok": ok})
    return {"text": "", "error": "道具の呼び出し回数が上限に達しました",
            "steps": max_steps, "tools": trace,
            "ms": int((time.monotonic() - t0) * 1000)}
