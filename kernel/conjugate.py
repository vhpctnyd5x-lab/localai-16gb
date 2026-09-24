#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
conjugate.py -- 動詞の活用を、規則で作る

  「移す」から「移して」「移した」「移しといて」…を、
  ひとつずつ書き並べるのではなく、国語で習う活用表から自動で作る。

  なぜ規則にしたか
  ────────────────
  はじめは外のAIに「述語を225個ならべて」と頼んだ。
  返ってきたのは52個で、しかも「寄せられるように」のような
  命令にならない形が混ざっていた。

  日本語の活用は規則で決まっている。
  規則で作れば、抜けもなく、間違いもなく、ただでいくらでも作れる。

  五段・一段・サ変の3つだけ扱う。頼みごとに使う動詞は、ほぼこれで足りる。

  五段活用の音の変化（学校で習う「行段」の表）:
      書く → 書か 書き 書く 書け 書こ    ／ て形は 書いて
      移す → 移さ 移し 移す 移せ 移そ    ／ て形は 移して
      運ぶ → 運ば 運び 運ぶ 運べ 運ぼ    ／ て形は 運んで
"""

# 五段活用。語尾の1文字 → (連用形の音, て形, た形)
GODAN = {
    "う": ("い", "って", "った"),
    "つ": ("ち", "って", "った"),
    "る": ("り", "って", "った"),
    "む": ("み", "んで", "んだ"),
    "ぶ": ("び", "んで", "んだ"),
    "ぬ": ("に", "んで", "んだ"),
    "く": ("き", "いて", "いた"),
    "ぐ": ("ぎ", "いで", "いだ"),
    "す": ("し", "して", "した"),
}
# 五段の未然形（〜ない／〜せる の前）
GODAN_A = {"う": "わ", "つ": "た", "る": "ら", "む": "ま", "ぶ": "ば",
           "ぬ": "な", "く": "か", "ぐ": "が", "す": "さ"}
# 五段の命令形
GODAN_E = {"う": "え", "つ": "て", "る": "れ", "む": "め", "ぶ": "べ",
           "ぬ": "ね", "く": "け", "ぐ": "げ", "す": "せ"}

# 「て」の後に付く、頼みごとの言い方
TE_TAILS = [
    "", "ください", "くれ", "くれる", "ほしい", "ほしいな", "もらえる",
    "もらえます", "おいて", "おいてね", "ね", "よ", "な",
]
# 連用形の後に付く言い方
RENYOU_TAILS = ["たい", "ます", "ましょう", "なさい"]


def _split(verb):
    """動詞を (語幹, 種類) に分ける。

    種類は "五段" / "一段" / "サ変" / None
    """
    if verb.endswith("する"):
        return verb[:-2], "サ変"
    if len(verb) >= 2 and verb[-1] == "る":
        # 「見る・食べる」のような一段は、直前が「い段・え段」
        prev = verb[-2]
        if _is_i_or_e(prev):
            return verb[:-1], "一段"
        return verb[:-1], "五段"
    if verb and verb[-1] in GODAN:
        return verb[:-1], "五段"
    return verb, None


_I_ROW = set("いきしちにひみりぎじびぴ")
_E_ROW = set("えけせてねへめれげぜべぺ")


def _is_i_or_e(ch):
    return ch in _I_ROW or ch in _E_ROW


def forms(verb):
    """ひとつの動詞から、頼みごとに使われる言い方を全部作る"""
    stem, kind = _split(verb)
    out = set()

    if kind == "サ変":
        te, ta, ren = stem + "して", stem + "した", stem + "し"
        base = [verb, stem + "しろ", stem + "せよ", stem + "させて",
                stem + "させといて", stem + "しといて"]
    elif kind == "一段":
        te, ta, ren = stem + "て", stem + "た", stem
        base = [verb, stem + "ろ", stem + "よ", stem + "させて",
                stem + "させといて", stem + "といて"]
    elif kind == "五段":
        last = verb[-1]
        ren = stem + GODAN[last][0]
        te = stem + GODAN[last][1]
        ta = stem + GODAN[last][2]
        base = [verb, stem + GODAN_E[last],
                stem + GODAN_A[last] + "せて",
                stem + GODAN_A[last] + "せといて",
                te[:-1] + "といて" if te.endswith("て") else te]
    else:
        return {verb}

    out.update(b for b in base if b)
    for t in TE_TAILS:
        out.add(te + t)
    for t in RENYOU_TAILS:
        out.add(ren + t)
    # 「〜とく」の縮約（移しておく → 移しとく）
    out.add(te[:-1] + "とく" if te.endswith("て") else te)
    return {w for w in out if 2 <= len(w) <= 12}


# ------------------------------------------------------------------
# 動作ごとの、もとになる動詞
#   ここだけ人が選ぶ。あとの活用は機械が作る
# ------------------------------------------------------------------
BASE_VERBS = {
    "移動": ["移す", "移動する", "動かす", "まとめる", "集める", "寄せる",
             "入れる", "しまう", "片付ける", "整理する", "放り込む",
             "分ける", "仕分ける", "送る", "持っていく"],
    "数える": ["数える", "カウントする", "調べる"],
    "一覧": ["見せる", "並べる", "listする", "出す", "教える", "表示する"],
    "作成": ["作る", "作成する", "用意する", "新規作成する", "こしらえる"],
    "ごみばこ": ["捨てる", "消す", "削除する", "始末する", "処分する",
                 "ゴミ箱に入れる"],
    "改名": ["改名する", "リネームする", "名前を変える", "つけ直す"],
    "重複": ["重複する", "かぶる", "だぶる"],
    "大きさ": ["合計する"],
    "もぐる": ["もぐる", "潜る"],
    "HTML": ["HTML化する", "ページにする"],
}


def build():
    """全部の動作について、述語カードを作る。

    戻り値: {述語: 動作}
    """
    out = {}
    for act, verbs in BASE_VERBS.items():
        for v in verbs:
            for f in forms(v):
                # 先に入った動作を優先する（早い者勝ちで衝突を避ける）
                out.setdefault(f, act)
    return out


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) > 1:
        for v in sys.argv[1:]:
            print(f"\n{v}  →  " + " / ".join(sorted(forms(v))))
    else:
        t = build()
        from collections import Counter
        c = Counter(t.values())
        print(f"できた述語: {len(t)} 個")
        for act, n in c.most_common():
            print(f"  {act:<8} {n:>4} 個")
        print("\n見本（移動）:")
        print("  " + " / ".join(sorted(k for k, v in t.items()
                                       if v == "移動")[:24]))
