# -*- coding: utf-8 -*-
"""chokkan ── 直感役。頼み文を見て「どの用件か／道具は要らないか」を **確率で** 数ミリ秒で決める（2026-09-18）。

  Jev（TypeSafe AI）の「System One モデル」の本物の真似: 文章を書かせず、学習した小さなモデルが
  確率つきで決める。9/18 に「素の頭脳に 1トークンで答えさせる」形（kimeru.py）を測ったら 確率が校正されておらず
  元の形に負けた（22/36 vs 28/36）。校正された確率には **学習** が要る → ここで自前の教材（chokkan_kyouzai.py）で
  文字 n-gram のロジスティック回帰を学習し、温度で校正する。標準ライブラリだけ・重みは JSON（chokkan_omomi.json）。

  位置づけ: 頭脳（LLM）の前に置く近道。決まった言い方の表（machine.match）に当たらなかった文を、
  ここで「用件 X・自信 p」にする。自信が線（SEN）以上なら道具へ、材料は machine.zairyou か 頭脳の言い方直しで取る。
  線より低ければ今まで通り 頭脳が返事を書く（＝取りこぼしはしても 誤発動はしない側に倒す）。

  使い方:  chokkan.kimeru("ちょっと5分はかって") → {"用件": "タイマー", "自信": 0.93, "上位": [...], "ms": 1}
           python3 chokkan.py --train      … 教材から学習して chokkan_omomi.json を作る（物差しは dougu/hakaru_chokkan.py）
"""
from __future__ import annotations
import json
import math
import os
import random
import re
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
OMOMI = os.path.join(HERE, "chokkan_omomi.json")
ZATSUDAN = "雑談"
SEN = float(os.environ.get("KERNEL_CHOKKAN_SEN", "0.5"))       # 線。物差しで決めた（9/18: 0.5 で 私の36問 30/36・頭脳の91問 道具 57/61・誤発動 2/30）

_Q = re.compile(r"[「『\"“](.*?)[」』\"”]")
_NUM = re.compile(r"[0-9]+(?:[.,][0-9]+)?")


def _seiri(text: str) -> str:
    """比べるための形にする: NFKC・小文字・空白除去・「…」の中身は Q・数字は 0"""
    s = unicodedata.normalize("NFKC", text or "").lower()
    s = _Q.sub("「q」", s)
    s = _NUM.sub("0", s)
    return re.sub(r"\s+", "", s)


def tokuchou(text: str) -> dict:
    """特徴 → 値。文字 1〜3-gram（端に ^ $）と、いくつかの合図"""
    s = _seiri(text)
    f = {}
    t = "^" + s + "$"
    for n in (1, 2, 3):
        for i in range(len(t) - n + 1):
            g = t[i:i + n]
            f[g] = f.get(g, 0.0) + 1.0
    raw = text or ""
    if _NUM.search(raw):
        f["#数"] = 1.0
    if "「" in raw or '"' in raw:
        f["#引用"] = 1.0
    if raw.rstrip().endswith(("？", "?")):
        f["#問"] = 1.0
    n = len(s)
    f["#長" + ("短" if n <= 6 else "中" if n <= 16 else "長")] = 1.0
    # 出現回数は 1 に丸めてから 長さで割る（長い文で特徴が膨れないように）
    norm = 1.0 / math.sqrt(max(1, len(f)))
    return {k: norm for k in f}


class Model:
    def __init__(self, classes=None, w=None, b=None, T=1.0):
        self.classes = list(classes or [])
        self.w = w or {}          # 特徴 → [重み × クラス数]
        self.b = b or [0.0] * len(self.classes)
        self.T = T

    # ── 推論 ──
    def logits(self, f: dict) -> list:
        z = list(self.b)
        for k, v in f.items():
            row = self.w.get(k)
            if row is None:
                continue
            for c in range(len(z)):
                z[c] += row[c] * v
        return z

    def kakuritsu(self, f: dict, T: float = None) -> list:
        z = self.logits(f)
        T = self.T if T is None else T
        m = max(z)
        e = [math.exp((x - m) / T) for x in z]
        s = sum(e)
        return [x / s for x in e]

    # ── 学習（ソフトマックス回帰・SGD・L2）──
    def train(self, rei: list, epochs: int = 40, lr: float = 0.5, l2: float = 1e-5, seed: int = 0, quiet: bool = False):
        rnd = random.Random(seed)
        idx = {c: i for i, c in enumerate(self.classes)}
        feats = [(tokuchou(t), idx[c]) for t, c in rei]
        C = len(self.classes)
        # クラスの重み: 雑談の例が用件の 10倍あるので、そのままだと「分からなければ雑談」に寄る。1/√件数 でならす
        kazu = [0] * C
        for _, y in feats:
            kazu[y] += 1
        omosa = [1.0 / math.sqrt(max(1, k)) for k in kazu]
        mean = sum(omosa[y] for _, y in feats) / len(feats)
        omosa = [o / mean for o in omosa]
        for ep in range(epochs):
            rnd.shuffle(feats)
            eta = lr / (1.0 + ep * 0.15)
            loss = 0.0
            for f, y in feats:
                p = self.kakuritsu(f, T=1.0)
                loss -= math.log(max(p[y], 1e-12))
                w_y = omosa[y]
                for c in range(C):
                    g = (p[c] - (1.0 if c == y else 0.0)) * w_y
                    if abs(g) < 1e-4:
                        continue
                    self.b[c] -= eta * g
                    for k, v in f.items():
                        row = self.w.get(k)
                        if row is None:
                            row = self.w[k] = [0.0] * C
                        row[c] -= eta * (g * v + l2 * row[c])
            if not quiet and (ep % 5 == 0 or ep == epochs - 1):
                print("  epoch %2d  loss %.3f  features %d" % (ep, loss / len(feats), len(self.w)))
        return self

    def ondo(self, rei: list) -> float:
        """温度の校正: 検証用の例で 負の対数尤度が最小の T を探す（Jev の RLCD に当たる「確率を信用できるようにする」段）"""
        idx = {c: i for i, c in enumerate(self.classes)}
        feats = [(tokuchou(t), idx[c]) for t, c in rei]
        best = (float("inf"), 1.0)
        for T in [0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3]:
            nll = 0.0
            for f, y in feats:
                nll -= math.log(max(self.kakuritsu(f, T)[y], 1e-12))
            if nll < best[0]:
                best = (nll, T)
        self.T = best[1]
        return self.T

    # ── 保存・読み込み ──
    def save(self, path: str = OMOMI):
        json.dump({"classes": self.classes, "w": {k: [round(x, 4) for x in v] for k, v in self.w.items()},
                   "b": [round(x, 4) for x in self.b], "T": self.T, "made": time.strftime("%Y-%m-%d %H:%M")},
                  open(path, "w", encoding="utf-8"), ensure_ascii=False)

    @classmethod
    def load(cls, path: str = OMOMI):
        d = json.load(open(path, encoding="utf-8"))
        return cls(d["classes"], d["w"], d["b"], d.get("T", 1.0))


_MODEL = None


def model() -> Model:
    global _MODEL
    if _MODEL is None:
        _MODEL = Model.load()
    return _MODEL


def kimeru(text: str, sen: float = None) -> dict:
    """頼み文 → {"用件": 名前 or None（雑談）, "自信": p, "上位": [(名前, p)×3], "ms": ms}。自信 < 線 なら 用件 None"""
    t0 = time.monotonic()
    m = model()
    p = m.kakuritsu(tokuchou(text))
    order = sorted(range(len(p)), key=lambda i: -p[i])
    top = [(m.classes[i], round(p[i], 3)) for i in order[:3]]
    na, pa = top[0]
    sen = SEN if sen is None else sen
    out = {"用件": None, "自信": pa, "上位": top, "ms": int((time.monotonic() - t0) * 1000)}
    if na != ZATSUDAN and pa >= sen:
        out["用件"] = na
    return out


# ── 教材の用意（物差しの文は落とす）──
def _ngram2(s: str) -> set:
    s = _seiri(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def kyouzai(nozoku: list = None, quiet: bool = False) -> list:
    """教材 → [(文, 用件)]。nozoku（物差しの文）と 2-gram の重なりが 0.5 以上の文は落とす（丸暗記を測らないため）"""
    import chokkan_kyouzai as K
    import machine
    rei = []
    for na, bun in K.KYOUZAI.items():
        if na not in machine.OPS:
            continue
        for b in bun:
            rei.append((b, na))
    for b in K.ZATSUDAN:
        rei.append((b, ZATSUDAN))
    # 頭脳が作った言い方（dougu/tsukuru_iikata.py）。組=学習 だけ入れる（組=物差し は独立した物差しに使う）
    nou = os.path.join(HERE, "chokkan_kyouzai_nou.jsonl")
    if os.path.exists(nou):
        for l in open(nou, encoding="utf-8"):
            d = json.loads(l)
            if d.get("組") == "学習" and (d["用件"] == ZATSUDAN or d["用件"] in machine.OPS):
                rei.append((d["文"], d["用件"]))
    if nozoku:
        ng = [_ngram2(x) for x in nozoku]
        mae = len(rei)
        def chikai(b):
            a = _ngram2(b)
            return any(len(a & g) / max(1, len(a | g)) >= 0.5 for g in ng)
        rei = [(b, na) for b, na in rei if not chikai(b)]
        if not quiet and mae != len(rei):
            print("  物差しに近い文を %d 落とした" % (mae - len(rei)))
    return rei


def gakushuu(nozoku: list = None, seed: int = 0, quiet: bool = False) -> Model:
    """学習: 85% で学習 → 15% で温度を校正 → 全部で学習し直して保存"""
    rei = kyouzai(nozoku, quiet=quiet)
    classes = sorted({c for _, c in rei})
    rnd = random.Random(seed)
    rei2 = list(rei)
    rnd.shuffle(rei2)
    n = len(rei2)
    kensho, gaku = rei2[: n // 7], rei2[n // 7:]
    m = Model(classes).train(gaku, quiet=quiet)
    T = m.ondo(kensho)
    ok = sum(1 for t, c in kensho if m.classes[max(range(len(classes)), key=lambda i: m.kakuritsu(tokuchou(t))[i])] == c)
    if not quiet:
        print("  検証 %d/%d（教材の 1/7 を除けて測った）・温度 T=%.2f" % (ok, len(kensho), T))
    m2 = Model(classes).train(rei, quiet=True)
    m2.T = T
    m2.save()
    if not quiet:
        print("  教材 %d 文・用件 %d・特徴 %d → %s" % (len(rei), len(classes), len(m2.w), os.path.relpath(OMOMI, HERE)))
    global _MODEL
    _MODEL = m2
    return m2


if __name__ == "__main__":
    import sys
    if "--train" in sys.argv:
        gakushuu()
    else:
        for t in sys.argv[1:] or ["ちょっと5分はかって", "今日は疲れた"]:
            print(t, "→", kimeru(t))
