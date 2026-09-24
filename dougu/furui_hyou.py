#!/usr/bin/env python3
"""kekka 枝の ふるい（pplonly）の md から、大きさ・速さ・PPL を 1つの表に抜く（9/24）。
使い方: git fetch origin kekka && python3 dougu/furui_hyou.py [日付 例 2026-09-24]
注意: ランナーの CPU が ジョブごとに違うので、別ジョブの t/s は そのまま比べない。"""
import re, subprocess, sys
hi = sys.argv[1] if len(sys.argv) > 1 else "2026-09-24"
names = subprocess.run(["git", "ls-tree", "-r", "--name-only", "origin/kekka"], capture_output=True, text=True).stdout.split()
rows = []
for n in names:
    if not re.search(r"kekka/ubuntu-24\.04_.*pplonly_f0\.md$", n):
        continue
    t = subprocess.run(["git", "show", "origin/kekka:" + n], capture_output=True, text=True).stdout
    if hi not in t.splitlines()[0]:
        continue
    cpu = re.search(r"model name\s*:\s*(.+)", t)
    cpu = cpu.group(1).replace("AMD EPYC ", "").replace(" Processor", "").replace("-Core", "c") if cpu else "?"
    size = re.search(r"\|\s*([\d.]+) GiB", t)
    pp = re.search(r"pp512 \|\s*([\d.]+)", t)
    tg = re.search(r"tg128 \|\s*([\d.]+)", t)
    ratio_pp = re.search(r"基準比 pp512: ([\d.]+)", t)
    ratio_tg = re.search(r"基準比 tg128: ([\d.]+)", t)
    ppl = re.search(r"PPL = ([\d.]+) \+/- ([\d.]+)", t)
    extra = [l.strip() for l in t.splitlines() if re.search(r"peak|探り|8 GB|pgmaj", l) and "取れなかった" not in l][:3]
    name = n.replace("kekka/ubuntu-24.04_", "").replace("_pplonly_f0.md", "").replace("pplonly_f0.md", "(基準)")
    rows.append((float(ppl.group(1)) if ppl else 99.0, name, cpu[:28], size.group(1) if size else "-",
                 pp.group(1) if pp else "-", tg.group(1) if tg else "-", ppl.group(2) if ppl else "-",
                 ratio_pp.group(1) if ratio_pp else "-", ratio_tg.group(1) if ratio_tg else "-", " / ".join(extra)[:160]))
rows.sort()
print("名前\tCPU\tGiB\tpp512\ttg128\tPPL\t±\t基準比 pp512\t基準比 tg128\t他")
for r in rows:
    print("\t".join([r[1], r[2], r[3], r[4], r[5], "%.4f" % r[0] if r[0] < 99 else "失敗", r[6], r[7], r[8], r[9]]))
