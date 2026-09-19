#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雲の先生（Groq gpt-oss-120b、だめなら NVIDIA）に、用件ごとの「遠回しな言い方」と「道具の言葉が入った雑談」を作らせる。
直感役（chokkan）の **学習用だけ**（物差しには入れない。物差しは 手書き＋手元の頭脳が作った物のまま＝独立を保つ）。
  出力: kernel/chokkan_kyouzai_kumo.jsonl  {"文", "用件", "組": "学習", "先生"}
  python3 tsukuru_iikata_kumo.py [--kazu 20]      Mac の頭脳を使わない（8080 が物差しで忙しくても動く）
"""
import json, os, re, subprocess, sys, time
KERNEL = os.environ.get("KERNEL_DIR") or os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import erabu, machine
OUT = os.path.join(KERNEL, "chokkan_kyouzai_kumo.jsonl")
KAZU = int(sys.argv[sys.argv.index("--kazu") + 1]) if "--kazu" in sys.argv else 20
GROQ = os.path.expanduser("~/.claude/scripts/groq.sh")
SYSTEM = "日本語で、指示された数だけ、1行に1つ、番号や記号を付けずに書く。説明は書かない。"


def kiku(prompt):
    for i in range(3):
        r = subprocess.run([GROQ, "-m", "openai/gpt-oss-120b", "-s", SYSTEM, prompt], capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout, "groq"
        time.sleep(20 * (i + 1))
    import nvidia
    return nvidia.ask(prompt, model="fast", system=SYSTEM), "nvidia"


def gyou(text):
    out = []
    for l in text.split("\n"):
        l = re.sub(r"^\s*[\d０-９]+[.．、)）:：]?\s*", "", l).strip().strip("-・*「」 ")
        if 3 <= len(l) <= 60:
            out.append(l)
    return out


def main():
    rei = dict(erabu.REI)
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT, encoding="utf-8"):
            done.add(json.loads(l)["用件"])
    f = open(OUT, "a", encoding="utf-8")
    t_all = time.monotonic()
    for na in [n for _, ns in erabu.GUN for n in ns]:
        if na in done or na not in machine.OPS:
            continue
        setsumei = (machine.OPS[na][0].__doc__ or "").strip().split("\n")[0].split(":", 1)[-1].strip()
        t0 = time.monotonic()
        text, sensei = kiku("パソコンの相棒に「%s」（%s）をしてほしい人が言いそうな、くだけた・遠回しな言い方を %d 個。"
                            "例の言い方（%s）はそのまま使わない。名前・数・言葉は具体的に入れる。言い回しは互いに違えて、丁寧な物とぞんざいな物を混ぜる。1行に1つ。"
                            % (na, setsumei, KAZU, rei.get(na, "")))
        bun = []
        for b in gyou(text):
            if b not in bun and not machine.match(b):        # 決まった言い方に当たる文は 直感役の出番ではない
                bun.append(b)
        for b in bun[:KAZU]:
            f.write(json.dumps({"文": b, "用件": na, "組": "学習", "先生": sensei}, ensure_ascii=False) + "\n")
        f.flush()
        print("  %-14s %2d文 %.0f秒 %s  例: %s" % (na, len(bun[:KAZU]), time.monotonic() - t0, sensei, " ／ ".join(bun[:2])))
    if "雑談" not in done:
        zatsu = []
        for t in ["天気・予定・暦・時間", "メール・メッセージ・連絡", "音楽・音・画面・アプリ", "ファイル・写真・パソコンの調子・電池・ネット", "計算・数・お金・買い物", "場所・時差・旅行・乗り物"]:
            text, sensei = kiku("「%s」に関わる言葉が入っているが、相棒に何も頼んでいない文（雑談・意見・思い出話・一般的な質問・出かける等の自分の行動の宣言）を 25 個。1行に1つ。" % t)
            zatsu += [b for b in gyou(text) if not machine.match(b)]
        for b in zatsu:
            f.write(json.dumps({"文": b, "用件": "雑談", "組": "学習", "先生": sensei}, ensure_ascii=False) + "\n")
        print("  雑談 %d文" % len(zatsu))
    f.close()
    print("全体 %.0f秒 → %s" % (time.monotonic() - t_all, OUT))


if __name__ == "__main__":
    main()
