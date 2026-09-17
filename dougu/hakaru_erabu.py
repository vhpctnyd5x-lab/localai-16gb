#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""頭脳が自分で道具を選ぶ（erabu.py）の物差し。決まった言い方に **当たらない** 頼み 12 と、道具を使ってはいけない雑談 12。

  python3 hakaru_erabu.py          … 8080 の頭脳を使う（hashiru_*.sh と同じく、立っている前提）
採点: 道具の頼みは 頭脳が「道具: 言い方」と書き、その言い方が期待の用件に当たること。雑談は道具を使わないこと。
"""
import json, os, sys, time
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel") if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import chat, machine
HERE = os.path.dirname(os.path.abspath(__file__))

DOUGU = [  # 正規表現には当たらない言い方（machine.match が None であることを先に確かめる）
    ("傘いるかな、今日", "天気"), ("あのポチの写真どこいったっけ", "ファイルを探す"), ("メール何通たまってる？", "未読メール"),
    ("ちょっと5分はかって", "タイマー"), ("NYの時間わかる？", "世界時計"), ("1234かける56いくつ", "計算"),
    ("明後日って何曜？", "こよみ"), ("明日なにか入ってたっけ", "予定"), ("画面まぶしい", "明るさ"), ("うるさい、音消して", "消音"),
    ("パソコン遅いんだけど何が重いの", "重いアプリ"), ("充電あとどれくらい", "電池"),
]
ZATSUDAN = ["今日は疲れた", "おすすめの映画ある？", "ありがとう、助かった", "猫と犬どっちが好き？", "3日後に旅行に行くんだ、楽しみ",
            "最近ネットで話題のことって何だと思う？", "5分だけ休憩してくる", "メールって書くの苦手なんだよね", "音楽は何が好き？", "明日は早起きしないと",
            "電池って発明したの誰だっけ", "計算が苦手で困ってる"]


def main():
    ok = n = 0; rows = []
    print("===== 頭脳が道具を選ぶ（%s） =====" % time.strftime("%m/%d %H:%M"))
    for toi, kitai in DOUGU:
        n += 1; t0 = time.monotonic()
        if machine.match(toi):
            print("  ！ %-22s は決まった言い方に当たるので、この物差しの問いとして不適切（%s）" % (toi, machine.match(toi)[0]))
        rep = chat.reply(toi, [], None); sec = time.monotonic() - t0
        d = rep.get("道具"); got = d[0] if d else None
        good = got == kitai; ok += good
        print("  %s %-22s %5.1f秒 期待=%-10s 出た=%s ／ %s" % ("○" if good else "×", toi, sec, kitai, got or "（道具なし）", rep.get("text", rep.get("error", ""))[:50].replace("\n", " ")))
        rows.append({"問": toi, "期待": kitai, "出た": got, "秒": round(sec, 1), "返事": rep.get("text", "")[:200]})
    for toi in ZATSUDAN:
        n += 1; t0 = time.monotonic()
        rep = chat.reply(toi, [], None); sec = time.monotonic() - t0
        d = rep.get("道具"); good = not d; ok += good
        print("  %s %-22s %5.1f秒 期待=雑談       出た=%s ／ %s" % ("○" if good else "×", toi, sec, (d[0] or d[1]) if d else "雑談", rep.get("text", rep.get("error", ""))[:50].replace("\n", " ")))
        rows.append({"問": toi, "期待": None, "出た": (d[0] or d[1]) if d else None, "秒": round(sec, 1), "返事": rep.get("text", "")[:200]})
    print("選ぶ: %d/%d（この1回の数字）" % (ok, n))
    os.makedirs(os.path.join(HERE, "kekka"), exist_ok=True)
    json.dump({"日付": time.strftime("%Y-%m-%d"), "正答": ok, "問数": n, "一件ずつ": rows}, open(os.path.join(HERE, "kekka", "erabu_%s.json" % time.strftime("%Y%m%d_%H%M")), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0 if ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
