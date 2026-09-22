#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""いまの直感役（chokkan）と 作り直し（chokkan2）を、同じ held-out で比べる物差し。
  比べ方（Codex の設計）: 「同じ頭脳呼び出し率での取りこぼし」で見る。線を振って曲線にし、
  さらに確率の質（NLL・Brier・ECE）も出す。36問（手作り）と 88文（頭脳作り）の両方。
  python3 hakaru_chokkan2.py [--train]
"""
import json, math, os, sys, time
KERNEL = os.environ.get("KERNEL_DIR") or os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, KERNEL)
import chokkan, chokkan2
from hakaru_erabu import DOUGU, BETSU, ZATSUDAN

def held_out():
    q = [(t, k) for t, k in DOUGU] + [(t, k) for t, k in BETSU] + [(t, None) for t in ZATSUDAN]
    nou = os.path.join(KERNEL, "chokkan_kyouzai_nou.jsonl")
    q2 = []
    if os.path.exists(nou):
        for l in open(nou, encoding="utf-8"):
            d = json.loads(l)
            if d.get("組") == "物差し":
                q2.append((d["文"], None if d["用件"] == "雑談" else d["用件"]))
    return q, q2

def hakaru(mod, toi, sen, shouko=None):
    """線 sen での (道具の正答, 道具の件数, 雑談の誤発動, 雑談の件数, 頭脳に回した割合)"""
    ok = dou = go = zatsu = mawashi = 0
    for t, kitai in toi:
        k = mod.kimeru(t, sen=sen, **({"shouko": shouko} if shouko is not None and mod is chokkan2 else {}))
        deta = k["用件"]
        mawashi += (deta is None)
        if kitai is None: zatsu += 1; go += (deta is not None)
        else: dou += 1; ok += (deta == kitai)
    return ok, dou, go, zatsu, mawashi / len(toi)

def shitsu(mod, toi):
    """確率の質: NLL・Brier・ECE（10箱）。正解は 用件（雑談は 雑談クラス）"""
    nll = br = 0.0; hako = [[0, 0.0, 0] for _ in range(10)]
    for t, kitai in toi:
        k = mod.kimeru(t, sen=0.0)
        p = dict(k["上位"]); na, pa = k["上位"][0]
        seikai = kitai or chokkan.ZATSUDAN
        pt = p.get(seikai, 1e-6)
        nll -= math.log(max(pt, 1e-12)); br += (1 - pt) ** 2
        i = min(9, int(pa * 10)); hako[i][0] += 1; hako[i][1] += pa; hako[i][2] += (na == seikai)
    n = len(toi)
    ece = sum(h[0] / n * abs(h[1] / h[0] - h[2] / h[0]) for h in hako if h[0])
    return nll / n, br / n, ece

def main():
    if "--train" in sys.argv:
        nozoku = [t for t, _ in DOUGU] + [t for t, _ in BETSU] + list(ZATSUDAN)
        print("== いまの chokkan を学習"); chokkan.gakushuu(nozoku=nozoku)
        print("== chokkan2 を学習"); chokkan2.gakushuu(nozoku=nozoku)
    chokkan._MODEL = chokkan2._MODEL = None
    q36, q88 = held_out()
    for na, toi in (("手作り 36問", q36), ("頭脳作り 88文", q88)):
        if not toi: continue
        print("\n===== %s（道具 %d・雑談 %d）=====" % (na, sum(1 for _, k in toi if k), sum(1 for _, k in toi if not k)))
        print("| 線 | いま 道具 | いま 誤発動 | 新 道具 | 新 誤発動 | いま 頭脳へ | 新 頭脳へ |"); print("|---|---|---|---|---|---|---|")
        for sen in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            a = hakaru(chokkan, toi, sen); b = hakaru(chokkan2, toi, sen, shouko=0.0)
            print("| %.1f | %d/%d | %d/%d | %d/%d | %d/%d | %.0f%% | %.0f%% |" % (sen, a[0], a[1], a[2], a[3], b[0], b[1], b[2], b[3], a[4]*100, b[4]*100))
        m1, m2 = chokkan.model(), chokkan2.model()
        a = hakaru(chokkan, toi, m1.sen if m1.sen is not None else chokkan.SEN)
        b = hakaru(chokkan2, toi, m2.sen, m2.shouko)
        print("★ 本番の線: いま(線%.2f) 道具 %d/%d・誤発動 %d/%d ／ 新(線%.2f・証拠≧%.1f) 道具 %d/%d・誤発動 %d/%d"
              % (m1.sen or chokkan.SEN, a[0], a[1], a[2], a[3], m2.sen, m2.shouko, b[0], b[1], b[2], b[3]))
        n1, br1, e1 = shitsu(chokkan, toi); n2, br2, e2 = shitsu(chokkan2, toi)
        print("  確率の質（小さいほど良い）: いま NLL %.3f Brier %.3f ECE %.3f ／ 新 NLL %.3f Brier %.3f ECE %.3f" % (n1, br1, e1, n2, br2, e2))
    t0 = time.monotonic(); [chokkan.kimeru("5分はかって") for _ in range(200)]; t1 = time.monotonic()
    [chokkan2.kimeru("5分はかって") for _ in range(200)]; t2 = time.monotonic()
    print("\n速さ: いま %.2fms/件 ／ 新 %.2fms/件" % ((t1-t0)*5, (t2-t1)*5))
if __name__ == '__main__':
    main()
