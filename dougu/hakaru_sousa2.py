#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_sousa2.py -- 物差し: 操作の輪の課題を増やす（メモ・Safari・Finder でファイルを動かす）。

  ★ 決めごと
    ・終わりの形は **機械で確かめる**。「できたと言った」は数えない。
      いちばん強いのは ファイルが在るか（画面を通さない）。
    ・**承認は自動**（shounin.JIDOU）。これは **無人の試験専用**。アプリからは絶対に立てない。
    ・手元のモデルは **すでに動いているもの**（127.0.0.1:8080）を使い回す。2本目は立てない（16GB）。
    ・1手あたりの秒数を出す。熱いときに 60〜80秒/手 が壁だった（2026-09-12）。

  使い方:  ./hashiru_sousa2.sh
"""
from __future__ import annotations
import json, os, shutil, sys, time

sys.path.insert(0, "/Volumes/Mac Windows/LocalAI/kernel")
import shounin
shounin.JIDOU = True          # ← 無人の試験だけ。アプリからは立てない
import sousa, hands

DESK = os.path.expanduser("~/Desktop")
DOCS = os.path.expanduser("~/Documents")
FUDA = "カーネル試験_0913.txt"
SHIRUSHI = "カーネル試験0913"


def _junbi_file():
    p = os.path.join(DESK, FUDA)
    with open(p, "w", encoding="utf-8") as f:
        f.write("これは操作の輪の試験に使う紙です。消してかまいません。\n")
    q = os.path.join(DOCS, FUDA)
    if os.path.exists(q):
        os.remove(q)


def _mieru(kotoba: str) -> bool:
    """画面に その言葉が見えているか（輪と同じ目で見る）"""
    try:
        g = sousa._gamen(None)
        return any(kotoba.replace(" ", "") in m["文"].replace(" ", "") for m in g["文字"])
    except Exception:
        return False


# ★ 課題は「GUI でしかできないこと」だけにする（2026-09-14）
#   ファイルを動かす課題を入れていたが、これは **道具（kernel の うつす）で 1秒** で済む。
#   GUI にやらせると 12手・600秒かけて毎回失敗していた。課題の作り方が間違っていた。
#   操作の輪は「アプリの画面の中でしかできないこと」に使う。
# (見出し, 目当て, 下ごしらえ, 終わりの形を確かめる)
MONDAI = [
    ("メモ: 新しいメモに 印を書く",
     f"メモを開いて、新しいメモに {SHIRUSHI} と書いて",
     None,
     lambda: _mieru(SHIRUSHI)),

    ("Safari: 前に出して 新しいタブを出す",
     "Safariを開いて 新しいタブを出して",
     None,
     lambda: (hands.mae_no_app() or "") == "Safari"),

    ("計算機: 12×34 を計算して 答えを読む",
     "計算機を開いて 12×34 を計算して、答えを教えて",
     None,
     lambda: _mieru("408")),
]


def main():
    print("  ※ 承認は自動（無人の試験）。手元のモデルは動いているものを使い回す\n")
    maru = 0
    for midashi, mokuteki, junbi, tashikame in MONDAI:
        if junbi:
            junbi()
        print("── %s" % midashi)
        print("   頼み: %s" % mokuteki)
        t0 = time.time()
        try:
            r = sousa.suru(mokuteki, iu=lambda s: print("   " + s.strip()[:110]))
        except Exception as e:
            print("   × つまずいた: %s: %s\n" % (type(e).__name__, e))
            continue
        byou = time.time() - t0
        te = len(r.get("手") or [])
        ok = bool(tashikame())
        maru += ok
        print("   %s  %s ／ %d手・%.0f秒（1手 %.0f秒）"
              % ("○" if ok else "×", str(r.get("報告"))[:60], te, byou, byou / max(te, 1)))
        print("   輪の自己申告: %s ／ 機械の確かめ: %s\n"
              % ("できた" if r.get("できた") else "できない", "○" if ok else "×"))
    print("  操作の課題: %d/%d" % (maru, len(MONDAI)))
    return 0 if maru == len(MONDAI) else 1


if __name__ == "__main__":
    sys.exit(main())
