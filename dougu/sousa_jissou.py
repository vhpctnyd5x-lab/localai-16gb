#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sousa_jissou.py -- 操作の輪を **実際に動かす** 試験（マウス・キーボードを動かす）。
   本人が「やっていい」と言ったときだけ走らせる。承認は自動（shounin.JIDOU）。終わったら Claude を前に戻す。"""
import sys, os, json, time, subprocess
K = "/Volumes/Mac Windows/LocalAI/kernel"; sys.path.insert(0, K)
import sousa, shounin, eyes, hands
shounin.JIDOU = True
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "kekka"); os.makedirs(OUT, exist_ok=True)

def osa(*lines):
    try:
        r = subprocess.run(["osascript"] + sum([["-e", l] for l in lines], []), capture_output=True, text=True, timeout=15)
        return (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return "", "時間切れ（ダイアログが開いている？）"


def katazuke(app):
    """自分が開いたアプリを閉じる。返事が無ければ（開くダイアログ等で固まる）止める"""
    out, err = osa('tell application "%s" to quit saving no' % app)
    if err:
        subprocess.run(["killall", app], capture_output=True)
    return out or err or "閉じた"

def gamen_ni(moji):
    s = eyes.look(fast=False)
    return moji in (s.get("全文") or ""), hands.mae_no_app()

import random
A, B = random.randint(11, 29), random.randint(31, 49)
KOTOBA = "牛乳を買う %d" % random.randint(10, 99)   # ★ 毎回ちがう文にする。TextEdit は消していない書類を復元し、前回の文を見て「できた」と言った   # ★ 毎回ちがう式にする。電卓は前回の答えを覚えていて、開いただけで「408」と答えた実測あり
KADAI = [
 ("電卓", "電卓を開いて %d×%d を計算して、答えを教えて" % (A, B),
  lambda r: str(A * B) in (r.get("報告") or "").replace(",", "")),      # 電卓は 1,225 と桁区切りで出す
 ("テキストエディット", "テキストエディットを開いて、新しい書類に「%s」と書いて" % KOTOBA,
  lambda r: KOTOBA in osa('tell application "TextEdit" to get text of front document')[0]),   # 書類の中身を直接読む（OCR は取りこぼす）
 ("Finder", "Finder でデスクトップを開いて",
  lambda r: hands.mae_no_app() == "Finder" and any(k in osa('tell application "Finder" to get name of front window')[0] for k in ("デスクトップ", "Desktop"))),
]
if len(sys.argv) > 1:
    KADAI = [k for k in KADAI if k[0] in sys.argv[1:]]
kekka = []
for na, toi, tashika in KADAI:
    # 前の課題の名残りを消す（開いたままの Finder の窓で「もう済んでいる」になった実測あり）
    osa('tell application "Finder" to close every window')
    for app in ("Calculator", "TextEdit"):
        subprocess.run(["killall", app], capture_output=True)
    if na == "電卓":   # 覚えている前回の答えを消す
        hands.front("Calculator"); time.sleep(0.8); hands.key("escape"); hands.key("escape"); time.sleep(0.3)
        osa('tell application "Calculator" to quit'); time.sleep(0.5)
    osa('tell application "Claude" to activate'); time.sleep(0.8)
    print("=== %s: %s" % (na, toi), flush=True)
    r = sousa.suru(toi, iu=lambda m: print(m, flush=True))
    try: ok = bool(tashika(r))
    except Exception as e: ok = False; print("  確かめでエラー:", e)
    print("%s %s %5.1f秒  報告=%r  手=%d" % ("○" if ok else "×", na, r["ミリ秒"] / 1000, (r.get("報告") or "")[:80], len(r.get("手") or [])), flush=True)
    kekka.append({"課題": na, "問": toi, "○": ok, "秒": r["ミリ秒"] / 1000, "報告": r.get("報告"), "手": r.get("手")})
    # 後片づけ（自分が開いたものだけ）
    if na == "テキストエディット":
        print("  片づけ:", katazuke("TextEdit"))
    if na == "電卓":
        print("  片づけ:", katazuke("Calculator"))
json.dump(kekka, open(os.path.join(OUT, "sousa.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("操作: %d/%d" % (sum(1 for x in kekka if x["○"]), len(kekka)))
osa('tell application "Claude" to activate')
