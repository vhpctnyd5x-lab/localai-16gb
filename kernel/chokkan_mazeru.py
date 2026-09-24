# -*- coding: utf-8 -*-
"""chokkan_mazeru ── 直感役の「二人がかり」。回帰（chokkan）と単純ベイズ（chokkan2）の確率を
幾何平均で混ぜ、混ぜ具合 w と 線 sen を **教材の交差検証（out-of-fold）だけ**で決める。
物差し（36問・88文）は決めたあと 1回だけ見る（物差しに合わせて選ばない・[[hakarikata-ana]]）。

  python3 chokkan_mazeru.py --train   … 交差検証で w と 線 を決め、両方の模型と一緒に保存
  chokkan_mazeru.kimeru("5分はかって") → chokkan と同じ形の返し
"""
from __future__ import annotations
import json, math, os, random, time
import chokkan as C1
import chokkan2 as C2

HERE = os.path.dirname(os.path.abspath(__file__))
SETTEI = os.path.join(HERE, "chokkan_mazeru.json")
ZATSUDAN = "雑談"
W_KOUHO = (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0)
SEN_KOUHO = (0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.8)


def _mazeru(d1: dict, d2: dict, w: float) -> dict:
    cls = set(d1) | set(d2)
    p = {c: max(d1.get(c, 1e-12), 1e-12) ** (1 - w) * max(d2.get(c, 1e-12), 1e-12) ** w for c in cls}
    s = sum(p.values())
    return {c: v / s for c, v in p.items()}


def _oof_ryouhou(rei, K=5, seed=0):
    """両方の模型の out-of-fold 確率（辞書）と正解を返す"""
    rnd = random.Random(seed)
    by = {}
    for t, c in rei:
        by.setdefault(c, []).append(t)
    fold = {}
    for c, ts in by.items():
        ts = list(ts); rnd.shuffle(ts)
        for i, t in enumerate(ts):
            fold[(t, c)] = i % K
    out = []
    for k in range(K):
        gaku = [x for x in rei if fold[x] != k]
        test = [x for x in rei if fold[x] == k]
        m1 = C1.Model(sorted({c for _, c in gaku})).train(gaku, quiet=True)
        m1.ondo(gaku[: max(50, len(gaku) // 5)])
        m2 = C2.Model(alpha=1.0, nagasa=0.3).fit(gaku)
        for t, c in test:
            p1 = m1.kakuritsu(C1.tokuchou(t))
            p2, _ = m2.kakuritsu(C2.tokuchou(t))
            out.append(({m1.classes[i]: p1[i] for i in range(len(p1))},
                        {m2.classes[i]: p2[i] for i in range(len(p2))}, c))
    return out


def erabu(oof, bacchi=20.0):
    """w と 線 を損得で選ぶ（Codex の設計: τ ≒ 1 − 頭脳の費用 / 誤発動の損）。
    費用: 道具を取りこぼす＝頭脳を1回呼ぶ＝1、誤発動（間違った道具を動かす・雑談に道具を出す）＝bacchi。"""
    best = None
    for w in W_KOUHO:
        mazeta = [(_mazeru(d1, d2, w), c) for d1, d2, c in oof]
        for sen in SEN_KOUHO:
            ok = go = mawashi = 0
            for p, c in mazeta:
                na = max(p, key=p.get)
                deru = na != ZATSUDAN and p[na] >= sen
                if c == ZATSUDAN:
                    go += deru
                elif deru and na == c:
                    ok += 1
                elif deru:
                    go += 1          # 違う道具を出した
                else:
                    mawashi += 1     # 頭脳へ
            son = mawashi * 1.0 + go * bacchi
            if best is None or son < best[4]:
                best = (w, sen, ok, go, son)
    return best[:4] if best else None


def gakushuu(nozoku=None, seed=0, quiet=False, K=5, bacchi=20.0):
    rei = C1.kyouzai(nozoku, quiet=quiet)
    cache = os.path.join(HERE, "chokkan_oof.json")
    if os.environ.get("KERNEL_OOF_CACHE") == "1" and os.path.exists(cache):
        oof = [(d1, d2, c) for d1, d2, c in json.load(open(cache, encoding="utf-8"))]
    else:
        oof = _oof_ryouhou(rei, K, seed)
        json.dump(oof, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    b = erabu(oof, bacchi)
    w, sen, ok, go = b
    C1.gakushuu(nozoku=nozoku, seed=seed, quiet=True)
    C2.gakushuu(nozoku=nozoku, seed=seed, quiet=True)
    json.dump({"w": w, "sen": sen, "oof_道具": ok, "oof_誤発動": go, "made": time.strftime("%Y-%m-%d %H:%M")},
              open(SETTEI, "w", encoding="utf-8"), ensure_ascii=False)
    if not quiet:
        print("  交差検証で決めた: 混ぜ w=%.2f・線 %.2f（OOF 道具 %d拾い・雑談の誤発動 %d）" % (w, sen, ok, go))
    return w, sen


_S = None


def settei():
    global _S
    if _S is None:
        _S = json.load(open(SETTEI, encoding="utf-8"))
    return _S


def kimeru(text: str, sen: float = None, w: float = None) -> dict:
    t0 = time.monotonic()
    s = settei()
    w = s["w"] if w is None else w
    sen = s["sen"] if sen is None else sen
    m1, m2 = C1.model(), C2.model()
    p1 = m1.kakuritsu(C1.tokuchou(text))
    p2, shouko = m2.kakuritsu(C2.tokuchou(text))
    p = _mazeru({m1.classes[i]: p1[i] for i in range(len(p1))},
                {m2.classes[i]: p2[i] for i in range(len(p2))}, w)
    o = sorted(p, key=lambda c: -p[c])
    na, pa = o[0], p[o[0]]
    out = {"用件": None, "自信": round(pa, 3), "証拠": round(shouko, 3),
           "上位": [(c, round(p[c], 3)) for c in o[:3]], "ms": int((time.monotonic() - t0) * 1000)}
    if na != ZATSUDAN and pa >= sen:
        out["用件"] = na
    return out


if __name__ == "__main__":
    import sys
    if "--train" in sys.argv:
        import importlib.util
        f = os.path.expanduser("~/LocalAI_mirror/koukai/dougu/hakaru_erabu.py")
        spec = importlib.util.spec_from_file_location("he", f); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        gakushuu(nozoku=[t for t, _ in mod.DOUGU] + [t for t, _ in mod.BETSU] + list(mod.ZATSUDAN))
    else:
        for t in sys.argv[1:] or ["ちょっと5分はかって", "今日は疲れた"]:
            print(t, "→", kimeru(t))
