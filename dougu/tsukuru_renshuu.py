#!/usr/bin/env python3
"""練習用の問題（手順書を選ぶための物差し。7段 128問は最後の確かめにだけ使う）。
数と答えは Python が決める（切手は総当たりで数える）。言い回しだけ NVIDIA に書き換えさせ、
数が全部残っているものだけ使う。→ monosashi/mondai_renshuu.jsonl
使い方: python3 dougu/tsukuru_renshuu.py [件数/型=16]
"""
import json, os, random, re, sys
KERNEL = os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import nvidia

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "monosashi", "mondai_renshuu.jsonl")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 16
R = random.Random(923)
SHINA = ["りんご", "ノート", "電池", "タオル", "缶詰", "鉛筆", "石けん", "封筒"]
BASHO = ["商店", "倉庫", "図書室", "売店", "文具店", "薬局"]


def kitte():
    while True:
        a, b, c = sorted(R.sample(range(2, 16), 3))
        g = R.randint(45, 130)
        n = sum(1 for z in range(g // c + 1) for y in range((g - c * z) // b + 1)
                if (g - c * z - b * y) % a == 0)
        if 6 <= n <= 40:
            ta = R.randint(20, 99)
            bun = (f"{a}円・{b}円・{c}円の切手を組み合わせて、ちょうど{g}円分にします。"
                   f"となりの人は{ta}円の荷物を出していました。どの切手も0枚でもよく、"
                   f"貼る順番は数えません。枚数の組み合わせは全部で何通りですか。")
            return bun, str(n), [a, b, c, g, ta]


def zaiko():
    s, b, k = R.randint(40, 150), R.randint(3, 9), R.randint(4, 12)
    u = R.randint(20, s + b * k - 10)
    r = R.choice([0, 0, R.randint(2, 9)])
    betsu, kagiri = R.randint(10, 40), R.randint(50, 120)
    shina, basho = R.choice(SHINA), R.choice(BASHO)
    bun = (f"{basho}に売り物の{shina}が{s}個あります。{k}個入りの箱が{b}箱届きました。"
           f"その日{u}個売れました。" + (f"あとで{r}個が返品されて売り場に戻りました。" if r else "") +
           f"なお、{basho}の奥には飾り用の{shina}が{betsu}個別にしまってあり、"
           f"棚には最大{kagiri}個まで並べられます。売り物の{shina}はいま何個ありますか。")
    return bun, str(s + b * k - u + r), [s, b, k, u, betsu, kagiri] + ([r] if r else [])


def iikae(bun, kazu):
    p = ("次の算数の文章題を、意味と数字を一切変えずに、別の自然な日本語の言い回しに書き換えてください。"
         "数字は全部そのまま残し、新しい数字は足さないこと。書き換えた問題文だけを出力。\n\n" + bun)
    try:
        t = nvidia.ask(p, model="super", timeout=120, max_tokens=600).strip()
    except Exception as e:
        return None
    kazu = lambda x: sorted(int(n) for n in re.findall(r"\d+", x))
    if kazu(t) == kazu(bun):
        return t
    print("   数が崩れた:", t[:80].replace("\n", " "), flush=True)
    return None


def main():
    rows = []
    for kata, f in (("場合分け_切手", kitte), ("同文脈_在庫", zaiko)):
        i = 0
        while i < N:
            bun, kotae, kazu = f()
            t = iikae(bun, kazu) or bun   # 書き換えが数を崩したら元の文
            i += 1
            rows.append({"id": f"r-{kata[:2]}{i:02d}", "段": 7, "型": kata, "問": t, "答": kotae, "答の形": "数"})
            print(kata, i, "NVIDIA" if t != bun else "元の文", flush=True)
    with open(OUT, "w", encoding="utf-8") as w:
        for r in rows:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("→", OUT, len(rows))


if __name__ == "__main__":
    main()
