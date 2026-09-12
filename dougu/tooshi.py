#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dougu/tooshi.py -- 通し試験。アプリと同じ入口 main.route() に頼み文を入れ、正しい道具に振り分けられるかを見る。
   物差し（hakaru*.py）は道具を直接呼ぶので、ここで「入口→振り分け→道具」がつながっていることを確かめる。"""
import io, os, sys, csv, shutil, contextlib, time, re
K = "/Volumes/Mac Windows/LocalAI/kernel"; sys.path.insert(0, K); os.chdir(K)
import main, settings as S
D = os.path.expanduser("~/Desktop/dougu_shiken"); shutil.rmtree(D, ignore_errors=True); os.makedirs(D)
with io.open(os.path.join(D, "uriage.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f); w.writerow(["品名", "分類", "個数", "単価"]); w.writerows([("りんご", "果物", 3, 120), ("みかん", "果物", 5, 80), ("ぶどう", "果物", 2, 300)])
cfg = S.load(); cfg["覚える"] = False; cfg["考える様子"] = True
ctx = {"設定": cfg, "記憶": None, "会話": [], "kernel": main.kernel}
S._apply(cfg, ctx)
KADAI = [
 ("ターミナル", "ターミナルで ~/Desktop/dougu_shiken にあるファイルを一覧して", "uriage.csv"),
 ("表",        "%s/uriage.csv の 個数 の列の合計を出して" % D, "10"),
 ("Web",       "https://example.com/ を読んで、ページの題は？", "Example Domain"),
 ("数え上げ",   "1から6の目のサイコロを2個ふって、目の和が7になるのは何通り？", "6"),
 ("雑談",      "こんにちは。今日は何をしようか迷っています。", ""),
]
if len(sys.argv) > 1:
    KADAI = [k for k in KADAI if k[0] in sys.argv[1:]]
maru = 0
for kata, toi, kitai in KADAI:
    buf = io.StringIO(); t0 = time.time()
    with contextlib.redirect_stdout(buf):
        try: main.route(toi, ctx)
        except Exception as e: print("例外:", type(e).__name__, e)
    out = buf.getvalue(); s = time.time() - t0
    # 道（/Users/…/2026-09-12_1949…）に入っている数字を当てないよう、道の行は外して見る（実際に "10" が日時に当たって○になっていた）
    mi = "\n".join(ln for ln in out.splitlines() if "/Users/" not in ln)
    ok = (kitai in mi) if kitai else (len(out.strip()) > 0)
    maru += ok
    print("%-5s %s %5.1f秒  %s" % (kata, "○" if ok else "×", s, out.strip().replace("\n", " ⏎ ")[:220]), flush=True)
print("通し: %d/%d" % (maru, len(KADAI)))
shutil.rmtree(D, ignore_errors=True)
