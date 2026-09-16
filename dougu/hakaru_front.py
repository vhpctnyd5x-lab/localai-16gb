#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_front.py -- 物差し: 応答しないアプリでも前に出せるか。

2026-09-13 の実測: メモ(Notes)が固まり `osascript ... activate` が 15秒で3回とも落ちた。
輪は「同じ手を3回」と見なして止まった。**道が1本しか無かったのが原因。**
本物のアプリは固めないので、`activate` が返ってこない場面を こちらで作って確かめる。
"""
from __future__ import annotations
import subprocess, sys
import os, sys
# ★ 2026-09-16: 正は内蔵の写し（外部SSDは日に何度も切れる）。無ければ SSD を見る
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel")
                                                if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import hands

MOTO = subprocess.run


def _nise(kotae: str):
    """osascript は必ず時間切れ／open は kotae のとおりに振る舞う にせもの"""
    def run(argv, *a, **k):
        if argv and argv[0] == "osascript":
            raise subprocess.TimeoutExpired(argv, 15)
        if argv and argv[0] == "open":
            class R: pass
            r = R(); r.returncode = 0 if kotae == "ok" else 1; r.stdout = ""; r.stderr = "ひらけない"
            return r
        return MOTO(argv, *a, **k)
    return run


def main():
    maru = 0
    # ① activate が返ってこない → open -a で前に出す
    hands.subprocess.run = _nise("ok")
    try:
        r = hands.front("メモ")
        ok = r.get("ok") and "open -a" in str(r.get("道", ""))
    except Exception as e:
        r, ok = str(e), False
    maru += ok
    print("  %s  activate が返ってこない → open -a に回る（%s）" % ("○" if ok else "×", r))

    # ② どちらも駄目なら、黙って成功したことにしない
    hands.subprocess.run = _nise("ng")
    try:
        hands.front("メモ"); ok2 = False; naka = "例外が出なかった"
    except Exception as e:
        ok2 = True; naka = str(e)[:60]
    maru += ok2
    print("  %s  両方だめなら つまずきとして返す（%s）" % ("○" if ok2 else "×", naka))

    hands.subprocess.run = MOTO
    print("\n  前に出す道: %d/2" % maru)
    return 0 if maru == 2 else 1


if __name__ == "__main__":
    sys.exit(main())
