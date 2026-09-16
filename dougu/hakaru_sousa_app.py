#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_sousa_app.py -- 操作の課題を、動いているアプリに頼んで測る。

確かめは **ファイルが在るか**（画面を通さない）。輪の自己申告は数えない。
承認は「する」で自動で返す。**無人の試験専用。**
"""
from __future__ import annotations
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsukau_app

DESK = os.path.expanduser("~/Desktop")
DOCS = os.path.expanduser("~/Documents")
FUDA = "カーネル試験_0913.txt"


def junbi():
    with open(os.path.join(DESK, FUDA), "w", encoding="utf-8") as f:
        f.write("これは操作の輪の試験に使う紙です。消してかまいません。\n")
    q = os.path.join(DOCS, FUDA)
    if os.path.exists(q):
        os.remove(q)


SHIRUSHI = "カーネル試験0913"


def _mieru(kotoba: str) -> bool:
    """画面に その言葉が見えているか（輪と同じ目で見る）"""
    try:
        import os, sys
        # ★ 2026-09-16: 正は内蔵の写し（外部SSDは日に何度も切れる）。無ければ SSD を見る
        sys.path.insert(0, os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel")
                                                                  if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel"))
        import sousa
        g = sousa._gamen(None)
        return any(kotoba.replace(" ", "") in m["文"].replace(" ", "") for m in g["文字"])
    except Exception as e:
        print("   （確かめられませんでした: %s）" % e)
        return False


def _mae_no_app() -> str:
    try:
        import os, sys
        sys.path.insert(0, os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel")
                                                                  if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel"))
        import hands
        return hands.mae_no_app() or ""
    except Exception:
        return ""


MONDAI = [
    ("Finder: デスクトップの紙を 書類へ 移す",
     f"Finderで デスクトップの {FUDA} を 書類フォルダ に移して",
     junbi,
     lambda: os.path.exists(os.path.join(DOCS, FUDA)) and not os.path.exists(os.path.join(DESK, FUDA))),
    ("メモ: 新しいメモに 印を書く",
     f"メモを開いて、新しいメモに {SHIRUSHI} と書いて",
     None,
     lambda: _mieru(SHIRUSHI)),
    ("Safari: 前に出して 新しいタブを出す",
     "Safariを開いて 新しいタブを出して",
     None,
     lambda: _mae_no_app() == "Safari"),
]


def main():
    maru = 0
    for midashi, tanomi, shitagoshirae, tashikame in MONDAI:
        if shitagoshirae:
            shitagoshirae()
        print("── %s" % midashi)
        print("   頼み: %s" % tanomi)
        t0 = time.time()
        r = tsukau_app.tanomu(tanomi)
        byou = time.time() - t0
        ok = bool(tashikame())
        maru += ok
        print("   返事: %s" % str(r.get("出力", "")).strip().replace("\n", " ")[:160])
        print("   %s  %.0f秒 ／ 機械の確かめ: %s\n" % ("○" if ok else "×", byou, "○" if ok else "×"))
    print("  操作の課題（アプリ経由）: %d/%d" % (maru, len(MONDAI)))
    return 0 if maru == len(MONDAI) else 1


if __name__ == "__main__":
    sys.exit(main())
