#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""教材を増やす（2026-09-22 夜）。独立した物差し2 で落ちたのは **言いよどみ・省略の多い話し言葉**（拾い率 52%）。
そこで「えっと」「あの」「これ」など、実際に口から出る形の言い方を 学習用に作らせる。
  物差し2（測る専用）とは別に作り、物差し2 の文と 2-gram が 45% 以上重なる物は落とす（物差しに合わせない）。
  python3 tsukuru_iiyodomi.py [--kazu 12]  → kernel/chokkan_kyouzai_iiyodomi.jsonl（組="学習"）
"""
import json, os, re, subprocess, sys, time
KERNEL = os.environ.get("KERNEL_DIR") or os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import erabu, machine, chokkan
OUT = os.path.join(KERNEL, "chokkan_kyouzai_iiyodomi.jsonl")
KAZU = int(sys.argv[sys.argv.index("--kazu") + 1]) if "--kazu" in sys.argv else 12
GROQ = os.path.expanduser("~/.claude/scripts/groq.sh")
SYS = "日本語で、指示された数だけ、1行に1つ、番号や記号を付けずに書く。説明は書かない。"

def kiku(p):
    for i in range(3):
        r = subprocess.run([GROQ, "-m", "openai/gpt-oss-120b", "-s", SYS, p], capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        if r.returncode == 0 and r.stdout.strip(): return r.stdout, "groq"
        time.sleep(10 * (i + 1))
    import nvidia
    return nvidia.ask(p, model="super", system=SYS, timeout=180), "nvidia"

def gyou(t):
    o = []
    for l in (t or "").split("\n"):
        l = re.sub(r"^\s*[\d０-９]+[.．、)）:：]?\s*", "", l).strip().strip("-・*「」 ")
        if 3 <= len(l) <= 60: o.append(l)
    return o

def _ng(s):
    s = chokkan._seiri(s)
    return {s[i:i+2] for i in range(len(s)-1)} or {s}

def main():
    mono = []
    for fn in ("chokkan_monosashi2_ok.jsonl", "chokkan_monosashi2_dame.jsonl"):
        p = os.path.join(KERNEL, fn)
        if os.path.exists(p):
            mono += [_ng(json.loads(l)["文"]) for l in open(p, encoding="utf-8")]
    mono += [_ng(t) for t in chokkan.monosashi_no_bun()]
    f = open(OUT, "w", encoding="utf-8"); n = 0; ochi = 0
    rei = dict(erabu.REI)
    for na in [x for _, ns in erabu.GUN for x in ns]:
        if na not in machine.OPS: continue
        setsu = (machine.OPS[na][0].__doc__ or "").strip().split("\n")[0].split(":", 1)[-1].strip()
        t, sensei = kiku("パソコンの相棒に「%s」（%s）を頼むときの、**話し言葉そのまま**の言い方を %d 個。"
                         "「えっと」「あの」「ちょっと」などの言いよどみ、「これ」「それ」などの指示語、主語や目的語の省略、"
                         "言い直し（〜じゃなくて〜）、語尾の崩れ（〜してくんない？ 〜してや）を混ぜる。例（%s）はそのまま使わない。1行に1つ。"
                         % (na, setsu, KAZU, rei.get(na, "")))
        bun = []
        for b in gyou(t):
            if b in bun or machine.match(b): continue
            a = _ng(b)
            if any(len(a & g)/max(1, len(a | g)) >= 0.45 for g in mono): ochi += 1; continue
            bun.append(b)
        for b in bun[:KAZU]:
            f.write(json.dumps({"文": b, "用件": na, "組": "学習", "先生": sensei, "種": "言いよどみ"}, ensure_ascii=False) + "\n"); n += 1
        f.flush()
        print("  %-14s %2d文 %s" % (na, len(bun[:KAZU]), sensei))
    z = 0
    for t0 in ["天気・予定・時間", "メール・連絡", "音・画面・アプリ", "ファイル・写真・電池・ネット", "計算・お金", "場所・旅行"]:
        t, sensei = kiku("「%s」の言葉が入っているが相棒に何も頼んでいない、**言いよどみや指示語の多い話し言葉**の文を 20 個。"
                         "感想・独り言・思い出・自分の行動の宣言。命令や依頼は書かない。1行に1つ。" % t0)
        for b in gyou(t):
            if machine.match(b): continue
            a = _ng(b)
            if any(len(a & g)/max(1, len(a | g)) >= 0.45 for g in mono): ochi += 1; continue
            f.write(json.dumps({"文": b, "用件": "雑談", "組": "学習", "先生": sensei, "種": "言いよどみ"}, ensure_ascii=False) + "\n"); z += 1
        f.flush()
    f.close()
    print("道具 %d文・雑談 %d文（物差しに近くて落とした %d）→ %s" % (n, z, ochi, OUT))

if __name__ == "__main__":
    main()
