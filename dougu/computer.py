#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""computer.py -- Kernel 用の「AIカーソル」実行器。

画面を見る部分は ``eyes.py``（macOS Vision）、動かす部分は ``hands.py``
（CGEvent）に任せる。ここでは、AI が提案した操作を一度保留し、画面側で
明示的に許可されたものだけを実行する。

重要な境界:
  * モデルにはシェル、AppleScript、任意のファイル書き込みを渡さない。
  * 座標は画面内だけ。入力は hands.py の安全確認も通す。
  * 保留中の操作は短時間で期限切れになり、一度しか実行できない。
  * observe/find は読み取り専用。操作は必ず prepare -> execute の順。
"""
from __future__ import annotations

import math
import os
import re
import secrets
import threading
import time
from typing import Any

import eyes
import hands


_LOCK = threading.RLock()
_PENDING: dict[str, dict[str, Any]] = {}
_TTL_SEC = 5 * 60
_MAX_PENDING = 8
_MAX_OCR = 160
_MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
_SECRET_LIKE = re.compile(
    r"(?i)(api[_ -]?key|password|passcode|secret|token|authorization|"
    r"sk-[a-z0-9_-]{12,}|sk-ant-[a-z0-9_-]{12,}|nvapi-[a-z0-9_-]{12,}|"
    r"AIza[0-9A-Za-z_-]{20,}|ya29\.[0-9A-Za-z_-]{20,}|"
    r"(?:ghp|github_pat|xox[baprs])-[-a-z0-9_]{12,}|"
    r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
_CLIPBOARD_SHORTCUTS = {"c", "v", "x"}


def _now() -> float:
    return time.time()


def _purge() -> None:
    cutoff = _now()
    for key, item in list(_PENDING.items()):
        if item.get("expires_at", 0) <= cutoff:
            _PENDING.pop(key, None)


def _point(value: Any, name: str) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} は [x, y] で指定してください")
    try:
        nums = [float(value[0]), float(value[1])]
    except (TypeError, ValueError):
        raise ValueError(f"{name} の座標が不正です")
    if not all(math.isfinite(x) for x in nums):
        raise ValueError(f"{name} の座標が不正です")
    return [int(round(nums[0])), int(round(nums[1]))]


def _inside(point: list[int], screen: dict[str, Any]) -> bool:
    return (0 <= point[0] < int(screen["width"])
            and 0 <= point[1] < int(screen["height"]))


def _screen() -> dict[str, int]:
    raw = hands.screen()
    return {"width": int(raw["幅"]), "height": int(raw["高さ"])}


def _element(item: dict[str, Any]) -> dict[str, Any]:
    box = item.get("箱") or {}
    center = item.get("まんなか") or {}
    return {
        "text": str(item.get("文", "")),
        "x": int(center.get("x", 0)),
        "y": int(center.get("y", 0)),
        "width": int(box.get("幅", 0)),
        "height": int(box.get("高さ", 0)),
        "confidence": round(float(item.get("確からしさ", 0)), 3),
    }


def observe(include_image: bool = False, fast: bool = False) -> dict[str, Any]:
    """画面を観測する。AI向けには OCR と座標だけを返す。"""
    path = eyes.shot()
    try:
        seen = eyes.read(path, fast=fast)
        screen = _screen()
        elements = [_element(x) for x in seen.get("文字", [])]
        result: dict[str, Any] = {
            "ok": True,
            "screen": screen,
            "cursor": hands.where(),
            "active_app": hands.mae_no_app(),
            "elements": elements[:_MAX_OCR],
            "elements_truncated": len(elements) > _MAX_OCR,
            "text": str(seen.get("全文", ""))[:12000],
            "scale": seen.get("倍率", 1),
        }
        if include_image:
            with open(path, "rb") as f:
                raw = f.read(_MAX_SCREENSHOT_BYTES + 1)
            if len(raw) <= _MAX_SCREENSHOT_BYTES:
                import base64
                result["image_data_url"] = (
                    "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
                )
            else:
                result["image_error"] = "スクリーンショットが大きすぎます"
        return result
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def find_text(text: str) -> dict[str, Any]:
    """画面上の文字を探す。押すことはしない。"""
    q = str(text or "").strip()
    if not q:
        raise ValueError("探す文字が空です")
    seen = observe(include_image=False, fast=False)
    ql = q.casefold()
    hits = [x for x in seen.get("elements", [])
            if ql == x["text"].strip().casefold()
            or ql in x["text"].casefold()
            or x["text"].casefold() in ql]
    return {"ok": True, "query": q, "hits": hits[:20],
            "screen": seen.get("screen"), "active_app": seen.get("active_app")}


def _key_spec(action: dict[str, Any]) -> dict[str, Any]:
    """keys 配列を hands.key の 1キー+修飾キーへ正規化する。"""
    raw = action.get("keys")
    if isinstance(raw, str):
        raw = [x for x in raw.replace("+", " ").split() if x]
    if not isinstance(raw, list) or not raw:
        key = action.get("key")
        raw = [key] if key else []
    if not raw:
        raise ValueError("keypress にはキーを指定してください")
    mods = {"cmd": False, "shift": False, "opt": False, "ctrl": False}
    aliases = {
        "command": "cmd", "cmd": "cmd", "⌘": "cmd",
        "shift": "shift", "⇧": "shift",
        "option": "opt", "alt": "opt", "opt": "opt", "⌥": "opt",
        "control": "ctrl", "ctrl": "ctrl", "⌃": "ctrl",
    }
    main = []
    for value in raw:
        word = str(value).strip().casefold()
        if word in aliases:
            mods[aliases[word]] = True
        else:
            main.append(word)
    if len(main) != 1:
        raise ValueError("keypress は修飾キーと1つのキーだけにしてください")
    key = main[0]
    allowed = {"return", "enter", "tab", "space", "delete", "escape", "esc",
               "left", "right", "up", "down", "home", "end", "pageup",
               "pagedown", "f1", "f2", "f3", "f4", "f5"}
    if len(key) == 1 and key.isascii() and key.isalnum():
        pass
    elif key not in allowed:
        raise ValueError(f"未対応のキーです: {key}")
    return {"key": key, **mods}


def _canonical(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        raise ValueError("操作はオブジェクトで指定してください")
    name = str(action.get("action") or action.get("操作") or "").strip().lower()
    aliases = {
        "doubleclick": "double_click", "double-click": "double_click",
        "rightclick": "right_click", "right-click": "right_click",
        "key": "keypress", "press": "keypress", "入力": "type",
        "クリック": "click", "移動": "move", "スクロール": "scroll",
    }
    name = aliases.get(name, name)
    allowed = {"move", "click", "double_click", "right_click", "drag",
               "scroll", "type", "keypress", "open_app"}
    if name not in allowed:
        raise ValueError("許可されていない操作です")

    out: dict[str, Any] = {"action": name}
    screen = _screen()
    if name in {"move", "click", "double_click", "right_click"}:
        p = _point(action.get("coordinate", action.get("座標")), "coordinate")
        if not _inside(p, screen):
            raise ValueError("画面の外の座標です")
        out["coordinate"] = p
    elif name == "drag":
        start = _point(action.get("start_coordinate", action.get("開始座標")),
                       "start_coordinate")
        end = _point(action.get("coordinate", action.get("終了座標")), "coordinate")
        if not (_inside(start, screen) and _inside(end, screen)):
            raise ValueError("画面の外の座標です")
        out["start_coordinate"], out["coordinate"] = start, end
    elif name == "scroll":
        try:
            amount = int(action.get("amount", action.get("量", 0)))
        except (TypeError, ValueError):
            raise ValueError("scroll の量が不正です")
        if not amount or abs(amount) > 20:
            raise ValueError("scroll の量は -20〜20 の範囲で指定してください")
        out["amount"] = amount
        if action.get("coordinate") is not None:
            p = _point(action["coordinate"], "coordinate")
            if not _inside(p, screen):
                raise ValueError("画面の外の座標です")
            out["coordinate"] = p
    elif name == "type":
        text = action.get("text", action.get("文字", ""))
        if not isinstance(text, str) or not text or "\x00" in text:
            raise ValueError("type の文字が空か不正です")
        if len(text) > hands.MAX_TYPE:
            raise ValueError(f"一度に打てるのは {hands.MAX_TYPE} 文字までです")
        if _SECRET_LIKE.search(text):
            raise PermissionError("安全のため、秘密情報らしい文字列は AIカーソルから入力しません")
        out["text"] = text
    elif name == "keypress":
        out.update(_key_spec(action))
    elif name == "open_app":
        app = str(action.get("app", action.get("アプリ", ""))).strip()
        if (not app or len(app) > 120
                or any(x in app for x in ("/", "\\", "\x00", '"', "\n", "\r"))):
            raise ValueError("open_app はアプリ名だけ指定してください")
        out["app"] = app
    return out


def _label(action: dict[str, Any]) -> str:
    name = action["action"]
    p = action.get("coordinate")
    if name == "move": return f"カーソルを {p} へ移動"
    if name == "click": return f"{p} をクリック"
    if name == "double_click": return f"{p} をダブルクリック"
    if name == "right_click": return f"{p} を右クリック"
    if name == "drag": return f"{action['start_coordinate']} から {p} へドラッグ"
    if name == "scroll": return f"{action.get('amount')} 行スクロール"
    if name == "type": return f"「{action['text'][:80]}」を入力"
    if name == "keypress":
        keys = [x for x, on in (("⌘", action.get("cmd")),
                                ("⇧", action.get("shift")),
                                ("⌥", action.get("opt")),
                                ("⌃", action.get("ctrl"))) if on]
        return "+".join(keys + [action["key"]]) + " を押す"
    return f"アプリ「{action['app']}」を前面に出す"


def prepare(action: dict[str, Any], reason: str = "") -> dict[str, Any]:
    """操作を検証して保留する。ここではまだマウスもキーも動かさない。"""
    canonical = _canonical(action)
    # 承認ボタンを押すまでに画面の解像度が変わった場合、座標を別の画面へ
    # 誤送信しないように、提案時の画面情報を保留操作へ束ねる。前面アプリは
    # 承認UIへフォーカスが移ることがあるため、実行時の一致条件にはしない。
    context = {"screen": _screen(), "active_app": hands.mae_no_app()}
    with _LOCK:
        _purge()
        if len(_PENDING) >= _MAX_PENDING:
            raise RuntimeError("保留中の操作が多すぎます。先に実行または取消してください")
        ident = secrets.token_urlsafe(18)
        item = {
            "id": ident,
            "action": canonical,
            "label": _label(canonical),
            "reason": str(reason or "")[:300],
            "created_at": _now(),
            "expires_at": _now() + _TTL_SEC,
            "context": context,
        }
        _PENDING[ident] = item
    return {"id": ident, "label": item["label"], "action": canonical,
            "reason": item["reason"], "expires_in_sec": _TTL_SEC,
            "observed_screen": context["screen"],
            "observed_app": context["active_app"]}


def _unsafe_input_app() -> str | None:
    app = hands.mae_no_app()
    if app:
        ok, reason = hands.utte_ii(app)
        if not ok:
            return reason or app
    return None


def _execute(action: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    name = action["action"]
    if name != "open_app" and context:
        expected = context.get("screen") or {}
        current = _screen()
        if (int(current.get("width", 0)) != int(expected.get("width", 0))
                or int(current.get("height", 0)) != int(expected.get("height", 0))):
            raise PermissionError(
                "承認までに画面サイズが変わったため、古い座標の操作を止めました")
    if name == "move":
        result = hands.move(*action["coordinate"])
    elif name == "click":
        result = hands.click(*action["coordinate"])
    elif name == "double_click":
        result = hands.click(*action["coordinate"], double=True)
    elif name == "right_click":
        result = hands.click(*action["coordinate"], right=True)
    elif name == "drag":
        result = hands.drag(*(action["start_coordinate"] + action["coordinate"]))
    elif name == "scroll":
        p = action.get("coordinate")
        result = hands.scroll(action["amount"], *(p or [])) if p else hands.scroll(action["amount"])
    elif name == "type":
        blocked = _unsafe_input_app()
        if blocked:
            raise PermissionError(f"安全のため入力を止めました: {blocked}")
        result = hands.type_text(action["text"])
    elif name == "keypress":
        blocked = _unsafe_input_app()
        if blocked:
            raise PermissionError(f"安全のためキー入力を止めました: {blocked}")
        if action.get("cmd") and action.get("key") in _CLIPBOARD_SHORTCUTS:
            raise PermissionError("安全のためクリップボード操作はAIカーソルから行いません")
        result = hands.key(action["key"], cmd=action["cmd"], shift=action["shift"],
                           opt=action["opt"], ctrl=action["ctrl"])
    elif name == "open_app":
        result = hands.front(action["app"])
    else:
        raise ValueError("操作が不明です")
    return {"ok": True, "result": result, "action": action,
            "cursor": hands.where(), "active_app": hands.mae_no_app()}


def execute(ident: str) -> dict[str, Any]:
    """保留操作を1回だけ実行する。"""
    with _LOCK:
        _purge()
        item = _PENDING.pop(str(ident), None)
    if item is None:
        raise KeyError("操作が見つからないか、期限切れです")
    return _execute(item["action"], item.get("context"))


def cancel(ident: str) -> bool:
    with _LOCK:
        return _PENDING.pop(str(ident), None) is not None
