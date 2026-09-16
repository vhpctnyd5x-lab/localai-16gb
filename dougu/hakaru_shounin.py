#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_shounin.py -- 物差し: machine の用件が「承認の札」を通るか。

2026-09-13 の実測で見つけた穴を、二度と開けないための物差し。
  画面（カーネル.app）から「計算機を開いて」と頼むと main.route は machine の
  「アプリをひらく」に当たる。既定の `確認: False` で素通りし、**札を1枚も出さずに**
  計算機が開いていた（chats.sqlite3 の記録: 1500ミリ秒・【アプリをひらく】）。

画面は触らない。部品（実際にアプリを開く関数）は差し替えて、
「聞いたか」「動かしたか」だけを見る。
"""
from __future__ import annotations
import os, sys, threading

import os, sys
# ★ 2026-09-16: 正は内蔵の写し（外部SSDは日に何度も切れる）。無ければ SSD を見る
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel")
                                                if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import machine, shounin, main


def _shibai(name: str, kotae: str | None, gamen: bool, kakunin: bool):
    """1回ぶんの芝居。返り: (聞かれた文 or None, 動いたか, machine.run の返事)"""
    kiita = []
    ugoita = []
    moto = machine.OPS[name]
    machine.OPS[name] = ((lambda slots: ugoita.append(True) or "にせもの を開きました"), moto[1])
    shounin.TOIKAKE = None
    import builtins
    moto_input = builtins.input
    # 端末のときは input() で聞く。聞いたことを数えるため、ここで受け止める
    # （無人なので「答えない」＝ EOF。shounin は「やめる」に倒す）
    def nise_input(prompt=""):
        kiita.append(str(prompt))
        raise EOFError
    try:
        if gamen:
            def toikake(obj):
                kiita.append(obj["承認"]["文"])
                # 画面の代わりに、別の糸から答える
                threading.Timer(0.01, shounin.kotaeru, (obj["承認"]["id"], kotae)).start()
            shounin.TOIKAKE = toikake
        else:
            builtins.input = nise_input
        ask = main._machine_ask(machine.kiken(name), {"確認": kakunin})
        shounin.hajimeru()
        try:
            ans = machine.run(name, {"アプリ": "にせもの"}, confirm=ask)
        finally:
            shounin.owaru()
        return (kiita[0] if kiita else None), bool(ugoita), ans
    finally:
        machine.OPS[name] = moto
        shounin.TOIKAKE = None
        builtins.input = moto_input


MONDAI = [
    # (見出し, 用件, 画面か, 確認, 答え, 期待: 聞かれるか, 動くか)
    ("画面・外・確認off → 札が出て、する で動く", "アプリをひらく", True,  False, "する",   True,  True),
    ("画面・外・やめる → 動かない",                "アプリをひらく", True,  False, "やめる", True,  False),
    ("画面・跡・やめる → 動かない",                "うちこむ",       True,  False, "やめる", True,  False),
    ("端末・外・確認off → これまで通り聞かずに動く", "アプリをひらく", False, False, None,     False, True),
    ("端末・跡・確認off → それでも聞く（無人なら動かない）", "うちこむ", False, False, None,   True,  False),
]


def main_():
    maru = 0
    for midashi, name, gamen, kakunin, kotae, k_machi, u_machi in MONDAI:
        try:
            kiita, ugoita, ans = _shibai(name, kotae, gamen, kakunin)
        except Exception as e:
            print("  ×  %s\n       つまずいた: %s: %s" % (midashi, type(e).__name__, e))
            continue
        ok = (bool(kiita) == k_machi) and (ugoita == u_machi)
        maru += ok
        print("  %s  %s" % ("○" if ok else "×", midashi))
        if not ok:
            print("       聞かれた: %r（期待 %s） / 動いた: %s（期待 %s） / 返事: %s"
                  % (kiita, k_machi, ugoita, u_machi, str(ans)[:60]))
    print("\n  承認の札: %d/%d" % (maru, len(MONDAI)))
    return 0 if maru == len(MONDAI) else 1


if __name__ == "__main__":
    sys.exit(main_())
