#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
policy.py -- 「次に置くべき部品」の順番を、過去の実績から学ぶ係

kernel.py の solve() は PARTS の辞書順で総当たりしている。
部品が増えるほど、無駄な枝を先に踏む回数が増えて破綻する。

この係は「どんな場面で、どの部品を置いたら成功したか」を数えておき、
次からは有望な順に並べ替えて返す。

  - 文脈キー … 「どのスロットが埋まっているか」＋「直前に置いた部品」の組。
               細かい版（スロットの値まで入れる）と粗い版（名前＋動作だけ）の
               2段構えにして、細かい版に実績が無ければ粗い版に落ちる。
  - 数える   … (文脈キー, 部品) ごとに 成功回数 / 失敗回数
  - 並べ方   … ウィルソン得点区間の下限（信頼区間の下限）で降順

素の成功率だと「1勝0敗(=1.00)」が「10勝1敗(=0.91)」より上に来てしまう。
下限を使えば、試行回数が少ないものは自動的に割り引かれる。

未試行の部品には固定の中立スコア(UNKNOWN)を与える。
  実績のある良い部品 > 未試行 > 実績のある悪い部品
という並びになるので、悪い部品より後ろに回されて永久に試されない、
という事故は起きない。

kernel.py は一切変更しない。使う側はこうする:

    import kernel, policy
    pol = policy.Policy()
    ...
    for name in pol.order(candidates, slots, path):
        ...
    pol.win(slots, plan)          # 成功したら
    pol.lose(slots, path, name, 理由)   # 枝が落ちたら

おまけに rank(slots, path) がある。探索の待ち行列をこれで並べ替えると
（＝幅優先ではなく、有望なほうから先に深く掘る）効きが桁違いに大きい。
実測: 部品16個・4種類の命令で 合計2936回 →
      並べ替えだけ(幅優先のまま) 1734回 / 待ち行列も並べ替え 180回
"""

import os, json, math, time, atexit

HERE = os.path.dirname(os.path.abspath(__file__))

# ウィルソン区間の z 値。1.0 ≒ 片側 84% くらい。
# 大きくすると慎重（実績を信用しない）、小さくすると大胆になる。
Z = 1.0

# ── UCB（試した回数に応じて持ち上げる）の強さ ──────────────
#
#   もとは「勝率の下限（ウィルソン）」で並べ、
#   試していない枝には固定の 0.5 を与えていた。
#   これが、自分で練習させた途端に破綻した。実測:
#       1500回 練習 → 覚えた枝 1,430本／点数の中央値 0.000
#                     0.5 を超える枝は 58本（4%）だけ
#       つまり「試したことのある枝」が
#             「試したことのない枝」より ほぼ必ず下に来る
#       → 探索順が壊れて 24/40 → 0/40
#   ランダムに試すと ほとんど失敗するので、
#   悲観的な下限では、稀な成功が失敗の海に溺れる。
#
#   直し方: 固定の点と比べるのをやめ、
#           「同じ場面の兄弟どうし」で比べる。
#               点 = 勝率 ＋ C × √( log(その場面の総試行) ÷ その枝の試行 )
#           試した回数が少ない枝ほど、後ろの項が大きくなって持ち上がる。
#           何度も試して駄目だった枝は、素直に下がる。
#   C を大きくすると冒険的、小さくすると保守的になる。
UCB_C = 0.7

# まだ一度も試していない (文脈キー, 部品) に与える中立スコア。
# 「実績のある良い部品」はこれを超え、「実績のある悪い部品」はこれを下回る。
UNKNOWN = 0.5

# 探索の開始地点（直前の部品が無い）を表す印
ROOT = "^"

# 何回ぶん変更を溜めたら保存するか
SAVE_EVERY = 200

# 前にディスクへ書いてから、次に書くまでの最短の間（秒）
MIN_GAP = 10.0

# rank() で「1手長い」ことに付ける罰。小さすぎると無駄な手順を掴み、
# 大きすぎると幅優先に戻ってしまう。
LEN_PENALTY = 0.0

# rank() の中で未試行の一手に与える値（UNKNOWN より低め）
UNKNOWN_IN_RANK = 0.2


# 同じ (成功数, 失敗数) の組は、何万回も出てくる。
# 毎回 平方根から計算し直していたので、練習で経験が増えるほど
# かえって遅くなっていた（実測 441ms → 1,163ms）。
# 学び方ではなく、覚え方のほうが足を引っぱっていた。
_WCACHE = {}


def _wilson_lower(win, lose, z=Z):
    """ウィルソン得点区間の下限。試行が少ないほど 0 に近く割り引かれる"""
    got = _WCACHE.get((win, lose))
    if got is not None:
        return got
    got = _wilson_calc(win, lose, z)
    if len(_WCACHE) < 200000:
        _WCACHE[(win, lose)] = got
    return got


def _wilson_calc(win, lose, z=Z):
    n = win + lose
    if n <= 0:
        return UNKNOWN
    p = win / n
    denom = 1.0 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (center - margin) / denom)


_CKCACHE = {}


def context_keys(slots, path):
    """文脈キーを、細かい順に並べて返す

    2段構えにする。

      細 … スロットの「値」まで入れたキー。
            例「場所=Desktop」と「場所=Downloads」では最善手が違う
            （Desktop は入れ子があるので「もぐる」、Downloads は「さがす」）ので、
            ここを一緒くたにすると学習が混ざって邪魔をする。
      粗 … スロットの「名前」＋「動作の値」だけのキー。
            初めて見る場所・種類でも、形が同じなら過去の実績を流用できる。

    どちらにも「直前に置いた部品」を入れる。
    同じ場面でも、直前が何かで次の最善手は変わるため。
    """
    last = path[-1] if path else ROOT
    # 同じ場面・同じ直前の手は、探索の中で何度も出てくる。
    # 文字列を毎回つなぎ直さず、一度作ったら覚えておく
    kagi = (tuple(sorted(slots.items())), last)
    got = _CKCACHE.get(kagi)
    if got is not None:
        return got
    names = "+".join(sorted(slots.keys()))
    act = slots.get("動作", "?")
    fine = "|".join(f"{k}={slots[k]}" for k in sorted(slots))
    got = [f"S:{fine}/{last}", f"G:{names}/{act}/{last}"]
    if len(_CKCACHE) < 50000:
        _CKCACHE[kagi] = got
    return got


def context_key(slots, path):
    """代表キー（粗いほう）。外から文脈を1つの文字列で見たいとき用"""
    return context_keys(slots, path)[-1]


class Policy:
    def __init__(self, path="policy.json"):
        if not os.path.isabs(path):
            path = os.path.join(HERE, path)
        self.path = path
        # {文脈キー: {部品名: {"w": 成功数, "l": 失敗数, "r": {理由: 回数}}}}
        self.table = {}
        self.autosave = True
        self._pending = 0
        self._last_save = 0.0
        self._sou = {}          # 場面ごとの総試行数（数え直さないための控え）
        self._load()
        atexit.register(self.flush)

    # ---------------- 保存と読み込み ----------------
    def _load(self):
        """壊れた JSON でも落ちない。読めなければ空から始める"""
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self.table = {}
            return
        if not isinstance(data, dict):
            self.table = {}
            return
        clean = {}
        for ctx, parts in (data.get("table") or data).items():
            if not isinstance(ctx, str) or not isinstance(parts, dict):
                continue
            cp = {}
            for part, rec in parts.items():
                if not isinstance(part, str) or not isinstance(rec, dict):
                    continue
                try:
                    w = int(rec.get("w", 0))
                    l = int(rec.get("l", 0))
                except Exception:
                    continue
                r = rec.get("r")
                cp[part] = {"w": max(0, w), "l": max(0, l),
                            "r": r if isinstance(r, dict) else {}}
            if cp:
                clean[ctx] = cp
        self.table = clean

    def save(self):
        """途中で失敗しても元ファイルを壊さないよう、書いてから差し替える

        ここが練習の足を引っぱっていた。
        経験が増えるほど書き出す量が増え、1回 1.26 秒かかっていた。
        40問 解く間に 5回 呼ばれ、6.7秒のうち 6.3秒 が書き出しだった。
        学ぶのはほぼ無料で、覚え書きを紙に写す作業だけが重かった。

        直し方は3つ:
          ・見やすさのための字下げ(indent)をやめる（量が半分以下になる）
          ・回数ではなく「時間」で区切る（何回変わっても、
            10秒に1回より多くは書かない）
          ・ほとんど出てこない枝は捨てる（表が太らない）
        """
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"table": self._karui()}, f,
                          ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, self.path)
            self._pending = 0
            self._last_save = time.time()
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass

    # ---------------- 記録 ----------------
    # lose() は探索1回につき何千回も呼ばれるので、毎回書き込むと遅い。
    # 変更を溜めておいて、区切りごと（と終了時）にまとめて書く。
    KARUI_MAX = 20000        # 表に残す場面の数の上限

    def _karui(self):
        """書き出す前に、痩せさせる。
        一度も勝ったことがなく、たった1回しか試していない枝は、
        覚えていても役に立たない（未試行と同じ扱いになるため）"""
        if len(self.table) <= self.KARUI_MAX:
            out = {}
            for ctx, parts in self.table.items():
                cp = {k: v for k, v in parts.items()
                      if v["w"] or v["l"] >= 2}
                if cp:
                    out[ctx] = cp
            return out
        # それでも多すぎるときは、よく通った場面から順に残す
        omoi = sorted(self.table.items(),
                      key=lambda kv: -sum(x["w"] + x["l"] for x in kv[1].values()))
        return dict(omoi[:self.KARUI_MAX])

    def _dirty(self):
        self._sou.clear()
        self._pending += 1
        if not self.autosave:
            return
        # 回数ではなく時間で区切る。何回変わっても、
        # 前に書いてから MIN_GAP 秒たつまでは書かない
        if (self._pending >= SAVE_EVERY
                and time.time() - self._last_save >= MIN_GAP):
            self.save()

    def flush(self):
        """溜めた変更を確実に書き出す"""
        if self._pending:
            self.save()

    def _rec(self, ctx, part):
        return self.table.setdefault(ctx, {}).setdefault(part, {"w": 0, "l": 0, "r": {}})

    def win(self, slots, plan):
        """成功した手順を記録する。手順の各段を「その文脈での正解」として数える"""
        if not plan:
            return
        for i, part in enumerate(plan):
            for ctx in context_keys(slots, plan[:i]):   # 細・粗の両方に入れる
                self._rec(ctx, part)["w"] += 1
        self._dirty()

    def lose(self, slots, path, part, reason=""):
        """ある文脈である部品を置いて失敗したことを記録する"""
        for ctx in context_keys(slots, path):
            rec = self._rec(ctx, part)
            rec["l"] += 1
            if reason:
                r = rec.setdefault("r", {})
                key = str(reason)[:60]
                r[key] = r.get(key, 0) + 1
        self._dirty()

    # ---------------- 並べ替え ----------------
    def _known(self, ctxs, part):
        """その (文脈, 部品) に実績があるか。
        ウィルソン下限はたまたま UNKNOWN と同じ値になることがある
        （1勝0敗は z=1 でちょうど 0.5）ので、値では判定しない"""
        if isinstance(ctxs, str):
            ctxs = [ctxs]
        for ctx in ctxs:
            rec = self.table.get(ctx, {}).get(part)
            if rec and (rec["w"] or rec["l"]):
                return True
        return False

    def _souryou(self, ctx):
        """その場面で、これまで何回ためしたか（兄弟ぜんぶの合計）"""
        got = self._sou.get(ctx)
        if got is None:
            got = sum(r["w"] + r["l"] for r in self.table.get(ctx, {}).values())
            self._sou[ctx] = got
        return got

    def score(self, ctxs, part):
        """細かいキーに実績があればそれを使い、無ければ粗いキーに落ちる。

        点の付け方は UCB。同じ場面の兄弟どうしで比べる（上の説明を参照）
        """
        if isinstance(ctxs, str):
            ctxs = [ctxs]
        for ctx in ctxs:
            rec = self.table.get(ctx, {}).get(part)
            if rec and (rec["w"] or rec["l"]):
                n = rec["w"] + rec["l"]
                N = max(self._souryou(ctx), n)
                return rec["w"] / n + UCB_C * math.sqrt(math.log(N + 1) / n)
        # 一度も試していない枝。いちばん先に一度は試す
        for ctx in ctxs:
            N = self._souryou(ctx)
            if N:
                return 1.0 + UCB_C * math.sqrt(math.log(N + 1))
        return UNKNOWN

    def order(self, candidates, slots, path):
        """試すべき順に並べ替えて返す

        実績がまったく無い文脈なら candidates の順序をそのまま返す（安全側）。
        実績があれば、スコアの高い順。同点なら元の順序を保つ（安定ソート）。
        """
        if not candidates:
            return list(candidates)
        ctxs = context_keys(slots, path)
        known = set()
        for ctx in ctxs:
            known |= set(self.table.get(ctx, {}).keys())
        if not known or not any(c in known for c in candidates):
            return list(candidates)                       # 実績なし → 触らない
        return sorted(candidates, key=lambda c: -self.score(ctxs, c))

    def rank(self, slots, path):
        """途中まで置いた手順そのものの「見込み」。0.0〜1.0、大きいほど有望

        order() は兄弟の並べ替えしかできない。幅優先だと「浅い層を全部なめてから
        次の層」なので、正解が深いところにあると並べ替えだけでは効きが薄い。
        探索の待ち行列をこの値で並べ替えると（＝有望なほうから先に深く掘る）、
        試行回数が大きく減る。使うかどうかは呼ぶ側の自由。
        """
        if not path:
            return UNKNOWN
        # 未試行の一手は、並べ替え(order)では中立に扱うが、
        # 手順まるごとの見込み(rank)では低めに見る。そうしないと
        # 「無駄な一手を挟んだ長い手順」が先に見つかってしまう。
        vals = []
        for i, part in enumerate(path):
            ctxs = context_keys(slots, path[:i])
            vals.append(self.score(ctxs, part) if self._known(ctxs, part)
                        else UNKNOWN_IN_RANK)
        return sum(vals) / len(vals) - LEN_PENALTY * len(path)

    # 注: rank() は「手順まるごとの見込み」なので、
    #     未試行の一手は UNKNOWN_IN_RANK のまま低く見ておく。
    #     ここまで UCB にすると、無駄な一手を挟んだ長い手順が
    #     先に浮かんできてしまう（実測で確認済み）

    # ---------------- 確認用 ----------------
    def stats(self):
        ctxs = len(self.table)
        pairs = wins = losses = 0
        top = []
        for ctx, parts in self.table.items():
            for part, rec in parts.items():
                pairs += 1
                wins += rec["w"]
                losses += rec["l"]
                top.append((round(_wilson_lower(rec["w"], rec["l"]), 3),
                            ctx, part, rec["w"], rec["l"]))
        top.sort(key=lambda t: -t[0])
        return {
            "文脈数": ctxs,
            "組合せ数": pairs,
            "成功のべ": wins,
            "失敗のべ": losses,
            "保存先": self.path,
            "上位": [{"文脈": c, "部品": p, "勝": w, "負": l, "得点": s}
                     for s, c, p, w, l in top[:10]],
        }

    def __repr__(self):
        s = self.stats()
        return f"<Policy 文脈{s['文脈数']} 組合せ{s['組合せ数']} 勝{s['成功のべ']} 負{s['失敗のべ']}>"


if __name__ == "__main__":
    print(json.dumps(Policy().stats(), ensure_ascii=False, indent=2))
