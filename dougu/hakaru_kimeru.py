#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1トークンで道具を選ぶ（kimeru.py / erabu.kimeru_dougu）の物差し。hakaru_erabu と同じ 36 の言い方で測る。

  python3 hakaru_kimeru.py [--hou 名前|番号|2段]  … 決めるところだけ（用件・自信・秒）。線をどこに引くかの表を出す
  python3 hakaru_kimeru.py --tooshi   … chat.reply を通して（材料取り・言い方作りまで）hakaru_erabu と同じ採点
8080 の頭脳が立っている前提（hashiru_kimeru.sh）。
"""
import json, os, sys, time
KERNEL = os.environ.get("KERNEL_DIR") or os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import chat, erabu, machine
from hakaru_erabu import DOUGU, BETSU, ZATSUDAN
HERE = os.path.dirname(os.path.abspath(__file__))
SEN_HYO = (0.3, 0.5, 0.7, 0.9)


def main():
    tooshi = "--tooshi" in sys.argv
    hou = sys.argv[sys.argv.index("--hou") + 1] if "--hou" in sys.argv else erabu.HOU
    rows = []
    mondai = [(t, k, "作った") for t, k in DOUGU] + [(t, k, "別") for t, k in BETSU] + [(t, None, "雑談") for t in ZATSUDAN]
    print("===== 1トークンで選ぶ（%s・%s・%s） =====" % (time.strftime("%m/%d %H:%M"), "通し" if tooshi else "決めるだけ", hou))
    sysm = chat.sys_dougu()
    for toi, kitai, kumi in mondai:
        t0 = time.monotonic()
        if tooshi:
            rep = chat.reply(toi, [], None); sec = time.monotonic() - t0
            d = rep.get("道具"); got = d[0] if d else None
            k = rep.get("決め") or {}
            good = (got == kitai) if kitai else (not d)
            print("  %s %-24s %5.1f秒 期待=%-10s 出た=%-10s 自信=%s 群=%s ／ %s" % ("○" if good else "×", toi, sec, kitai or "雑談", got or "雑談",
                  k.get("自信"), k.get("群"), (rep.get("text") or rep.get("error") or "")[:40].replace("\n", " ")))
            rows.append({"問": toi, "組": kumi, "期待": kitai, "出た": got, "秒": round(sec, 1), "決め": k, "返事": (rep.get("text") or "")[:200], "先生": rep.get("teacher")})
        else:
            k = erabu.kimeru_dougu(sysm, chat._build_prompt(toi, [], None), hou=hou); sec = time.monotonic() - t0
            got = k.get("用件")
            good = (got == kitai) if kitai else (got is None)
            print("  %s %-24s %5.1f秒 期待=%-10s 出た=%-10s p1=%.2f p2=%s 自信=%.2f かさ=%s/%s 出た字=%r 読んだ=%s" % ("○" if good else "×", toi, sec, kitai or "雑談", got or "雑談",
                  k["p1"], k["p2"], k["自信"], k["かさ1"], k["かさ2"], k.get("出た"), k.get("tokens")))
            rows.append({"問": toi, "組": kumi, "期待": kitai, "出た": got, "秒": round(sec, 1), "決め": k})
    # 線ごとの成績（決めるだけの時は 自信 < 線 なら「道具なし」と扱う）
    print("\n  線     道具(作った) 道具(別)  雑談の誤発動  合計")
    for sen in SEN_HYO:
        a = b = c = 0
        for r in rows:
            k = r["決め"] or {}
            got = r["出た"] if (k.get("自信", 0) >= sen or not k) else None
            if r["組"] == "作った": a += got == r["期待"]
            elif r["組"] == "別": b += got == r["期待"]
            else: c += got is not None
        print("  %.1f     %2d/%d       %2d/%d       %2d/%d        %2d/%d" % (sen, a, len(DOUGU), b, len(BETSU), c, len(ZATSUDAN), a + b + (len(ZATSUDAN) - c), len(mondai)))
    byou = [r["秒"] for r in rows]
    print("  1問 %.1f秒（中央値 %.1f）" % (sum(byou) / len(byou), sorted(byou)[len(byou) // 2]))
    os.makedirs(os.path.join(HERE, "kekka"), exist_ok=True)
    json.dump({"日付": time.strftime("%Y-%m-%d"), "通し": tooshi, "法": hou, "線": erabu.SEN, "一件ずつ": rows},
              open(os.path.join(HERE, "kekka", "kimeru_%s%s.json" % ("tooshi_" if tooshi else "", time.strftime("%Y%m%d_%H%M"))), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
