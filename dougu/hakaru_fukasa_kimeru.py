#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「この問いは深く考える必要があるか」を 1トークン（はい/いいえ の確率）で決めさせ、深さ0 で落とした問いを拾えるかを測る。

  材料: kekka/fukasa120_f0.json・fukasa6dan_f0.json・fukasa7dan_f0.json（深さ0 の正誤つき 368問）
  比べる相手: teachers.fukasa_miru（今の おまかせ＝強い語・弱い語3つ・長さ50）
  見るもの: 落とした問い（×）を拾う割合（取りこぼし）と、○ の問いまで深くする割合（無駄）
  python3 hakaru_fukasa_kimeru.py     … 8080 の頭脳が立っている前提
"""
import json, os, sys, time
KERNEL = os.environ.get("KERNEL_DIR") or os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import kimeru, teachers
HERE = os.path.dirname(os.path.abspath(__file__))
SYS = "あなたは日本語の助手です。"
TOI = "上の【問い】に正しく答えるには、途中の計算や条件を段階を追って慎重に考える必要がある？（一目で答えられるなら いいえ）"


def main():
    rows = []
    for fn, kumi in (("fukasa120_f0.json", "120"), ("fukasa6dan_f0.json", "6段"), ("fukasa7dan_f0.json", "7段")):
        d = json.load(open(os.path.join(HERE, "kekka", fn), encoding="utf-8"))
        for r in d["一件ずつ"]:
            rows.append({"組": kumi, "id": r["id"], "型": r.get("型"), "問": r["問"], "○": bool(r.get("○")), "字数": len(r["問"])})
    print("===== 深さを 1トークンで決める（%s・%d問） =====" % (time.strftime("%m/%d %H:%M"), len(rows)))
    t_all = time.monotonic()
    for i, r in enumerate(rows):
        t0 = time.monotonic()
        try:
            k = kimeru.hai_iie(SYS, "【問い】" + r["問"], TOI)
            r["p"] = round(k["はい"], 3); r["かさ"] = round(k["かさ"], 3); r["出た"] = k["先頭"][:6]
        except Exception as e:
            r["p"] = None; r["かさ"] = None; r["出た"] = "%s" % e
        r["秒"] = round(time.monotonic() - t0, 1)
        r["おまかせ"] = teachers.fukasa_miru(r["問"])
        if i % 20 == 0:
            print("  %3d/%d %s %s p=%s かさ=%s %.1f秒 %s" % (i, len(rows), r["組"], "○" if r["○"] else "×", r["p"], r["かさ"], r["秒"], r["型"]))
    ochi = [r for r in rows if not r["○"]]
    atari = [r for r in rows if r["○"]]
    print("\n  落とした問い %d・合った問い %d。深くする割合（拾えた×／深くした○）" % (len(ochi), len(atari)))
    print("  おまかせ（今）: 拾えた %d/%d・○を深くした %d/%d" % (sum(1 for r in ochi if r["おまかせ"] == 2), len(ochi), sum(1 for r in atari if r["おまかせ"] == 2), len(atari)))
    for sen in (0.1, 0.3, 0.5, 0.7, 0.9):
        f = lambda r: (r["p"] or 0) >= sen
        print("  p ≧ %.1f      : 拾えた %d/%d・○を深くした %d/%d" % (sen, sum(1 for r in ochi if f(r)), len(ochi), sum(1 for r in atari if f(r)), len(atari)))
    for kumi in ("120", "6段", "7段"):
        rs = [r for r in rows if r["組"] == kumi]
        print("  %s: 平均 p=%.2f（× %.2f／○ %.2f）平均 %.1f秒" % (kumi, sum((r["p"] or 0) for r in rs) / len(rs),
              (sum((r["p"] or 0) for r in rs if not r["○"]) / max(1, sum(1 for r in rs if not r["○"]))),
              (sum((r["p"] or 0) for r in rs if r["○"]) / max(1, sum(1 for r in rs if r["○"]))), sum(r["秒"] for r in rs) / len(rs)))
    print("  全体 %.0f秒" % (time.monotonic() - t_all))
    json.dump({"日付": time.strftime("%Y-%m-%d"), "問い": TOI, "一件ずつ": rows}, open(os.path.join(HERE, "kekka", "fukasa_kimeru_%s.json" % time.strftime("%Y%m%d_%H%M")), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
