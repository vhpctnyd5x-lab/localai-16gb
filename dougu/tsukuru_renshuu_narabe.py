#!/usr/bin/env python3
"""並べ方・順位の練習問題（8段とは別。答えは総当たりで正確に）→ monosashi/mondai_renshuu_narabe.jsonl"""
import itertools, json, os, random
R = random.Random(9232)
HERE = os.path.dirname(os.path.abspath(__file__))
HITO = ["青木", "井上", "上田", "江藤", "大野", "加藤", "木村"]
rows = []
def kazoe(n, conds):
    return [p for p in itertools.permutations(range(1, n + 1)) if all(c(p) for c in conds)]
while len(rows) < 8:                      # 並べ方の数
    n = R.randint(4, 6); h = HITO[:n]; a, b, c = R.sample(range(n), 3)
    kinds = R.sample(["tonari_nai", "tonari", "hashi", "mae"], 2); conds = []; bun = []
    for k in kinds:
        if k == "tonari_nai": conds.append(lambda p, a=a, b=b: abs(p[a] - p[b]) != 1); bun.append(f"{h[a]}さんと{h[b]}さんは隣り合わない")
        if k == "tonari": conds.append(lambda p, a=a, c=c: abs(p[a] - p[c]) == 1); bun.append(f"{h[a]}さんと{h[c]}さんは必ず隣どうし")
        if k == "hashi": conds.append(lambda p, c=c, n=n: p[c] in (1, n)); bun.append(f"{h[c]}さんはどちらかの端")
        if k == "mae": conds.append(lambda p, b=b, c=c: p[b] < p[c]); bun.append(f"{h[b]}さんは{h[c]}さんより前")
    x = len(kazoe(n, conds))
    if x == 0: continue
    rows.append({"id": f"rn-{len(rows)+1:02d}", "段": 7, "型": "並べ方_練習", "答の形": "数", "答": str(x),
                 "問": f"{'、'.join(h)}の{n}人が写真のために横一列に並びます。条件は、" + "、".join(bun) + f"です。部屋には椅子が{R.randint(7,12)}脚あります。並び方は何通りですか。"})
while len(rows) < 16:                     # 何番目（答えが1つに決まるものだけ）
    n = R.randint(4, 5); h = HITO[:n]; p0 = list(range(1, n + 1)); R.shuffle(p0)
    facts, conds = [], []
    for _ in range(12):
        i, j = R.sample(range(n), 2); k = R.choice(["mae", "tonari", "ichi"])
        if k == "mae" and p0[i] < p0[j]: conds.append(lambda p, i=i, j=j: p[i] < p[j]); facts.append(f"{h[i]}さんは{h[j]}さんより先にゴールした")
        if k == "tonari" and abs(p0[i] - p0[j]) == 1: conds.append(lambda p, i=i, j=j: abs(p[i] - p[j]) == 1); facts.append(f"{h[i]}さんと{h[j]}さんの順位は続いていた")
        if k == "ichi" and R.random() < 0.3: conds.append(lambda p, i=i, v=p0[i]: p[i] == v); facts.append(f"{h[i]}さんは{p0[i]}位だった")
        kai = kazoe(n, conds)
        t = R.randrange(n)
        if len({q[t] for q in kai}) == 1 and len(facts) >= 2: break
    else: continue
    rows.append({"id": f"rn-{len(rows)+1:02d}", "段": 7, "型": "推理_練習", "答の形": "数", "答": str(kai[0][t]),
                 "問": f"{'、'.join(h)}の{n}人が徒競走をしました（同着なし）。" + "。".join(facts) + f"。応援に来た家族は{R.randint(8,20)}人でした。{h[t]}さんは何位でしたか。"})
with open(os.path.join(HERE, "..", "monosashi", "mondai_renshuu_narabe.jsonl"), "w", encoding="utf-8") as fp:
    for r in rows: fp.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(rows)); print(rows[0]["問"], rows[0]["答"]); print(rows[-1]["問"], rows[-1]["答"])
