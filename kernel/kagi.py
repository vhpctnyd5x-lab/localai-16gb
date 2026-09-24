#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""macOS キーチェーンの秘密を、本人の承認後に指定先へだけ渡す薄い橋。

秘密の取得は ai-keychain の access_broker だけを通す。このモジュールは値を
返さず、表示せず、ログにも書かない。頭脳が見られるのは登録名だけ。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
from types import ModuleType
from typing import Callable

_CANDIDATES = (
    os.path.expanduser("~/.agents/skills/ai-keychain/scripts"),
    os.path.expanduser("~/.Codex/skills/ai-keychain/scripts"),
    os.path.expanduser("~/.claude/skills/ai-keychain/scripts"),
)
_LOCK = threading.Lock()
_MODULES: tuple[ModuleType, ModuleType] | None = None


class KagiError(RuntimeError):
    """秘密値を含まない、利用者へ見せてもよいエラー。"""


def _script_dir() -> str:
    override = os.environ.get("AI_KEYCHAIN_SCRIPTS")
    candidates = ((os.path.expanduser(override),) if override else _CANDIDATES)
    for path in candidates:
        if (os.path.isfile(os.path.join(path, "keychain.py"))
                and os.path.isfile(os.path.join(path, "access_broker.py"))):
            return path
    raise KagiError("ai-keychain の承認ブローカーが見つかりません")


def _load_file(module_name: str, path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise KagiError("ai-keychain を読み込めません")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_modules() -> tuple[ModuleType, ModuleType]:
    """既存ブローカーを読み込む。get_secret を直接呼ぶ入口は作らない。"""
    global _MODULES
    with _LOCK:
        if _MODULES is not None:
            return _MODULES
        path = _script_dir()
        try:
            keychain = _load_file("_kernel_ai_keychain", os.path.join(path, "keychain.py"))
            # access_broker.py は ``import keychain`` する。読み込み中だけ安全な実体を渡し、
            # 同名の既存モジュールがあれば必ず元へ戻す。
            old = sys.modules.get("keychain")
            sys.modules["keychain"] = keychain
            try:
                broker = _load_file("_kernel_ai_access_broker",
                                    os.path.join(path, "access_broker.py"))
            finally:
                if old is None:
                    sys.modules.pop("keychain", None)
                else:
                    sys.modules["keychain"] = old
        except KagiError:
            raise
        except Exception:
            raise KagiError("ai-keychain を読み込めません") from None
        _MODULES = (keychain, broker)
        return _MODULES


def ichiran() -> list[str]:
    """登録名だけを返す。秘密値は取得しない。"""
    try:
        keychain, _broker = _load_modules()
        names = keychain.list_secrets()
    except KagiError:
        raise
    except Exception:
        raise KagiError("鍵の名前一覧を読めませんでした") from None
    return sorted({str(name) for name in names if str(name).strip()})


def _saki_no_namae(saki: Callable[[str], object]) -> str:
    module = getattr(saki, "__module__", "")
    name = getattr(saki, "__qualname__", "") or getattr(saki, "__name__", "")
    if not name:
        name = type(saki).__name__
    label = (module + "." + name).strip(".")
    return label[:120] or "指定された受け渡し先"


def tsukau(name: str, saki: Callable[[str], object]) -> dict:
    """本人が許可した秘密を ``saki`` へ1回だけ渡し、安全な成否だけ返す。

    ``saki`` の戻り値は、秘密を含む可能性があるため必ず捨てる。失敗時も元の
    例外文は外へ出さない。
    """
    name = str(name or "").strip()
    if not name:
        raise KagiError("鍵の名前が空です")
    if not callable(saki):
        raise KagiError("受け渡し先は呼び出せるものにしてください")
    label = _saki_no_namae(saki)
    try:
        _keychain, broker = _load_modules()
        secret = broker.request_secret(
            name, requester="LocalAI kernel", reason=label + " へ渡す")
    except BaseException:
        return {"使えた": False, "名前": name, "先": label,
                "エラー": "承認またはキーチェーンの確認に失敗しました"}
    if secret is None:
        return {"使えた": False, "名前": name, "先": label,
                "エラー": "許可されなかったか、登録されていません"}
    try:
        saki(secret)
    except BaseException:
        return {"使えた": False, "名前": name, "先": label,
                "エラー": "受け渡し先で失敗しました"}
    finally:
        secret = None
    return {"使えた": True, "名前": name, "先": label, "エラー": None}


if __name__ == "__main__":
    # 一覧は名前だけ。値を表示する入口は意図的に置かない。
    for _name in ichiran():
        print(_name)
