#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nvkey.py -- （nvsetup と同じ判定を、カーネルの画面から使うための部品）

もとは NVIDIA の鍵を ~/.nvidia.env に入れて、その場で動作確認する。

  ターミナルで  nvsetup  と打つだけ。

  やること:
    1. いまの状態を調べて日本語で言う
    2. 新しい鍵を受け取る（打った文字は画面に出ない）
    3. 形を確かめる → 一覧を叩く → 推論を叩く
    4. 3つ全部通ったときだけ保存する（通らない鍵で上書きしない）

  なぜ要るか:
    「鍵を入れ直したのに動かない」が繰り返し起きている。
    原因はたいてい鍵の "種類" 違いで、一覧(/v1/models)は通るのに
    推論(/chat/completions)だけ 403 になる。見た目では区別がつかない。
    このツールは推論まで実際に叩くので、その場で白黒がつく。
"""
import json, os, ssl, sys, urllib.error, urllib.request

ENV = os.path.expanduser("~/.nvidia.env")
LIST = "https://integrate.api.nvidia.com/v1/models"
CHAT = "https://integrate.api.nvidia.com/v1/chat/completions"
PROBE = "nvidia/nemotron-3.5-lightning-30b-a3b"   # いちばん軽いモデルで試す


def ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def read_env():
    if not os.path.exists(ENV):
        return None
    try:
        for line in open(ENV, encoding="utf-8"):
            line = line.strip()
            if line.startswith("NVIDIA_API_KEY"):
                return line.partition("=")[2].strip().strip('"').strip("'") or None
    except OSError:
        return None
    return None


def katachi(k):
    """形だけ見る。ここで落ちるものは通信するまでもない"""
    if not k:
        return "鍵がからっぽです"
    if not k.isascii():
        return ("鍵に日本語が入っています。説明の例文をそのまま貼っていませんか。\n"
                "   nvapi- で始まる長い文字列が本物です")
    if " " in k or "\t" in k:
        return "鍵に空白が混ざっています。写し間違いかもしれません"
    if not k.startswith("nvapi-"):
        return (f"鍵が nvapi- で始まっていません（いまは {k[:6]!r} で始まっています）。\n"
                "   build.nvidia.com で作った鍵は必ず nvapi- で始まります")
    if len(k) < 40:
        return f"鍵が短すぎます（{len(k)}文字）。途中で切れていませんか"
    return None


def call(url, key, body=None, timeout=40):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx()) as r:
            return 200, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode()[:200]
        except Exception:
            return e.code, ""
    except Exception as e:
        return 0, str(e)[:200]


def shindan(k):
    """一覧と推論を両方叩いて、どこで落ちるかを特定する。
    戻り: (使えるか, 説明)"""
    bad = katachi(k)
    if bad:
        return False, "【形】" + bad


    code, d = call(LIST, k)
    if code == 401:
        return False, ("【一覧】401。鍵そのものが拒まれました。\n"
                       "   写し間違いか、すでに失効させた古い鍵です")
    if code != 200:
        return False, f"【一覧】{code} で通りませんでした： {str(d)[:120]}"
    n = len(d.get("data", [])) if isinstance(d, dict) else 0


    code, d = call(CHAT, k, {"model": PROBE, "max_tokens": 8,
                             "messages": [{"role": "user", "content": "hi"}]})
    if code == 200:

        return True, "3つとも通りました"
    if code == 403:
        return False, (
            "【推論】403。**これが今まさに起きている症状です。**\n"
            "   一覧は見えるのに推論だけ拒まれる＝鍵の『種類』が違います。\n"
            "   NGC で作った鍵は、一覧は見られても推論は通りません。\n"
            "   直し方:\n"
            "     1. build.nvidia.com を開く\n"
            "     2. 使いたいモデルの**ページ**を開く（一覧ページではなく個別ページ）\n"
            "     3. そのページの中の「Get API Key」を押して作る\n"
            "   ※ 無料ぶんを使い切っている場合も 403 になります")
    if code == 429:
        return False, "【推論】429。回数制限です。少し待ってからやり直してください"
    return False, f"【推論】{code}： {str(d)[:150]}"


def save(k):
    old = None
    if os.path.exists(ENV):
        old = open(ENV, encoding="utf-8").read()
    lines, done = [], False
    for line in (old or "").splitlines():
        if line.strip().startswith("NVIDIA_API_KEY"):
            lines.append(f"NVIDIA_API_KEY={k}"); done = True
        else:
            lines.append(line)
    if not done:
        lines.append(f"NVIDIA_API_KEY={k}")
    if old is not None:
        open(ENV + ".bak", "w", encoding="utf-8").write(old)
    with open(ENV, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    os.chmod(ENV, 0o600)      # 本人だけが読める


