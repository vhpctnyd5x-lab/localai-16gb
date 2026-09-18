#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""頭脳（8080）に、用件ごとの「遠回しな言い方」と「道具の言葉が入った雑談」を作らせる。直感役（chokkan）の教材と、独立した物差しに使う。

  出力: kernel/chokkan_kyouzai_nou.jsonl  {"文", "用件", "組": "学習"|"物差し"}
  ★ 私（Claude）が書いた教材・物差しとは独立（頭脳が作る）。用件ごとに 前の 2/3 を学習、後の 1/3 を物差しに回す。
  python3 tsukuru_iikata.py [--kazu 12]
"""
import json, os, re, sys, time, urllib.request
KERNEL = os.environ.get("KERNEL_DIR") or os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import erabu, machine, teachers
OUT = os.path.join(KERNEL, "chokkan_kyouzai_nou.jsonl")
KAZU = int(sys.argv[sys.argv.index("--kazu") + 1]) if "--kazu" in sys.argv else 12


def kiku(prompt, n_predict=700, temp=0.8):
    msgs = [{"role": "system", "content": "日本語で、指示された数だけ、1行に1つ、番号や記号を付けずに書く。説明は書かない。"},
            {"role": "user", "content": prompt}]
    p = teachers._katachi(msgs, False, 20)
    payload = {"prompt": p, "n_predict": n_predict, "temperature": temp, "top_p": 0.95, "cache_prompt": True, "stream": False}
    req = urllib.request.Request(teachers.LOCAL_URL + "/completion", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as f:
        return json.loads(f.read().decode("utf-8")).get("content", "")


def gyou(text):
    out = []
    for l in text.split("\n"):
        l = re.sub(r"^\s*[\d０-９]+[.．、)）:：]?\s*", "", l).strip().strip("-・*「」 ")
        if 3 <= len(l) <= 60:
            out.append(l)
    return out


def main():
    rei = dict(erabu.REI)
    done = {}
    if os.path.exists(OUT):
        for l in open(OUT, encoding="utf-8"):
            d = json.loads(l); done.setdefault(d["用件"], []).append(d)
    f = open(OUT, "a", encoding="utf-8")
    t_all = time.monotonic()
    for na in [n for _, ns in erabu.GUN for n in ns]:
        if na in done:
            continue
        setsumei = (machine.OPS[na][0].__doc__ or "").strip().split("\n")[0].split(":", 1)[-1].strip()
        t0 = time.monotonic()
        text = kiku("パソコンの相棒に「%s」（%s）をしてほしい人が言いそうな、くだけた・遠回しな言い方を %d 個。"
                    "例の言い方（%s）はそのまま使わない。名前・数・言葉は具体的に入れる。1行に1つ。" % (na, setsumei, KAZU, rei.get(na, "")))
        bun = []
        for b in gyou(text):
            if b not in bun and not machine.match(b):        # 決まった言い方に当たる文は 直感役の出番ではない
                bun.append(b)
        for i, b in enumerate(bun[:KAZU]):
            f.write(json.dumps({"文": b, "用件": na, "組": "学習" if i < (KAZU * 2) // 3 else "物差し"}, ensure_ascii=False) + "\n")
        f.flush()
        print("  %-14s %2d文 %.0f秒  例: %s" % (na, len(bun[:KAZU]), time.monotonic() - t0, " ／ ".join(bun[:3])))
    if "雑談" not in done:
        zatsu = []
        for tema in ["天気・予定・暦・時間", "メール・メッセージ・連絡", "音楽・音・画面・アプリ", "ファイル・写真・パソコンの調子・電池・ネット"]:
            text = kiku("「%s」に関わる言葉が入っているが、相棒に何も頼んでいない文（雑談・意見・思い出話・一般的な質問）を 25 個。1行に1つ。" % tema, temp=0.9)
            zatsu += [b for b in gyou(text) if not machine.match(b)]
        for i, b in enumerate(zatsu):
            f.write(json.dumps({"文": b, "用件": "雑談", "組": "学習" if i % 3 else "物差し"}, ensure_ascii=False) + "\n")
        print("  雑談 %d文" % len(zatsu))
    f.close()
    print("全体 %.0f秒 → %s" % (time.monotonic() - t_all, OUT))


if __name__ == "__main__":
    main()
