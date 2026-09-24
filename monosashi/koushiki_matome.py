#!/usr/bin/env python3
"""公式ベンチマークの 分けて測った結果（koushiki_<名>_b*of*.jsonl）を 1つにまとめる。
使い方: python3 koushiki_matome.py <フォルダ> → 標準出力に表（Markdown）"""
import glob, json, os, re, sys
from collections import defaultdict

d = sys.argv[1]
kumi = defaultdict(list)
for f in sorted(glob.glob(os.path.join(d, "koushiki_*_b*of*.jsonl"))):
    m = re.match(r"koushiki_(.+)_b(\d+)of(\d+)\.jsonl", os.path.basename(f))
    kumi[(m.group(1), int(m.group(3)))] += [json.loads(l) for l in open(f, encoding="utf-8")]
print("| ベンチマーク | 解いた問題 | 正解率 | 平均秒 | 平均字（考えた分も） |\n|---|---|---|---|---|")
for (na, n), rs in sorted(kumi.items()):
    rs = list({r["i"]: r for r in rs}.values())
    if not rs: continue
    if isinstance(rs[0]["○"], dict):   # IFEval: 問い単位は 平均、指示単位は 全部の指示を まとめて割る（lm-eval と同じ）
        s = " / ".join(["%s %.1f%%" % (k, 100 * sum(r["○"][k] for r in rs) / len(rs)) for k in ("strict", "loose")] +
                       ["%s %.1f%%" % (k, 100 * sum(sum(r["○"][k]) for r in rs) / max(1, sum(len(r["○"][k]) for r in rs)))
                        for k in ("inst_strict", "inst_loose")])
    else:
        s = "%.1f%%" % (100 * sum(bool(r["○"]) for r in rs) / len(rs))
    print("| %s | %d | %s | %.0f | %.0f |" % (na, len(rs), s, sum(r["秒"] for r in rs) / len(rs),
                                             sum(r["字"] for r in rs) / len(rs)))
