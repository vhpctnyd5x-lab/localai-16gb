#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yosoku.py -- 先に気づく。予測と、おどろき

  【なぜ】
  いまのカーネルは、聞かれてから動く。だから道具に見える。
  生き物っぽさは「聞かれる前に、次に来るものを構えている」ところから出る。

  【仕組み（脳の予測符号化と同じ形）】
      いまの様子 → 次に来るものを 予想して 持っておく
                 → 実際に来たものと くらべる
                 → ちがった分（おどろき）だけ 覚える
  合っているうちは何も学ばない。おどろいたときだけ学ぶ。
  これで、いつもの事は静かになり、変な事だけが目立つ。

  【おどろきの使い道】
      小さい → 黙って先回りしておく（候補を出す）
      大きい → 声をかける（「いつもと違いますね」）
  つまり、いつ口を開くかを、機械が自分で決められる。

  【掛け算】
  数え表を引くだけ。1万ビットの近さも XOR と数えるだけ。
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "yosoku.json")


def _key(e):
    return "|".join(f"{k}={e[k]}" for k in sorted(e))


def _vec(e):
    vs = [hdv.bind(hdv.atom("枠:" + k), hdv.atom("値:" + str(v)))
          for k, v in e.items()]
    return hdv.bundle_bits(vs) if vs else 0


class Mimamori:
    """見張って、次を構える"""

    def __init__(self, oku=3):
        self.oku = oku            # いくつ前まで手がかりにするか
        self.tbl = {}             # 手がかり -> {次の出来事: 回数}
        self.rireki = []
        self.mita = {}            # 出来事の鍵 -> 中身
        self.odoroki = []         # (時刻, おどろき, 出来事)

    # ---- 構える ----------------------------------------------------
    def yosou(self, k=3):
        """次に来そうな出来事を、多い順に"""
        for n in range(min(self.oku, len(self.rireki)), 0, -1):
            te = "→".join(self.rireki[-n:])
            d = self.tbl.get(te)
            if d:
                s = sorted(d.items(), key=lambda x: -x[1])[:k]
                zen = sum(d.values())
                return [(self.mita.get(a, a), v / zen, n) for a, v in s]
        return []

    # ---- 来たものと くらべて、おどろいた分だけ覚える ----------------
    def kita(self, e):
        key = _key(e)
        self.mita[key] = e
        mae = self.yosou(5)
        if not mae:
            od = 1.0                      # 何も構えていなかった＝まるごと驚き
        else:
            atari = next((p for x, p, _ in mae if _key(x) == key), 0.0)
            if atari:
                od = 1.0 - atari          # 当てていたら、おどろかない
            else:
                # 形は近いか（1万ビットで見る）。近ければ おどろきは小さい
                v = _vec(e)
                chikai = max(hdv.near(v, _vec(x)) for x, _, _ in mae)
                od = 1.0 - 0.5 * chikai

        for n in range(1, self.oku + 1):
            if len(self.rireki) >= n:
                te = "→".join(self.rireki[-n:])
                d = self.tbl.setdefault(te, {})
                d[key] = d.get(key, 0) + 1
        self.rireki.append(key)
        self.odoroki.append((len(self.rireki), od, e))
        return od

    def futsuu(self, mado=40):
        """ふだんの おどろき の大きさ（この上に出たら「変」）

        二度まちがえた所。
        ① ぜんぶの履歴で測る → 覚えたての「まるごと驚き」が混ざり、
           いつまでも 1.00 のままで、何にも驚けない
        ② 近ごろの 9割目 で測る → 履歴が十数件しかないと、
           9割目そのものが 1.00 になってしまい、やはり驚けない
        まん中（中央値）に、少し足したものを基準にする。
        くせが付いていれば まん中は 0 に近いので、
        ふだんと違うことだけが、はっきり上に出る。
        """
        v = sorted(o for _, o, _ in self.odoroki[-mado:])
        if len(v) < 6:
            return 1.0
        mannaka = v[len(v) // 2]
        return max(0.30, min(1.0, mannaka + 0.30))

    def nankai(self, e):
        """この出来事を、これまで何回見たか"""
        return self.rireki.count(_key(e))

    def hen(self, od, e=None):
        """声をかけるべきか。

        おどろきだけで決めると、うるさい。
        一度いつもと違うことをすると、その次の「いつもの操作」まで
        （並びが崩れたせいで）驚いてしまうため。
        ふだんやっていること自体は、順番が変でも黙っている。
        """
        if od <= self.futsuu():
            return False
        if e is not None and self.nankai(e) >= 3:
            return False          # よくやること。順番が違うだけなら黙る
        return True

    # ---- しまう ----------------------------------------------------
    def save(self, path=STORE):
        # おどろきの履歴も残す。ここを保存し忘れていて、
        # 立ち上げ直すたびに「ふだんの おどろき」が 1.00 に戻り、
        # 何が起きても驚けない状態になっていた（実測で発覚）
        json.dump({"oku": self.oku, "tbl": self.tbl,
                   "rireki": self.rireki[-500:], "mita": self.mita,
                   "おどろき": [[a, b] for a, b, _c in self.odoroki[-200:]]},
                  open(path, "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))

    def load(self, path=STORE):
        d = json.load(open(path, encoding="utf-8"))
        self.oku, self.tbl = d["oku"], d["tbl"]
        self.rireki, self.mita = d["rireki"], d["mita"]
        self.odoroki = [(a, b, {}) for a, b in d.get("おどろき", [])]
        return self


# ------------------------------------------------------------------
def tameshi():
    import random
    rnd = random.Random(0)
    print("■ くせ を覚えて、先に構えられるか\n")
    m = Mimamori()

    # 作りごとの「いつもの一日」。
    #   朝: メールを見る → 書類を開く → 保存
    #   昼: 画像を整理
    #   夜: 動画を見る
    asa = [{"事": "メール"}, {"事": "書類をひらく"}, {"事": "保存"}]
    hiru = [{"事": "画像を整理"}, {"事": "保存"}]
    yoru = [{"事": "動画"}, {"事": "音量"}]
    hi = asa + hiru + yoru

    for d in range(14):
        for e in hi:
            m.kita(dict(e, 曜=["月","火","水","木","金","土","日"][d % 7]))

    # 15日目。当てられるか
    print("  15日目。次に何が来るか、来る前に言う:")
    atari = 0
    for e in hi:
        y = m.yosou(1)
        iu = y[0][0]["事"] if y else "（構えなし）"
        od = m.kita(dict(e, 曜="月"))
        ok = (iu == e["事"])
        atari += ok
        print(f"    {'✓' if ok else '✗'} 構え「{iu}」 ← 実際「{e['事']}」"
              f"   おどろき {od:.2f}")
    print(f"    {atari}/{len(hi)} 当てた")

    print(f"\n  ふだんの おどろき: {m.futsuu():.2f}")
    print("\n  ── いつもと違うことが起きたら ──")
    for e in [{"事": "ぜんぶ消す"}, {"事": "書類をひらく"}]:
        od = m.kita(dict(e, 曜="月"))
        print(f"    「{e['事']}」 おどろき {od:.2f}"
              f"  → {'声をかける' if m.hen(od) else '黙っている'}")


if __name__ == "__main__":
    tameshi()
