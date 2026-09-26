#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加道具が返す effects を親側の門番へ渡す前の共通検査。"""
from __future__ import annotations

import os
import re
import shlex
import tempfile
from pathlib import Path
from typing import Any, Callable


class EffectRejected(ValueError):
    pass


_RISK = {"見る": 0, "戻せる": 1, "戻せない": 2, "禁止": 3}


def _inside(path: str, root: str) -> bool:
    try:
        Path(path).relative_to(Path(root))
        return True
    except ValueError:
        return False


def _has_symlink(raw: str) -> bool:
    path = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not path.is_absolute():
        path = Path.cwd() / path
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def inspect_effects(
    effects: Any,
    declared_risk: str,
    *,
    canonicalize: Callable[[str], str],
    is_protected: Callable[[str], bool],
    is_secret: Callable[[str], bool],
    kensa: Callable[[dict], str],
    contains_secret: Callable[[Any], bool],
    scope_roots: list[str] | None = None,
) -> dict:
    if type(effects) is not list or len(effects) > 32:
        raise EffectRejected("effects の数が不正です")
    if declared_risk not in _RISK or declared_risk == "禁止":
        declared_risk = "戻せない"
    roots = [canonicalize(root) for root in (scope_roots or [])]
    normalized, risk = [], declared_risk
    for raw in effects:
        if type(raw) is not dict or type(raw.get("type")) is not str:
            raise EffectRejected("effect の形が不正です")
        kind = raw["type"]
        if kind == "write" and set(raw) == {"type", "path", "text"} and type(raw["path"]) is str and type(raw["text"]) is str:
            path = raw["path"]
            if len(path) > 4096 or len(raw["text"].encode("utf-8")) > 256 * 1024 or contains_secret(raw["text"]):
                raise EffectRejected("書き込み内容が大きすぎるか秘密を含みます")
            gate_tool = {"書く": {"path": path, "text": raw["text"]}}
        elif kind == "delete" and set(raw) == {"type", "path"} and type(raw["path"]) is str:
            path = raw["path"]
            if len(path) > 4096: raise EffectRejected("削除先のパスが長すぎます")
            gate_tool = {"命令": {"cmd": "rm -- " + shlex.quote(path)}}
        elif kind == "send" and set(raw) == {"type", "to", "text", "transport"} and all(type(raw[k]) is str for k in ("to", "text", "transport")):
            if (raw["transport"] not in {"メール", "メッセージ"} or not re.fullmatch(r"[^\s「」『』、。]{1,40}", raw["to"])
                    or any(char in raw["to"] for char in ('"', "\\"))
                    or not raw["text"].strip() or any(char in raw["text"] for char in ('"', "\\", "\n", "\r", "「", "」", "『", "』"))):
                raise EffectRejected("送信先・方法・本文が不正です")
            if len(raw["text"].encode("utf-8")) > 8 * 1024 or contains_secret(raw):
                raise EffectRejected("送信内容が大きすぎるか秘密を含みます")
            gate_tool = {"用件": {"text": f"{raw['to']}さんに{raw['transport']}で「{raw['text']}」を送る"}}
            path = None
        else:
            raise EffectRejected("許可していない effect です")
        own_risk = kensa(gate_tool)
        if own_risk == "禁止":
            raise EffectRejected("門番が禁止した effect です")
        if path is not None:
            symlink_path = os.path.expandvars(os.path.expanduser(path))
            if not os.path.isabs(symlink_path):
                symlink_path = str(Path.home() / symlink_path)
            if _has_symlink(symlink_path):
                raise EffectRejected("シンボリックリンク先は扱えません")
            try:
                canonical = canonicalize(path)
            except Exception as error:
                raise EffectRejected("effect のパスが不正です") from error
            if is_protected(canonical) or is_secret(canonical):
                raise EffectRejected("保護先または秘密のパスです")
            if not roots or not any(_inside(canonical, root) for root in roots):
                raise EffectRejected("ユーザーが指定した対象範囲の外です")
            normalized.append({**raw, "path": canonical})
        else:
            normalized.append(dict(raw))
        if _RISK.get(own_risk, 2) > _RISK.get(risk, 2):
            risk = own_risk
    return {"effects": normalized, "risk": risk, "ok": True}


def _self_test() -> None:
    canon = lambda value: os.path.realpath(os.path.expanduser(value))
    denied = lambda value: value.endswith("/kernel/config") or value.endswith("/.groq.env")
    def gate(tool):
        value = next(iter(tool.values()))
        if value.get("path", "").endswith("/kernel/config"):
            return "禁止"
        return "戻せる" if "書く" in tool else "戻せない"
    args = dict(canonicalize=canon, is_protected=denied, is_secret=denied, kensa=gate,
                contains_secret=lambda value: value == "secret", scope_roots=["/private/tmp/tsuika"])
    safe = inspect_effects([{"type": "write", "path": "/private/tmp/tsuika/report.txt", "text": "ok"}], "見る", **args)
    assert safe["risk"] == "戻せる"
    attacks = [
        {"type": "write", "path": "/private/tmp/tsuika/../kernel/config", "text": "x"},
        {"type": "write", "path": "/private/tmp/tsuika/report.txt", "text": "secret"},
        {"type": "exec", "cmd": "echo escape"},
    ]
    for effect in attacks:
        try: inspect_effects([effect], "見る", **args)
        except EffectRejected: pass
        else: raise AssertionError("禁止すべき effect を拒否しませんでした")
    sent = inspect_effects([{"type": "send", "to": "青木", "text": "確認しました", "transport": "メール"}], "見る", **args)
    assert sent["risk"] == "戻せない"
    with tempfile.TemporaryDirectory(prefix="nouryoku-link-") as temporary:
        root = Path(os.path.realpath(temporary)); target = root / "target.txt"; link = root / "link.txt"
        target.write_text("fixture", encoding="utf-8"); link.symlink_to(target)
        try:
            inspect_effects([{"type": "write", "path": str(link), "text": "x"}], "見る",
                            canonicalize=canon, is_protected=lambda _value: False, is_secret=lambda _value: False,
                            kensa=gate, contains_secret=lambda _value: False, scope_roots=[temporary])
        except EffectRejected: pass
        else: raise AssertionError("シンボリックリンク先を拒否しませんでした")


if __name__ == "__main__":
    _self_test()
    print("nouryoku: ok")
