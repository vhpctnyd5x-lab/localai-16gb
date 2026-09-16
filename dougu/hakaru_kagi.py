#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kagi.py の物差し。実物の秘密やキーチェーンには触れず、漏れだけを調べる。"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import secrets
import sys

KERNEL = os.environ.get("KERNEL_DIR") or next(
    (d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"),
                 "/Volumes/Mac Windows/LocalAI/kernel")
     if os.path.isfile(os.path.join(d, "server.py"))),
    "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import kagi


class _Keychain:
    def list_secrets(self):
        return ["zeta", "alpha", "alpha", ""]

    def get_secret(self, _name):
        raise AssertionError("承認を飛ばして直接読んだ")


class _Broker:
    def __init__(self, secret):
        self.secret = secret
        self.calls = []
        self.mode = "ok"

    def request_secret(self, name, requester, reason):
        self.calls.append((name, requester, reason))
        if self.mode == "error":
            raise RuntimeError(self.secret)
        if self.mode == "deny":
            return None
        return self.secret


def _contains(value, needle):
    if isinstance(value, dict):
        return any(_contains(k, needle) or _contains(v, needle) for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(_contains(v, needle) for v in value)
    return needle in str(value)


def main():
    # ソースにも結果ファイルにも固定の偽秘密を置かない。
    secret = secrets.token_urlsafe(32)
    keychain, broker = _Keychain(), _Broker(secret)
    original = kagi._MODULES
    out, err, log = io.StringIO(), io.StringIO(), io.StringIO()
    handler = logging.StreamHandler(log)
    root = logging.getLogger()
    root.addHandler(handler)
    checks = []
    results = []
    received = []
    try:
        kagi._MODULES = (keychain, broker)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            checks.append(("一覧は名前だけ", kagi.ichiran() == ["alpha", "zeta"]))

            def destination(value):
                received.append(value == secret)
                return {"捨てるべき戻り値": value}

            results.append(kagi.tsukau("alpha", destination))
            checks.append(("受け渡し先だけに1回渡す", received == [True]))
            checks.append(("承認ブローカーを通る", len(broker.calls) == 1
                           and broker.calls[0][0] == "alpha"
                           and broker.calls[0][1] == "LocalAI kernel"))

            def broken(_value):
                raise RuntimeError(secret)

            results.append(kagi.tsukau("alpha", broken))
            checks.append(("受け渡し先の例外文を隠す", results[-1]["エラー"] == "受け渡し先で失敗しました"))

            broker.mode = "error"
            results.append(kagi.tsukau("alpha", destination))
            checks.append(("承認側の例外文を隠す", results[-1]["エラー"] == "承認またはキーチェーンの確認に失敗しました"))

            broker.mode = "deny"
            results.append(kagi.tsukau("alpha", destination))
            checks.append(("拒否時は渡さない", results[-1]["使えた"] is False and received == [True]))

        checks.append(("printに出ない", secret not in out.getvalue() and secret not in err.getvalue()))
        checks.append(("ログに出ない", secret not in log.getvalue()))
        checks.append(("戻り値に出ない", not _contains(results, secret)))
        checks.append(("例外として外へ出ない", all(isinstance(r, dict) for r in results)))
    finally:
        root.removeHandler(handler)
        kagi._MODULES = original
        secret = None

    ok = sum(1 for _name, passed in checks if passed)
    for name, passed in checks:
        print("%s %s" % ("○" if passed else "×", name))
    print("鍵: %d/%d" % (ok, len(checks)))
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kekka")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "kagi_20260917.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"日付": "2026-09-17", "点": ok, "満点": len(checks),
                   "結果": [{"項目": name, "○": passed} for name, passed in checks]},
                  f, ensure_ascii=False, indent=1)
    print("→", out)
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
