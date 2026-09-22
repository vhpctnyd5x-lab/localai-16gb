#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作った物差し（chokkan_monosashi2.jsonl）の**検品**。作った先生（NVIDIA）とは別の先生（Groq）に、
1文ずつ「この文だけを見て、その用件を頼んでいると言い切れるか」を聞き、言い切れない物は落とす。
（作った側と検品する側を分ける。落とした物も残す＝後で見返せる）
  python3 kenpin_monosashi.py   → chokkan_monosashi2_ok.jsonl（合格）と ..._dame.jsonl
"""
import json, os, subprocess, sys, time
KERNEL = os.environ.get("KERNEL_DIR") or os.path.expanduser("~/LocalAI_mirror/kernel")
IN = os.path.join(KERNEL, "chokkan_monosashi2.jsonl")
OK = os.path.join(KERNEL, "chokkan_monosashi2_ok.jsonl")
DAME = os.path.join(KERNEL, "chokkan_monosashi2_dame.jsonl")
GROQ = os.path.expanduser("~/.claude/scripts/groq.sh")
SYS = "日本語。1行につき『番号<TAB>はい』か『番号<TAB>いいえ』だけを書く。説明は書かない。"

def kiku(prompt):
    for i in range(3):
        r = subprocess.run([GROQ, "-m", "openai/gpt-oss-120b", "-s", SYS, prompt], capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
        time.sleep(10 * (i + 1))
    return ""

rows = [json.loads(l) for l in open(IN, encoding="utf-8")]
ok, dame = [], []
for i in range(0, len(rows), 25):
    kata = rows[i:i + 25]
    q = []
    for j, d in enumerate(kata):
        if d["用件"] == "雑談":
            q.append("%d. 「%s」 … この文は、パソコンの相棒に何かを頼んでいますか。" % (j + 1, d["文"]))
        else:
            q.append("%d. 「%s」 … この文だけを見て、相棒に『%s』をしてほしいと言い切れますか。足りない情報があって他の用件とも取れるなら いいえ。" % (j + 1, d["文"], d["用件"]))
    t = kiku("次の各文に はい／いいえ で答えてください。\n" + "\n".join(q))
    kotae = {}
    for l in t.split("\n"):
        p = l.replace("\t", " ").split()
        if len(p) >= 2 and p[0].rstrip(".．").isdigit():
            kotae[int(p[0].rstrip(".．"))] = ("はい" in p[-1])
    for j, d in enumerate(kata):
        a = kotae.get(j + 1)
        good = (a is False) if d["用件"] == "雑談" else (a is True)
        d["検品"] = "groq"
        (ok if good else dame).append(d)
    print("  %d/%d 見た（合格 %d・落ち %d）" % (min(i + 25, len(rows)), len(rows), len(ok), len(dame)))
for path, rs in ((OK, ok), (DAME, dame)):
    with open(path, "w", encoding="utf-8") as f:
        for d in rs: f.write(json.dumps(d, ensure_ascii=False) + "\n")
d_ok = sum(1 for d in ok if d["用件"] != "雑談"); z_ok = len(ok) - d_ok
print("合格 %d文（道具 %d・雑談 %d）／ 落ち %d文 → %s" % (len(ok), d_ok, z_ok, len(dame), OK))
