#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sousa_ippo.py -- 操作の輪の「1手目」だけを見る（何も動かさない）。頭脳が JSON で妥当な手を返すか。"""
import sys, os, json, time
K = "/Volumes/Mac Windows/LocalAI/kernel"; sys.path.insert(0, K)
import sousa
g = sousa._gamen()
print("画面:", g["アプリ"], len(g["文字"]), "個の文字")
# (目当て, 期待する手, 期待する中身)。★ 1回目は「電卓」と頼んだのに例に書いた「テキストエディット」を写した → 例を <アプリ名> の形に
MOKUTEKI = [
 ("電卓を開いて 12×34 を計算して、答えを教えて", "アプリ", "電卓"),
 ("テキストエディットを開いて、新しい書類に「牛乳を買う」と書いて", "アプリ", "テキストエディット"),
 ("いま前に出ているアプリのメニューの「ヘルプ」を押して", "押す", "ヘルプ"),
 ("画面に見えている文字を読んで、いま何のアプリが前にあるか教えて", "できた", "Claude"),
]
maru = 0
for toi, kitai, naka in MOKUTEKI:
    t = time.time(); te, ng = sousa._te_wo_kimeru(toi, [], g, 120); s = time.time() - t
    ok = bool(te) and te.get("手") == kitai and naka in json.dumps(te, ensure_ascii=False)
    maru += ok
    print("%s %5.1f秒  %s → %s  期待=%s/%s" % ("○" if ok else "×", s, toi[:28], json.dumps(te, ensure_ascii=False) if te else ng, kitai, naka))
print("1手目: %d/%d" % (maru, len(MOKUTEKI)))
