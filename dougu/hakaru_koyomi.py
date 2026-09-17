#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""こよみの物差し。アプリと同じ道（machine.match → machine.run）で 日付の問いに 暦が答えるか。頭脳は使わない（0秒）。

  python3 hakaru_koyomi.py
120問の物差しの「こよみ」8問（深さ0 の頭脳が3問落とした）＋ 今日を起点にした問い ＋ 暦ではない文（頭脳に回すべき）。
"""
import datetime, json, os, sys
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel") if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import machine
HERE = os.path.dirname(os.path.abspath(__file__))
Y = "月火水木金土日"


def main():
    kyou = datetime.date.today()
    d = lambda n: kyou + datetime.timedelta(days=n)
    kadai = []
    for r in (json.loads(l) for l in open(os.path.join(HERE, "..", "monosashi", "mondai.jsonl"), encoding="utf-8") if l.strip()):
        if r["型"] == "こよみ":
            kadai.append((r["問"], r["答"]))
    kadai += [
        ("今日は何曜日？", Y[kyou.weekday()] + "曜日"),
        ("明日は何月何日ですか", "%d月%d日" % (d(1).month, d(1).day)),
        ("3日後は何曜日", Y[d(3).weekday()] + "曜日"),
        ("2週間後は何月何日", "%d月%d日" % (d(14).month, d(14).day)),
        ("%d月%d日まであと何日" % (d(20).month, d(20).day), "あと20日"),
        ("%d年%d月%d日から%d年%d月%d日まで何日ありますか" % (d(0).year, d(0).month, d(0).day, d(15).year, d(15).month, d(15).day), "15日"),
        ("2026年12月25日は何曜日", "金曜日"),
        ("来年の1月1日は何曜日", Y[datetime.date(kyou.year + 1, 1, 1).weekday()] + "曜日"),
        ("14時30分の2時間後は何時？", "16時30分"),
        ("午後3時の90分後は何時", "16時30分"),
        ("9:15の45分前は何時ですか", "8時30分"),
        ("23時の2時間後は何時", "1時00分（翌日）"),
    ]
    inai = ["何日か休みたい", "12月の予定を教えて", "3日後にビールを買っておいて", "いま何時？"]
    ok = 0
    for toi, kitai in kadai:
        hit = machine.match(toi)
        ans = machine.run(*hit) if hit and hit[0] == "こよみ" else None
        good = ans is not None and kitai in str(ans)
        ok += good
        print("%s %-46s 期待=%-8s 出た=%s" % ("○" if good else "×", toi[:46], kitai, ans))
    for toi in inai:
        hit = machine.match(toi)
        good = not (hit and hit[0] == "こよみ")
        ok += good
        print("%s %-46s 期待=頭脳へ 出た=%s" % ("○" if good else "×", toi, hit[0] if hit else "（当たらず）"))
    n = len(kadai) + len(inai)
    print("こよみ: %d/%d（この1回の数字・%s）" % (ok, n, kyou))
    os.makedirs(os.path.join(HERE, "kekka"), exist_ok=True)
    json.dump({"日付": str(kyou), "正答": ok, "問数": n}, open(os.path.join(HERE, "kekka", "koyomi_%s.json" % kyou.strftime("%Y%m%d")), "w", encoding="utf-8"), ensure_ascii=False)
    return 0 if ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
