#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dougu/hakaru.py -- 「表」と「文章」の道具（kernel/shigoto.py）の物差し。各10課題・機械採点。
   ★ 採点は「報告の文か、成果物の中身に、期待した値があるか」。曖昧な課題（要約など）は入れない。"""
import json, io, os, sys, time, shutil, csv, re
K = "/Volumes/Mac Windows/LocalAI/kernel"; sys.path.insert(0, K)
import shigoto
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "kekka"); os.makedirs(OUT, exist_ok=True)
D = os.path.expanduser("~/Desktop/dougu_shiken"); shutil.rmtree(D, ignore_errors=True); os.makedirs(D)

# ── 素材 ──
rows = [("りんご", "果物", 3, 120), ("みかん", "果物", 5, 80), ("ぶどう", "果物", 2, 300),
        ("にんじん", "野菜", 4, 60), ("たまねぎ", "野菜", 6, 40), ("トマト", "野菜", 3, 150)]
with io.open(os.path.join(D, "uriage.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f); w.writerow(["品名", "分類", "個数", "単価"]); w.writerows(rows)
bun = ["2026年9月1日 朝の会議。参加者は5人。", "予算は120万円で決まった。", "次の会議は2026年9月15日。",
       "宿題: 資料を3部コピーする。", "宿題: 会場をおさえる。", "2026年9月1日 朝の会議。参加者は5人。", "メモおわり。"]
io.open(os.path.join(D, "memo.txt"), "w", encoding="utf-8").write("\n".join(bun) + "\n")
C = os.path.join(D, "uriage.csv"); M = os.path.join(D, "memo.txt")

KADAI = [
 ("表", "%s の 個数 の列の合計を出して" % C, ["23"]),
 # ★ 期待の並びは「全部あること」(AND)。["125.0","125"] と書いて 125.0 の正答を×にしていた（3回目の測定で発覚）
 ("表", "%s の 単価 の平均を出して（小数1桁）" % C, ["125.0"]),
 ("表", "%s で 単価がいちばん高い品名は？" % C, ["ぶどう"]),
 ("表", "%s で 個数が3より多い行は何行？" % C, ["3"]),
 ("表", "%s を 単価の高い順に並べ替えて、先頭の品名を出して" % C, ["ぶどう"]),
 ("表", "%s に 金額（個数×単価）の列を足して、新しいCSVとして保存して" % C, ["金額", "360"]),
 ("表", "%s を 分類ごとに 個数を合計して出して" % C, ["10", "13"]),
 ("表", "%s は何行ある？（見出しを除く）" % C, ["6"]),
 ("表", "%s から 品名に「り」を含む行だけ抜き出して出して" % C, ["りんご"]),
 ("表", "%s を JSON に変換して保存して" % C, ["\"品名\"", "りんご"]),
 ("文章", "%s は何行ある？" % M, ["7"]),
 ("文章", "%s の文字数（改行を除く）を数えて" % M, [str(sum(len(x) for x in bun))]),
 ("文章", "%s から「宿題」を含む行だけ抜き出して出して" % M, ["3部コピー", "会場"]),
 ("文章", "%s の中の「会議」を「打ち合わせ」に置き換えて、新しいファイルに保存して" % M, ["打ち合わせ"]),
 ("文章", "%s から 日付（2026年◯月◯日）を全部抜き出して出して" % M, ["9月1日", "9月15日"]),
 ("文章", "%s の 重複している行を取り除いて、新しいファイルに保存して" % M, ["メモおわり"]),
 ("文章", "%s の 各行の先頭に 番号（1. 2. …）を付けて、新しいファイルに保存して" % M, ["1. ", "7. "]),
 ("文章", "%s の中に「万円」はいくつ出てくる？" % M, ["1"]),
 ("文章", "%s の 行を 五十音順に並べ替えて、新しいファイルに保存して" % M, ["メモおわり"]),
 ("文章", "%s の内容を HTML の箇条書き（ul/li）にして保存して" % M, ["<li>", "会議"]),
]
if len(sys.argv) > 1:
    KADAI = KADAI[:int(sys.argv[1])]

def naka(paths):
    s = ""
    for p in paths:
        try: s += io.open(p, encoding="utf-8").read()[:5000]
        except Exception: pass
    return s

kekka = []; maru = 0
for i, (kata, toi, kitai) in enumerate(KADAI):
    r = shigoto.suru(toi, timeout=150)
    honbun = (r.get("報告") or "") + "\n" + naka(r.get("成果物") or [])
    # ★ 数は「3より多い」のような条件の写しに当てない（実際に 7行（誤）を ○ にしていた）
    kazu = set(shigoto._kazu_dake(honbun))
    ok = r.get("できた", False) and all((k in kazu) if re.fullmatch(r"-?\d+(?:\.\d+)?", k) else (k in honbun) for k in kitai)
    maru += ok
    print("%2d %-3s %s %5.1f秒  %s  期待=%s  報告=%r" % (i + 1, kata, "○" if ok else "×", r["ミリ秒"] / 1000, r.get("確かめ", ""), kitai, (r.get("報告") or r.get("エラー") or "")[:50]), flush=True)
    kekka.append({"型": kata, "問": toi, "期待": kitai, "○": ok, "秒": r["ミリ秒"] / 1000, "報告": r.get("報告"), "成果物": r.get("成果物"), "経過": r.get("経過"), "エラー": r.get("エラー")})
json.dump(kekka, open(os.path.join(OUT, "hyou_bunshou.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for kata in ("表", "文章"):
    g = [x for x in kekka if x["型"] == kata]
    if g: print("%s: %d/%d = %.0f%%  平均 %.0f秒" % (kata, sum(1 for x in g if x["○"]), len(g), 100 * sum(1 for x in g if x["○"]) / len(g), sum(x["秒"] for x in g) / len(g)))
shutil.rmtree(D, ignore_errors=True)
print("→", os.path.join(OUT, "hyou_bunshou.json"))
