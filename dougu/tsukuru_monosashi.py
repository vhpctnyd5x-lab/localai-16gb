#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立した**物差し**を増やす（2026-09-22）。いまの物差しは 36問＋88文しかなく、
「誤発動 1% 未満」と言うには足りない（48/88 で誤り 0 でも 95% 上限は 6.1%/3.4%・Codex）。
ここでは 学習に使っていない先生（NVIDIA nemotron）に頼み、学習の教材と近い文は落として、
**測る専用**の文を作る（組="物差し2"。chokkan.kyouzai は 組=="学習" しか読まないので混ざらない）。

  python3 tsukuru_monosashi.py [--kazu 8] [--yarinaosu]
  出力: kernel/chokkan_monosashi2.jsonl  {"文","用件","組":"物差し2","先生"}
"""
import json, os, re, subprocess, sys, time, unicodedata
KERNEL = os.environ.get("KERNEL_DIR") or os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import erabu, machine, chokkan
OUT = os.path.join(KERNEL, "chokkan_monosashi2.jsonl")
KAZU = int(sys.argv[sys.argv.index("--kazu") + 1]) if "--kazu" in sys.argv else 8
SYSTEM = "日本語で、指示された数だけ、1行に1つ、番号や記号を付けずに書く。説明は書かない。"
GROQ = os.path.expanduser("~/.claude/scripts/groq.sh")


def kiku(prompt):
    """先生は NVIDIA（教材を作った Groq とは別の先生にして、独立を保つ）。だめなら Groq。"""
    import nvidia
    for i in range(2):
        try:
            t = nvidia.ask(prompt, model="super", system=SYSTEM, timeout=180, max_tokens=1200)
            if t and t.strip():
                return t, "nvidia"
        except Exception as e:
            print("   nvidia だめ: %s" % str(e)[:80])
        time.sleep(5)
    r = subprocess.run([GROQ, "-m", "openai/gpt-oss-120b", "-s", SYSTEM, prompt], capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
    return r.stdout, "groq"


def gyou(text):
    out = []
    for l in (text or "").split("\n"):
        l = re.sub(r"^\s*[\d０-９]+[.．、)）:：]?\s*", "", l).strip().strip("-・*「」 ")
        if 3 <= len(l) <= 60:
            out.append(l)
    return out


def _ng(s):
    s = chokkan._seiri(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def main():
    kyouzai = [t for t, _ in chokkan.kyouzai(quiet=True)]     # 学習に使う全文（近い物は落とす）
    ng_kyou = [_ng(t) for t in kyouzai]
    sude = set()
    if os.path.exists(OUT) and "--yarinaosu" not in sys.argv:
        for l in open(OUT, encoding="utf-8"):
            sude.add(json.loads(l)["文"])
    f = open(OUT, "w" if "--yarinaosu" in sys.argv else "a", encoding="utf-8")
    rei = dict(erabu.REI)
    kazu_all = ochita = 0
    for na in [n for _, ns in erabu.GUN for n in ns]:
        if na not in machine.OPS:
            continue
        setsumei = (machine.OPS[na][0].__doc__ or "").strip().split("\n")[0].split(":", 1)[-1].strip()
        t0 = time.monotonic()
        text, sensei = kiku("パソコンの相棒に「%s」（%s）をしてほしい人が、実際に口に出しそうな言い方を %d 個。"
                            "教科書みたいな言い方ではなく、言いよどみ・省略・話し言葉を混ぜる。例（%s）はそのまま使わない。1行に1つ。"
                            % (na, setsumei, KAZU, rei.get(na, "")))
        bun = []
        for b in gyou(text):
            if b in sude or b in bun or machine.match(b):
                continue
            a = _ng(b)
            if any(len(a & g) / max(1, len(a | g)) >= 0.45 for g in ng_kyou):   # 教材に近い＝測る意味がない
                ochita += 1
                continue
            bun.append(b)
        for b in bun[:KAZU]:
            f.write(json.dumps({"文": b, "用件": na, "組": "物差し2", "先生": sensei}, ensure_ascii=False) + "\n")
        f.flush()
        kazu_all += len(bun[:KAZU])
        print("  %-14s %2d文 %.0f秒 %s" % (na, len(bun[:KAZU]), time.monotonic() - t0, sensei))
    # 雑談（道具の言葉が入っているが頼んでいない＝一番間違えやすい）
    z = 0
    for t in ["天気・予定・暦・時間", "メール・連絡", "音・画面・アプリ", "ファイル・写真・パソコンの調子・電池・ネット",
              "計算・数・お金", "場所・時差・旅行", "思い出話・愚痴・独り言"]:
        text, sensei = kiku("「%s」に関わる言葉が入っているが、相棒には何も頼んでいない話し言葉の文を 20 個。"
                            "感想・思い出・意見・自分の行動の宣言など。命令や依頼は書かない。1行に1つ。" % t)
        for b in gyou(text):
            if b in sude or machine.match(b):
                continue
            a = _ng(b)
            if any(len(a & g) / max(1, len(a | g)) >= 0.45 for g in ng_kyou):
                ochita += 1
                continue
            f.write(json.dumps({"文": b, "用件": "雑談", "組": "物差し2", "先生": sensei}, ensure_ascii=False) + "\n")
            z += 1
        f.flush()
    f.close()
    print("道具 %d文・雑談 %d文（教材に近くて落とした %d）→ %s" % (kazu_all, z, ochita, OUT))


if __name__ == "__main__":
    main()
