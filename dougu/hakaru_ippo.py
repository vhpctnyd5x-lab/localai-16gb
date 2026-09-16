#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_ippo.py -- 1手ぶんの秒を、目（画面を見る）と 頭（手を決める）に分けて測る。

2026-09-13: 1手 115〜124秒 だった。どちらが重いか 推測で語らないための物差し。
画面は見るだけ（押す・打つはしない）。承認も要らない。
"""
from __future__ import annotations
import sys, time
import os, sys
# ★ 2026-09-16: 正は内蔵の写し（外部SSDは日に何度も切れる）。無ければ SSD を見る
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel")
                                                if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import sousa

MOKUTEKI = "メモを開いて、新しいメモに カーネル試験0913 と書いて"


def main():
    for ban in (1, 2):
        t = time.time(); g = sousa._gamen(None); me = time.time() - t
        t = time.time()
        te, ng = sousa._te_wo_kimeru(MOKUTEKI, [], g, 120, fukasa=sousa.FUKASA_TE)
        atama = time.time() - t
        print("  %d回目: 目 %.1f秒 ／ 頭 %.1f秒 ／ 見えた文字 %d個 ／ 前のアプリ %s"
              % (ban, me, atama, len(g["文字"]), g["アプリ"]))
        print("        頭の返し: %s" % (str(te) if te else ng)[:90])
    # 深さ2 だといくらか（困った時に払う値段）
    t = time.time(); g = sousa._gamen(None); me = time.time() - t
    t = time.time(); te, ng = sousa._te_wo_kimeru(MOKUTEKI, [], g, 180, fukasa=2); atama = time.time() - t
    print("  深さ2: 目 %.1f秒 ／ 頭 %.1f秒" % (me, atama))
    return 0


if __name__ == "__main__":
    sys.exit(main())
