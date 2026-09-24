#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ruisui.py -- 類推。「AにとってのBは、CにとってのX」

  いまのカーネルには これが無い。
  だから、覚えた形から一歩も外に出られない。

  やり方（掛け算なし。XOR だけ）:
      アメリカ=ドル、日本=円 … を ひとつの束にする
          組 = たばねる( むすぶ(アメリカ,ドル), むすぶ(日本,円), … )
      引くとき
          むすぶ(組, アメリカ) ≒ ドル      ← XOR は 2回かけると元に戻る

  束にすると他のペアが「雑音」として混ざるが、
  1万ビットあれば、いちばん近いものを選べば正しく出る。

  カーネルでの使いどころ:
      「Desktop の 画像 を 数える」を知っている
          → 「Downloads の 音楽 は？」が、教わらずに出る
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hdv


class Kumi:
    """ものとものの組。ひと束に押し込んで、あとから引く"""

    def __init__(self, name="組"):
        self.name = name
        self.pairs = []
        self._v = None
        self.goi = {}        # 名前 -> ベクトル（引いた後、名前に戻すための表）

    def oboeru(self, a, b):
        self.pairs.append((a, b))
        for w in (a, b):
            self.goi.setdefault(w, hdv.atom(w))
        self._v = None
        return self

    @property
    def v(self):
        if self._v is None:
            self._v = hdv.bundle_bits(
                [hdv.bind(hdv.atom(a), hdv.atom(b)) for a, b in self.pairs])
        return self._v

    def _chikai(self, q, nozoku=(), k=1):
        """いちばん近い『知っている名前』に寄せる（掃除）"""
        s = sorted(((hdv.near(q, v), w) for w, v in self.goi.items()
                    if w not in nozoku), key=lambda x: -x[0])
        return s[:k]

    def hiku(self, a, k=1):
        """a の相手は？"""
        return self._chikai(hdv.bind(self.v, hdv.atom(a)), nozoku=(a,), k=k)

    def ruisui(self, a, b, c, k=1):
        """a にとっての b は、c にとって何？

        b と a の「ずれ」を取り出し、それを c に足す。
            ずれ = むすぶ(a, b)
            答え = むすぶ(ずれ, c)
        """
        # ずれの取り方が肝心。
        #   (a,b) をこの組で覚えているなら、組そのものが「ずれ」。
        #   束になっているぶん、他の組の力も借りられる。
        #   覚えていないときだけ、その場の a と b から作る
        #   （このときは当てにならない。近さが 0.5 前後なら当てずっぽう）
        zure = self.v if (a, b) in self.pairs else hdv.bind(hdv.atom(a), hdv.atom(b))
        for w in (a, b, c):
            self.goi.setdefault(w, hdv.atom(w))
        return self._chikai(hdv.bind(zure, hdv.atom(c)), nozoku=(a, b, c), k=k)

    def shiru(self, *words):
        """答えの候補として、この語も知っておく"""
        for w in words:
            self.goi.setdefault(w, hdv.atom(w))
        return self


class Waku(Kumi):
    """枠つきの組（役割 → 中身）。手順の類推に使う

        しごと = 枠(動作=数える, 場所=Desktop, 種類=画像)
        「場所は？」と聞けば Desktop が返る
    """

    def __init__(self, **slots):
        super().__init__("しごと")
        for k, v in slots.items():
            self.oboeru("枠:" + k, "値:" + str(v))

    def toi(self, waku):
        got = self.hiku("枠:" + waku, k=1)
        if not got:
            return None, 0.0
        near, w = got[0]
        return (w[2:] if w.startswith("値:") else w), near


def tameshi():
    print("■ 類推ができるか（一度も教えていない答えを出せるか）\n")

    k = Kumi("国と通貨")
    for a, b in [("アメリカ", "ドル"), ("日本", "円"), ("イギリス", "ポンド"),
                 ("メキシコ", "ペソ"), ("インド", "ルピー")]:
        k.oboeru(a, b)
    print("  覚えた: アメリカ=ドル 日本=円 イギリス=ポンド メキシコ=ペソ インド=ルピー")
    for q in ["メキシコ", "日本", "イギリス"]:
        n, w = k.hiku(q)[0]
        print(f"    {q} の通貨は？ → {w}  （近さ {n:.3f}）")
    n, w = k.ruisui("アメリカ", "ドル", "メキシコ")[0]
    print(f"    アメリカにとってのドルは、メキシコにとって？ → {w}  （近さ {n:.3f}）")

    print("\n  ── カーネルの仕事で ──")
    s = Waku(動作="数える", 場所="Desktop", 種類="画像")
    for w in ["動作", "場所", "種類"]:
        v, n = s.toi(w)
        print(f"    {w} は？ → {v}  （近さ {n:.3f}）")

    # 教わっていない組み合わせ
    k2 = Kumi("場所と中身")
    for a, b in [("Desktop", "画像"), ("Downloads", "動画"),
                 ("Documents", "書類"), ("Music", "音楽")]:
        k2.oboeru(a, b)
    n, w = k2.ruisui("Desktop", "画像", "Music")[0]
    print(f"\n    Desktop の画像 は、Music にとって？ → {w}  （近さ {n:.3f}）")


if __name__ == "__main__":
    tameshi()
