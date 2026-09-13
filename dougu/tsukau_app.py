#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tsukau_app.py -- 動いているカーネル.app に、外から頼む（試験用の運転手）。

  ★ なぜ要るか（2026-09-13 の実測）
    画面を撮る許可（システム設定 → 画面収録）は **アプリの中の python** にしか無い。
    こちらのシェルから `sousa.py` を直に回すと、1手目で必ず止まる。
    → 操作の試験は **アプリ本人に頼む**。実際の道（/ask/stream → 承認の札 → /approve）を
      そのまま通るので、通し試験としても正しい。

  ★ 合鍵（トークン）は 環境変数でもらう。**書き置きしない・公開しない。**
      KERNEL_URL="http://127.0.0.1:50771/?t=..."   （窓の引数から取れる）

  ★ 承認は「する」で自動で返す。**無人の試験専用。**
"""
from __future__ import annotations
import json, os, sys, urllib.parse, urllib.request

URL = os.environ.get("KERNEL_URL", "")


def _saki():
    if not URL:
        raise SystemExit("KERNEL_URL がありません（窓の引数から取ってください）")
    u = urllib.parse.urlparse(URL)
    t = urllib.parse.parse_qs(u.query).get("t", [""])[0]
    return f"{u.scheme}://{u.netloc}", t


def _post(michi: str, obj: dict, stream: bool = False, timeout: int = 900):
    moto, t = _saki()
    req = urllib.request.Request(
        f"{moto}{michi}", data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json", "Cookie": f"kt={t}"})
    return urllib.request.urlopen(req, timeout=timeout)


def kotaeru(ident: str, kotae: str = "する"):
    try:
        _post("/approve", {"id": ident, "答え": kotae}, timeout=20).read()
    except Exception as e:
        print("   （承認を返せませんでした: %s）" % e)


def tanomu(text: str, iu=print, kotae: str = "する") -> dict:
    """アプリに1つ頼んで、終わりまで見る。札が来たら kotae で返す。"""
    r = _post("/ask/stream", {"text": text}, stream=True)
    saigo = {}
    for gyou in r:
        gyou = gyou.strip()
        if not gyou:
            continue
        try:
            m = json.loads(gyou)
        except Exception:
            continue
        if m.get("承認"):
            iu("   ▶ 札: %s → %s" % (m["承認"]["文"], kotae))
            kotaeru(m["承認"]["id"], kotae)
        elif m.get("経過"):
            iu("   " + str(m["経過"]).strip()[:130])
        elif m.get("完了"):
            saigo = m["完了"]
    return saigo


if __name__ == "__main__":
    print(json.dumps(tanomu(" ".join(sys.argv[1:])), ensure_ascii=False, indent=2))
