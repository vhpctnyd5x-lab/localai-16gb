#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""おまかせ（teachers.fukasa_miru）の机上の物差し。

深さ0・1・2 を1問ずつ測った結果（kekka/fukasa*_f0.json …）を突き合わせ、
「問いを見て深さを決める」決め方ごとに 正答・深くした数・かかる秒 を出す。
決め方は問いの文字だけで決まり（決定的）、同じ深さの答えは同じなので、
実際に回した数字と一致する。ただし机上は机上と書く。

  python3 omakase_tsukue.py                 … 120問（kekka/fukasa120_f*.json）
  python3 omakase_tsukue.py --name 6dan     … 難しい6段
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel") if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import teachers


def yomu(name, f):
    p = os.path.join(HERE, "kekka", "fukasa%s_f%d.json" % (name, f))
    if not os.path.isfile(p):
        p2 = os.path.join(HERE, "kekka", "fukasa%s_f%d.tochuu.jsonl" % (name, f))
        if not os.path.isfile(p2):
            return None
        rows = [json.loads(l) for l in open(p2, encoding="utf-8") if l.strip()]
    else:
        rows = json.load(open(p, encoding="utf-8"))["一件ずつ"]
    return {r["id"]: r for r in rows}


def matome(name, kimekata, fukasa_all):
    """kimekata(問) → 深さ。返す: (問数, 正答, 深くした数, 合計秒, 取りこぼしの id)"""
    ids = sorted(set.intersection(*(set(d) for d in fukasa_all.values())))
    n = ok = fukai = 0; byou = 0.0; ochi = []
    for i in ids:
        toi = fukasa_all[min(fukasa_all)][i]["問"]
        f = kimekata(toi)
        r = fukasa_all[f][i]
        n += 1; ok += bool(r["○"]); fukai += (f > 0); byou += float(r["秒"])
        if not r["○"]:
            ochi.append((i, r["型"], f))
    return n, ok, fukai, byou, ochi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="120")
    a = ap.parse_args()
    fk = {f: d for f in (0, 1, 2) if (d := yomu(a.name, f))}
    print("読めた深さ:", {f: len(d) for f, d in fk.items()})
    for f, d in fk.items():
        ids = sorted(d)
        print("深さ%d だけ: %d/%d 合計%.0f秒 中央%.0f秒 ×=%s" % (
            f, sum(bool(d[i]["○"]) for i in ids), len(ids), sum(d[i]["秒"] for i in ids),
            sorted(d[i]["秒"] for i in ids)[len(ids)//2], [i for i in ids if not d[i]["○"]]))
    kouho = {"今のおまかせ(0/2)": teachers.fukasa_miru}
    if 1 in fk:
        kouho["おまかせ→深さ1(0/1)"] = lambda t: 1 if teachers.fukasa_miru(t) else 0
    for na, km in kouho.items():
        need = {km(r["問"]) for r in fk[min(fk)].values()}
        if not need <= set(fk):
            print(na, ": 深さ", need - set(fk), "の結果がまだ無い"); continue
        n, ok, fukai, byou, ochi = matome(a.name, km, fk)
        print("%s: %d/%d 深くした%d 合計%.0f秒（1問%.1f秒） 取りこぼし=%s" % (na, ok, n, fukai, byou, byou / max(n, 1), ochi))


if __name__ == "__main__":
    main()
