#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直感役（kernel/chokkan.py・学習した小さな決定モデル）の物差し。hakaru_erabu と同じ held-out 36問（頭脳は使わない・秒でなくミリ秒）。

  python3 hakaru_chokkan.py            … 保存された重みで測る
  python3 hakaru_chokkan.py --train    … 教材から学習し直してから測る（物差しの文に近い教材は落とす）
採点: 道具の頼みは 期待の用件が線以上の自信で出ること。雑談は 用件が出ないこと。線ごとの表を出す。
"""
import json, os, sys, time
KERNEL = os.environ.get("KERNEL_DIR") or os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import chokkan
from hakaru_erabu import DOUGU, BETSU, ZATSUDAN
HERE = os.path.dirname(os.path.abspath(__file__))
SEN_HYO = (0.3, 0.5, 0.6, 0.7, 0.8, 0.9)


def main():
    nozoku = [t for t, _ in DOUGU] + [t for t, _ in BETSU] + ZATSUDAN
    if "--train" in sys.argv:
        chokkan.gakushuu(nozoku=nozoku)
    chokkan._MODEL = None
    m = chokkan.model()                      # 保存した重みを読み直して測る（測る物と使う物を同じに・Codex の審査 9/18）
    sen0 = m.sen if m.sen is not None else chokkan.SEN
    print("===== 直感役（%s・重み %s・T=%.2f・線 %.1f は校正用で決めた値） =====" % (time.strftime("%m/%d %H:%M"), json.load(open(chokkan.OMOMI)).get("made"), m.T, sen0))
    rows = []
    for toi, kitai, kumi in [(t, k, "作った") for t, k in DOUGU] + [(t, k, "別") for t, k in BETSU] + [(t, None, "雑談") for t in ZATSUDAN]:
        k = chokkan.kimeru(toi, sen=0.0)
        na, p = k["上位"][0]
        got = None if na == chokkan.ZATSUDAN else na
        good = (got == kitai) if kitai else (got is None)
        print("  %s %-24s 期待=%-10s 出た=%-10s p=%.2f  2位=%s %.2f  %dms" % ("○" if good else "×", toi, kitai or "雑談", got or "雑談", p, k["上位"][1][0], k["上位"][1][1], k["ms"]))
        rows.append({"問": toi, "組": kumi, "期待": kitai, "出た": got, "p": p, "上位": k["上位"]})
    a = b = c = 0
    for r in rows:
        got = r["出た"] if r["p"] >= sen0 else None
        if r["組"] == "作った": a += got == r["期待"]
        elif r["組"] == "別": b += got == r["期待"]
        else: c += got is not None
    print("\n  ★ 本番の線 %.1f: 道具(作った) %d/%d・道具(別) %d/%d・雑談の誤発動 %d/%d・合計 %d/%d（この1回の数字）" % (sen0, a, len(DOUGU), b, len(BETSU), c, len(ZATSUDAN), a + b + (len(ZATSUDAN) - c), len(rows)))
    print("  線     道具(作った) 道具(別)  雑談の誤発動  合計   （参考。線は上で決めてあり、ここで選ばない）")
    for sen in SEN_HYO:
        a = b = c = 0
        for r in rows:
            got = r["出た"] if r["p"] >= sen else None
            if r["組"] == "作った": a += got == r["期待"]
            elif r["組"] == "別": b += got == r["期待"]
            else: c += got is not None
        print("  %.1f     %2d/%d       %2d/%d       %2d/%d        %2d/%d" % (sen, a, len(DOUGU), b, len(BETSU), c, len(ZATSUDAN), a + b + (len(ZATSUDAN) - c), len(rows)))
    # 頭脳が作った独立の物差し（組=物差し）。私が書いた教材とは無縁なので、丸暗記の疑いが無い数字
    nou = os.path.join(KERNEL, "chokkan_kyouzai_nou.jsonl")
    if os.path.exists(nou):
        mono = [json.loads(l) for l in open(nou, encoding="utf-8")]
        gaku_bun = {d["文"] for d in mono if d.get("組") == "学習"}
        mono = [d for d in mono if d.get("組") == "物差し" and d["文"] not in gaku_bun]      # 学習側と同文は外す（Codex の審査）
        print("\n  頭脳が作った物差し %d文（道具 %d・雑談 %d）: 線ごとの 道具の正答／雑談の誤発動" % (len(mono), sum(1 for d in mono if d["用件"] != "雑談"), sum(1 for d in mono if d["用件"] == "雑談")))
        ks = [(d, chokkan.kimeru(d["文"], sen=0.0)) for d in mono]
        for sen in SEN_HYO:
            a = c = 0
            for d, k in ks:
                na, p = k["上位"][0]
                got = None if (na == chokkan.ZATSUDAN or p < sen) else na
                if d["用件"] != "雑談": a += got == d["用件"]
                else: c += got is not None
            print("  %.1f     道具 %3d/%d   雑談の誤発動 %2d/%d" % (sen, a, sum(1 for d in mono if d["用件"] != "雑談"), c, sum(1 for d in mono if d["用件"] == "雑談")))
        if "--kuwashiku" in sys.argv:
            for d, k in ks:
                na, p = k["上位"][0]
                if (d["用件"] == "雑談") != (na == chokkan.ZATSUDAN) or (d["用件"] != "雑談" and na != d["用件"]):
                    print("    × %-30s 期待=%-10s 出た=%s %.2f" % (d["文"][:30], d["用件"], na, p))
    os.makedirs(os.path.join(HERE, "kekka"), exist_ok=True)
    json.dump({"日付": time.strftime("%Y-%m-%d"), "T": m.T, "一件ずつ": rows}, open(os.path.join(HERE, "kekka", "chokkan_%s.json" % time.strftime("%Y%m%d_%H%M")), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
