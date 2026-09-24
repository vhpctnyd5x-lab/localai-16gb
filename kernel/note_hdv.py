#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
note_hdv.py -- 「にた状況」で引けるノート

  いままでのノートは、形が1文字でも違うと当たらなかった。

      覚えた形: 動作+場所+種類 / 数える
      来た形  : 動作+場所+種類+時期 / 数える   ← 当たらない。0からやり直し

  ここでは状況まるごとを1本の1万ビットにして、いちばん近い過去を探す。

      場所=Desktop  →  むすぶ(atom「枠:場所」, atom「値:Desktop」)   ← XOR
      種類=画像     →  むすぶ(atom「枠:種類」, atom「値:画像」)
      ぜんぶ たばねる（多数決）

  掛け算は1回も使わない。使うのは XOR・AND・OR・ビット数え だけ。

  【大事な決めごと】
  にている過去から出てきた手順は、そのまま実行しない。
  必ず下見（try_plan）で確かめてから使う。
  「にている」は当てずっぽうなので、確かめる係を挟まないと危ない。
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hdv

# 枠ごとの重み。手順を決めるのは、ほとんど「動作」なので重くする。
#
#   重みを付けずに試したら「重複＋場所＋種類」が
#   「数える＋場所＋種類」に引かれた。場所と種類の票数で負けたため。
#   実測（見たことのない5問）:
#       重み2 → 3/5  近さ平均 0.737   （他の枠も効いている）
#       重み3 → 4/5  近さ平均 0.836   ← ここが正直な最適
#       重み4 → 4/5  近さ平均 0.940   （2問が完全一致＝動作だけで決まった）
#       重み7 → 5/5  近さ平均 1.000   （全問が動作だけ。にている判定をしていない）
#   重み7の5/5は見かけ倒し。1万ビットを使う意味が消えるので採らない。
WEIGHT = {"動作": 3, "種類": 2, "時期": 2, "除く": 2,
          "場所": 1, "名前": 1, "行き先": 1, "対象": 1, "パス": 1}

# これ以下の近さなら「にていない」として使わない。
# でたらめな2本は必ず 0.50 になるので、0.62 は「偶然ではない」と言える線
MIN_NEAR = 0.62


def _flat(v):
    if isinstance(v, (list, tuple)):
        return "/".join(map(str, v))
    return str(v)


def encode(slots):
    """状況（スロット）を、1本の1万ビットにする"""
    vs, ws = [], []
    for k, v in sorted(slots.items()):
        vs.append(hdv.bind(hdv.atom("枠:" + str(k)), hdv.atom("値:" + _flat(v))))
        ws.append(WEIGHT.get(k, 1))
    return hdv.bundle_bits(vs, ws) if vs else 0


class SimNote:
    """状況 → 手順 の記憶。にた状況でも引ける

    中身は JSON（人が読める）。1万ビットは読み込むときに作り直す。
    保存すると46MBになってしまうし、作り直しは一瞬なので持たない。
    """

    def __init__(self, path=None):
        self.path = path
        self.items = []              # [{"枠": slots, "手順": plan, "回数": n}]
        self._vecs = []              # 上と同じ並びの1万ビット
        if path and os.path.exists(path):
            self.load()

    # --- 出し入れ ---
    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self.items = json.load(f)
        except Exception:
            self.items = []
        self._vecs = [encode(it["枠"]) for it in self.items]
        return self

    def save(self):
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # --- 覚える ---
    def add(self, slots, plan):
        slots = {k: _flat(v) for k, v in slots.items()}
        plan = list(plan)
        for it in self.items:
            if it["枠"] == slots and it["手順"] == plan:
                it["回数"] = it.get("回数", 1) + 1
                self.save()
                return
        self.items.append({"枠": slots, "手順": plan, "回数": 1})
        self._vecs.append(encode(slots))
        self.save()

    # --- 思い出す ---
    def recall(self, slots, n=3, floor=MIN_NEAR):
        """にている順に (近さ, 過去のスロット, 手順) を返す"""
        if not self.items:
            return []
        q = encode({k: _flat(v) for k, v in slots.items()})
        scored = []
        for v, it in zip(self._vecs, self.items):
            s = hdv.near(q, v)
            if s >= floor:
                scored.append((s, it["枠"], it["手順"]))
        scored.sort(key=lambda x: -x[0])
        return scored[:n]

    def __len__(self):
        return len(self.items)


if __name__ == "__main__":
    import time
    LEARNED = [
        ({"動作": "数える", "場所": "Desktop", "種類": "画像"},
         ["さがす", "しぼる(種類)", "かぞえる"]),
        ({"動作": "一覧", "場所": "Desktop"}, ["さがす", "ならべる"]),
        ({"動作": "移動", "場所": "Desktop", "種類": "画像", "時期": "去年"},
         ["さがす", "しぼる(種類)", "しぼる(時期)", "つくる", "うつす"]),
        ({"動作": "数える", "場所": "Downloads", "種類": "PDF"},
         ["さがす", "しぼる(種類)", "かぞえる"]),
        ({"動作": "移動", "場所": "Desktop"}, ["さがす", "しわけ"]),
        ({"動作": "重複", "場所": "Desktop"}, ["さがす", "かさなり"]),
    ]
    NEW = [
        ({"動作": "数える", "場所": "Downloads", "種類": "画像", "時期": "今月"},
         ["さがす", "しぼる(種類)", "かぞえる"], "数える＋種類 の形"),
        ({"動作": "一覧", "場所": "Downloads", "種類": "動画"},
         ["さがす", "ならべる"], "一覧の形"),
        ({"動作": "移動", "場所": "Downloads", "種類": "音楽", "時期": "先月"},
         ["さがす", "しぼる(種類)", "しぼる(時期)", "つくる", "うつす"], "移動＋2条件"),
        ({"動作": "重複", "場所": "Downloads", "種類": "PDF"},
         ["さがす", "かさなり"], "重複の形"),
        ({"動作": "数える", "場所": "Desktop", "種類": "書類", "名前": "会議"},
         ["さがす", "しぼる(種類)", "かぞえる"], "名前つきの数える"),
    ]
    def shape(s): return "+".join(sorted(s)) + " / " + s.get("動作", "?")

    mem = SimNote()
    for s, p in LEARNED:
        mem.items.append({"枠": s, "手順": p, "回数": 1})
        mem._vecs.append(encode(s))
    old = {shape(s): p for s, p in LEARNED}
    hit_old = sum(1 for s, _p, _n in NEW if shape(s) in old)

    print("■ 見たことのない状況で、正しい手順を思い出せるか")
    ok, t0 = 0, time.time()
    for slots, want, label in NEW:
        got = mem.recall(slots, 1)
        if not got:
            print(f"  ✗ {label}  → にた過去なし")
            continue
        s, past, plan = got[0]
        good = plan == want
        ok += good
        print(f"  {'✓' if good else '✗'} {label}")
        print(f"      引いた過去: {shape(past)}  （近さ {s:.3f}）")
        print(f"      出た手順  : {' → '.join(plan)}")
    ms = (time.time() - t0) * 1000
    print("=" * 60)
    print(f"  いまのノート（形が完全一致）: {hit_old}/{len(NEW)} 当たった")
    print(f"  1万ビット（にている順）    : {ok}/{len(NEW)} 当たった"
          f"  （{ms:.1f} ミリ秒・かけ算 0回）")
