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
SEN = float(os.environ.get("KERNEL_CHOKKAN_SEN", "0.5"))       # 線の既定。学習時に校正用で決めた値（重みの sen）があればそちら

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
    def __init__(self, classes=None, w=None, b=None, T=1.0, sen=None):
        self.classes = list(classes or [])
        self.w = w or {}          # 特徴 → [重み × クラス数]
        self.b = b or [0.0] * len(self.classes)
        self.T = T
        self.sen = sen            # 校正用で決めた線（None なら SEN）

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
        """原子的に書く（途中で落ちても前の重みが残る）。丸めは 6桁（4桁だと測った値と読み直した値がずれる・Codex の審査）"""
        tmp = path + ".tmp"
        json.dump({"classes": self.classes, "w": {k: [round(x, 6) for x in v] for k, v in self.w.items()},
                   "b": [round(x, 6) for x in self.b], "T": self.T, "sen": self.sen, "made": time.strftime("%Y-%m-%d %H:%M")},
                  open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str = OMOMI):
        d = json.load(open(path, encoding="utf-8"))
        return cls(d["classes"], d["w"], d["b"], d.get("T", 1.0), d.get("sen"))


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
    na, pa = m.classes[order[0]], p[order[0]]          # ★ 線の判定は丸める前の値で（Codex の審査 9/18）
    sen = (m.sen if m.sen is not None else SEN) if sen is None else sen
    out = {"用件": None, "自信": round(pa, 3), "上位": top, "ms": int((time.monotonic() - t0) * 1000)}
    if na != ZATSUDAN and pa >= sen:
        out["用件"] = na
    return out


# ── 教材の用意（物差しの文は落とす）──
def _ngram2(s: str) -> set:
    s = _seiri(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def monosashi_no_bun() -> list:
    """物差し（dougu/hakaru_erabu.py の DOUGU・BETSU・ZATSUDAN）の文。見つからなければ空。
    ★ Codex の審査（9/18）: --train が物差しを除かずに学習できてしまっていた → いつも除く"""
    for d in (os.path.join(HERE, "..", "koukai", "dougu"), os.path.join(HERE, "..", "dougu"), os.path.expanduser("~/LocalAI_mirror/koukai/dougu")):
        f = os.path.join(d, "hakaru_erabu.py")
        if os.path.isfile(f):
            import importlib.util
            spec = importlib.util.spec_from_file_location("hakaru_erabu", f)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception:
                continue
            return [t for t, _ in mod.DOUGU] + [t for t, _ in mod.BETSU] + list(mod.ZATSUDAN)
    return []


def kyouzai(nozoku: list = None, quiet: bool = False) -> list:
    """教材 → [(文, 用件)]。物差しの文（自動で集める＋nozoku）と 2-gram の重なりが 0.5 以上の文は落とす（丸暗記を測らないため）"""
    import chokkan_kyouzai as K
    import machine
    nozoku = list(nozoku or []) + monosashi_no_bun()
    rei = []
    for na, bun in K.KYOUZAI.items():
        if na not in machine.OPS:
            continue
        for b in bun:
            rei.append((b, na))
    for b in K.ZATSUDAN:
        rei.append((b, ZATSUDAN))
    # 頭脳が作った言い方（dougu/tsukuru_iikata.py）。組=学習 だけ入れる（組=物差し は独立した物差しに使う）
    # 雲の先生が作った言い方（dougu/tsukuru_iikata_kumo.py）も 組=学習 だけ（9/19 測って差なし 27→28・誤発動 2→3 → 既定は入れない。KERNEL_KUMO=1 で入れる）
    files = ["chokkan_kyouzai_nou.jsonl"] + (["chokkan_kyouzai_kumo.jsonl"] if os.environ.get("KERNEL_KUMO", "0") == "1" else [])
    for fn in files:
        nou = os.path.join(HERE, fn)
        if not os.path.exists(nou):
            continue
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
    """学習: 用件ごとに層化して 6/7 で学習 → 残り 1/7（校正用）で温度と線（SEN）を決める → **その模型を保存**。
    ★ 前は校正のあと全部で学習し直していた（校正が保存した模型のものでない・Codex の審査 9/18）。
    線は 校正用で「雑談の誤発動 0 のまま 道具を最も拾う値」。物差し（held-out）は線を決めるのに使わない。"""
    rei = kyouzai(nozoku, quiet=quiet)
    classes = sorted({c for _, c in rei})
    rnd = random.Random(seed)
    by = {}
    for t, c in rei:
        by.setdefault(c, []).append(t)
    gaku, kensho = [], []
    for c, ts in by.items():
        ts = list(ts)
        rnd.shuffle(ts)
        k = max(1, len(ts) // 7) if len(ts) >= 3 else 0
        kensho += [(t, c) for t in ts[:k]]
        gaku += [(t, c) for t in ts[k:]]
    m = Model(classes).train(gaku, quiet=quiet)
    T = m.ondo(kensho)
    # 線: 校正用で 雑談を道具と間違えない範囲で いちばん道具を拾う値
    best = (0.5, -1)
    for sen in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        ok = gobatsu = 0
        for t, c in kensho:
            p = m.kakuritsu(tokuchou(t))
            i = max(range(len(classes)), key=lambda j: p[j])
            na, pa = classes[i], p[i]
            if c == ZATSUDAN:
                gobatsu += (na != ZATSUDAN and pa >= sen)
            else:
                ok += (na == c and pa >= sen)
        if gobatsu == 0 and ok > best[1]:
            best = (sen, ok)
    m.sen = best[0]
    ok = sum(1 for t, c in kensho if classes[max(range(len(classes)), key=lambda j: m.kakuritsu(tokuchou(t))[j])] == c)
    if not quiet:
        print("  校正用 %d文（用件ごとに 1/7）: 当たり %d/%d・温度 T=%.2f・線 SEN=%.1f" % (len(kensho), ok, len(kensho), T, m.sen))
    m.save()
    if not quiet:
        print("  教材 %d 文（学習 %d）・用件 %d・特徴 %d → %s" % (len(rei), len(gaku), len(classes), len(m.w), os.path.relpath(OMOMI, HERE)))
    global _MODEL
    _MODEL = Model.load()          # 読み直した模型を使う（保存した物と測る物を同じにする）
    return _MODEL


if __name__ == "__main__":
    import sys
    if "--train" in sys.argv:
        gakushuu()
    else:
        for t in sys.argv[1:] or ["ちょっと5分はかって", "今日は疲れた"]:
            print(t, "→", kimeru(t))
