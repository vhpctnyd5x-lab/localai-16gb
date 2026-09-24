# -*- coding: utf-8 -*-
"""chokkan2 ── 直感役の作り直し（2026-09-22）。確率をまともにする三段: 事後確率 → 較正 → 保留。

  なぜ作り直すか（Codex の設計 dougu/kekka/shinsa_sekkei2.md）:
    ・いまの chokkan.py は softmax 回帰の生の値を自信として使っている。未知語・クラス頻度・証拠の量を
      知らないので、「知らない文ほど自信満々」になり得る。線も 1/7 の校正用 1回で決めていた。
    ・ここでは 文字 n-gram の **Dirichlet-multinomial 単純ベイズ**（共役事前分布）にする。
      未知の n-gram には事前分布が効くので、小さい教材でも確率が暴れない。
    ・較正は **交差検証の外（out-of-fold）** の予測で温度 T を決める（自分の学習点で較正しない）。
    ・保留は 2つ: 自信 < 線、または 証拠が薄い（見たことのある n-gram の割合が低い）。

  標準ライブラリだけ。重みは JSON（chokkan2_omomi.json）。使い方は chokkan.py と同じ:
    chokkan2.kimeru("5分はかって") → {"用件": "タイマー", "自信": 0.93, "証拠": 0.88, "上位": [...], "ms": 0}
    python3 chokkan2.py --train   … 学習して保存    --kuraberu … いまの chokkan と比べる
"""
from __future__ import annotations
import json, math, os, random, re, time, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
OMOMI = os.path.join(HERE, "chokkan2_omomi.json")
ZATSUDAN = "雑談"
_Q = re.compile(r"[「『\"“](.*?)[」』\"”]")
_NUM = re.compile(r"[0-9]+(?:[.,][0-9]+)?")
NGRAM = (2, 3, 4, 5)            # 文字 n-gram の長さ（1 は情報が薄いので入れない）


def _seiri(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "").lower()
    s = _Q.sub("「q」", s)
    s = _NUM.sub("0", s)
    return re.sub(r"\s+", "", s)


def tokuchou(text: str) -> dict:
    """文字 n-gram の **回数**（単純ベイズなので回数のまま。長さの効きは推論で割って消す）"""
    t = "^" + _seiri(text) + "$"
    f = {}
    for n in NGRAM:
        for i in range(len(t) - n + 1):
            g = t[i:i + n]
            f[g] = f.get(g, 0) + 1
    return f


class Model:
    """Dirichlet-multinomial 単純ベイズ。alpha は事前分布の強さ、T は温度、sen は線、shouko は証拠の下限。"""

    def __init__(self, classes=None, kazu=None, goukei=None, mae=None, V=0, alpha=0.2, T=1.0, sen=0.5, shouko=0.0, nagasa=0.5):
        self.classes = list(classes or [])
        self.kazu = kazu or {}         # n-gram → [回数 × クラス数]
        self.goukei = goukei or []     # クラスごとの総回数
        self.mae = mae or []           # log 事前確率
        self.V = V                     # 語彙の大きさ
        self.alpha, self.T, self.sen, self.shouko, self.nagasa = alpha, T, sen, shouko, nagasa

    def _logp(self, f: dict, alpha=None):
        """log p(文|用件)。長さで割ってから温度をかけるのは kakuritsu 側"""
        al = self.alpha if alpha is None else alpha
        C = len(self.classes)
        z = [0.0] * C
        shiru = 0
        n = 0
        for g, x in f.items():
            row = self.kazu.get(g)
            n += x
            if row is not None:
                shiru += x
            for c in range(C):
                cnt = row[c] if row is not None else 0
                z[c] += x * math.log((cnt + al) / (self.goukei[c] + al * self.V))
        return z, (shiru / n if n else 0.0), n

    def kakuritsu(self, f: dict, T=None, alpha=None):
        z, shouko, n = self._logp(f, alpha)
        # 長さの効きをならす（長文ほど確率が 0/1 に張り付くのを防ぐ）。nagasa=1 で完全に平均、0 で生
        w = 1.0 / max(1.0, n) ** self.nagasa
        z = [self.mae[c] + z[c] * w for c in range(len(self.classes))]
        T = self.T if T is None else T
        m = max(z)
        e = [math.exp((x - m) / T) for x in z]
        s = sum(e)
        return [x / s for x in e], shouko

    # ── 学習 ──
    def fit(self, rei: list):
        self.classes = sorted({c for _, c in rei})
        C = len(self.classes)
        idx = {c: i for i, c in enumerate(self.classes)}
        self.kazu = {}
        self.goukei = [0] * C
        kensuu = [0] * C
        for t, c in rei:
            y = idx[c]
            kensuu[y] += 1
            for g, x in tokuchou(t).items():
                row = self.kazu.get(g)
                if row is None:
                    row = self.kazu[g] = [0] * C
                row[y] += x
                self.goukei[y] += x
        self.V = len(self.kazu)
        # 事前確率: 件数そのままだと雑談（10倍ある）に寄るので √件数 でならす
        w = [math.sqrt(k) for k in kensuu]
        s = sum(w)
        self.mae = [math.log(x / s) for x in w]
        return self

    def save(self, path=OMOMI):
        tmp = path + ".tmp"
        json.dump({"classes": self.classes, "kazu": self.kazu, "goukei": self.goukei, "mae": self.mae, "V": self.V,
                   "alpha": self.alpha, "T": self.T, "sen": self.sen, "shouko": self.shouko, "nagasa": self.nagasa,
                   "made": time.strftime("%Y-%m-%d %H:%M")}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path=OMOMI):
        d = json.load(open(path, encoding="utf-8"))
        return cls(d["classes"], d["kazu"], d["goukei"], d["mae"], d["V"], d["alpha"], d["T"], d["sen"], d["shouko"], d.get("nagasa", 0.5))


_MODEL = None


def model() -> Model:
    global _MODEL
    if _MODEL is None:
        _MODEL = Model.load()
    return _MODEL


def kimeru(text: str, sen: float = None, shouko: float = None) -> dict:
    """頼み文 → {"用件": 名前 or None, "自信": p, "証拠": 0〜1, "上位": [(名, p)×3], "ms": ms}"""
    t0 = time.monotonic()
    m = model()
    p, sho = m.kakuritsu(tokuchou(text))
    o = sorted(range(len(p)), key=lambda i: -p[i])
    na, pa = m.classes[o[0]], p[o[0]]
    sen = m.sen if sen is None else sen
    shouko = m.shouko if shouko is None else shouko
    out = {"用件": None, "自信": round(pa, 3), "証拠": round(sho, 3),
           "上位": [(m.classes[i], round(p[i], 3)) for i in o[:3]], "ms": int((time.monotonic() - t0) * 1000)}
    if na != ZATSUDAN and pa >= sen and sho >= shouko:
        out["用件"] = na
    return out


# ── 学習の全体（交差検証で alpha・nagasa・温度・線を決める）──
def _oof(rei, K=5, alpha=0.2, nagasa=0.5, seed=0):
    """out-of-fold の (確率, 証拠, 正解) を返す。較正と線決めはこれだけを使う"""
    rnd = random.Random(seed)
    by = {}
    for t, c in rei:
        by.setdefault(c, []).append(t)
    fold = {}
    for c, ts in by.items():
        ts = list(ts)
        rnd.shuffle(ts)
        for i, t in enumerate(ts):
            fold[(t, c)] = i % K
    out = []
    for k in range(K):
        gaku = [(t, c) for (t, c) in rei if fold[(t, c)] != k]
        test = [(t, c) for (t, c) in rei if fold[(t, c)] == k]
        m = Model(alpha=alpha, nagasa=nagasa).fit(gaku)
        for t, c in test:
            p, sho = m.kakuritsu(tokuchou(t), T=1.0)
            out.append((p, sho, m.classes.index(c), m.classes))
    return out


def gakushuu(nozoku=None, seed=0, quiet=False, K=5):
    import chokkan as C1
    rei = C1.kyouzai(nozoku, quiet=quiet)
    best = None
    for alpha in (0.05, 0.1, 0.2, 0.5, 1.0):
        for nagasa in (0.3, 0.5, 0.7, 1.0):
            oof = _oof(rei, K, alpha, nagasa, seed)
            nll = -sum(math.log(max(p[y], 1e-12)) for p, _, y, _ in oof) / len(oof)
            if best is None or nll < best[0]:
                best = (nll, alpha, nagasa, oof)
    nll, alpha, nagasa, oof = best
    # 温度: out-of-fold の NLL 最小
    def nll_at(T):
        s = 0.0
        for p, _, y, _ in oof:
            z = [math.log(max(x, 1e-300)) / T for x in p]
            mx = max(z)
            e = [math.exp(x - mx) for x in z]
            s -= math.log(max(e[y] / sum(e), 1e-12))
        return s / len(oof)
    T = min((0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0), key=nll_at)
    # 線と証拠の下限: 雑談の誤発動 0 のまま 道具を最も拾う（out-of-fold で）
    def naosu(p, T):
        z = [math.log(max(x, 1e-300)) / T for x in p]
        mx = max(z)
        e = [math.exp(x - mx) for x in z]
        s = sum(e)
        return [x / s for x in e]
    bestsen = None
    for sen in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
        for sho_min in (0.0,):   # 証拠の下限は 独立した物差し2 で 149問中 3問しか拾えず（移らない）→ 使わない（2026-09-22 実測）
            ok = go = 0
            for p, sho, y, cls in oof:
                q = naosu(p, T)
                i = max(range(len(q)), key=lambda j: q[j])
                deru = cls[i] != ZATSUDAN and q[i] >= sen and sho >= sho_min
                if cls[y] == ZATSUDAN:
                    go += deru
                else:
                    ok += (deru and i == y)
            # 誤発動を最小に、同じなら道具を多く拾う方（誤発動 0 が無い教材でも決まる）
            if bestsen is None or (go, -ok) < (bestsen[3], -bestsen[2]):
                bestsen = (sen, sho_min, ok, go)
    m = Model(alpha=alpha, nagasa=nagasa).fit(rei)
    m.T, m.sen, m.shouko = T, bestsen[0], bestsen[1]
    m.save()
    if not quiet:
        print("  教材 %d文・用件 %d・n-gram %d種  alpha=%.2f 長さ%.1f T=%.2f 線=%.2f 証拠≧%.1f  (OOF NLL %.3f・OOF 道具 %d拾い・雑談の誤発動 %d)"
              % (len(rei), len(m.classes), m.V, alpha, nagasa, T, m.sen, m.shouko, nll, bestsen[2], bestsen[3]))
    global _MODEL
    _MODEL = Model.load()
    return _MODEL


if __name__ == "__main__":
    import sys
    if "--train" in sys.argv:
        gakushuu()
    else:
        for t in sys.argv[1:] or ["ちょっと5分はかって", "今日は疲れた"]:
            print(t, "→", kimeru(t))
