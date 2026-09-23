#!/usr/bin/env python3
"""時刻電卓の練習問題（8段とは別。答えは datetime で正確に）→ monosashi/mondai_renshuu_jikan.jsonl"""
import datetime as dt, json, os, random
R = random.Random(9231)
HERE = os.path.dirname(os.path.abspath(__file__))
YOU = ["工場の機械", "図書館の整理", "パン工房の仕込み", "マラソン大会の運営", "天体カメラ", "データの書き出し", "水族館の清掃"]
rows = []
for i in range(16):
    a = dt.datetime(2026, R.randint(1, 11), R.randint(1, 27), R.randint(0, 23), R.choice(range(0, 60, 5)))
    b = a + dt.timedelta(minutes=R.randint(90, 3 * 24 * 60))
    hiku = R.choice([0, R.randint(5, 90)])
    kankei = R.randint(2, 9)
    w = "月火水木金土日"
    f = lambda t: f"{t.month}月{t.day}日（{w[t.weekday()]}）{t.hour}時{t.minute}分"
    tani = R.choice(["分", "分", "時間"]) if (int((b - a).total_seconds() // 60) - hiku) % 60 == 0 else "分"
    fun = int((b - a).total_seconds() // 60) - hiku
    q = (f"{R.choice(YOU)}は{f(a)}に動き始め、{f(b)}に止まりました。" + (f"その間、点検で{hiku}分だけ止めていました。" if hiku else "") +
         f"担当者は{kankei}人です。動いていた時間は全部で何{tani}ですか。")
    rows.append({"id": f"rj-{i + 1:02d}", "段": 7, "型": "時刻_練習", "問": q, "答": str(fun if tani == "分" else fun // 60), "答の形": "数"})
with open(os.path.join(HERE, "..", "monosashi", "mondai_renshuu_jikan.jsonl"), "w", encoding="utf-8") as fp:
    for r in rows: fp.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(rows), rows[0]["問"], rows[0]["答"])
