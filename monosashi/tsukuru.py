#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tsukuru.py -- 思考力の物差し（問題集）を作る。

★ この道具の一番大事な決まり:
    **答えは Python が出す。AI には一切書かせない。**
  前回の教材づくりで効いた「ラベルが構造から確定するものだけを入れる」を
  そのまま持ってきている。AI に事実を書かせた瞬間に嘘が混ざる。

★ 段数（何回考えを積むか）をラベルとして持たせる。
  1段しか出来ない／3段で崩れる、が分かると
  「量子化の壁」なのか「学習不足」なのかを切り分けられる（引き継ぎ書2 3章)。

出しかた:
    python3 tsukuru.py --kazu 120 --out mondai.jsonl
1件の形:
    {"id":"k2-007","型":"かいもの","段":2,"問":"…","答":"430","答の形":"数"}
"""
import argparse, json, random, datetime, itertools, os, sys

# ── 材料。**問題文に出てくる言葉を散らすため**だけのもの ──────────
NA = ["さとし", "ゆかり", "たけし", "みさき", "けんじ", "あやこ",
      "りょう", "なおみ", "しんじ", "ともこ"]
MONO = [("えんぴつ", "本"), ("ノート", "冊"), ("りんご", "個"), ("かん詰め", "缶"),
        ("シール", "枚"), ("ボール", "個"), ("パン", "個"), ("箱", "箱"),
        ("カード", "枚"), ("びん", "本")]
MISE = ["みどり商店", "やまぶき堂", "こまち市場", "あおば売店", "ひばり屋"]
YOUBI = ["月", "火", "水", "木", "金", "土", "日"]


def _n(x):
    """答えは必ず文字列。数はカンマなしの半角で持つ。"""
    if isinstance(x, float):
        return ("%g" % x)
    return str(x)


# ══════════════════════════════════════════════════════════════
#  1段 ── 1回考えれば出る
# ══════════════════════════════════════════════════════════════
def m_keisan1(r):
    a, b = r.randint(12, 99), r.randint(3, 19)
    shu = r.choice(["たす", "ひく", "かける"])
    if shu == "たす":
        toi, ans = "%d に %d をたすと いくつですか。" % (a, b), a + b
    elif shu == "ひく":
        toi, ans = "%d から %d をひくと いくつですか。" % (a, b), a - b
    else:
        toi, ans = "%d に %d をかけると いくつですか。" % (a, b), a * b
    return "たんじゅん計算", 1, toi, _n(ans), "数"


def m_tani1(r):
    kind = r.choice(["km", "分", "kg", "L", "時間"])
    if kind == "km":
        v = r.randint(2, 40)
        return "たんい", 1, "%d キロメートルは 何メートルですか。" % v, _n(v * 1000), "数"
    if kind == "分":
        v = r.randint(3, 55)
        return "たんい", 1, "%d 分は 何秒ですか。" % v, _n(v * 60), "数"
    if kind == "kg":
        v = r.randint(2, 30)
        return "たんい", 1, "%d キログラムは 何グラムですか。" % v, _n(v * 1000), "数"
    if kind == "L":
        v = r.randint(2, 30)
        return "たんい", 1, "%d リットルは 何ミリリットルですか。" % v, _n(v * 1000), "数"
    v = r.randint(2, 12)
    return "たんい", 1, "%d 時間は 何分ですか。" % v, _n(v * 60), "数"


def m_kurabe1(r):
    xs = r.sample(range(11, 990), 4)
    ookii = r.random() < 0.5
    toi = ("つぎの数のうち いちばん%sものは どれですか。 %s"
           % ("大きい" if ookii else "小さい", "、".join(str(x) for x in xs)))
    return "くらべる", 1, toi, _n(max(xs) if ookii else min(xs)), "数"


# ══════════════════════════════════════════════════════════════
#  2段 ── 一度出した数を、もう一度つかう
# ══════════════════════════════════════════════════════════════
def m_kaimono2(r):
    mono, tan = r.choice(MONO)
    nedan, kazu = r.randint(30, 240), r.randint(3, 12)
    harai = ((nedan * kazu) // 100 + r.randint(1, 9)) * 100
    toi = ("%s を 1%s %d円で %d%s 買い、%d円 出しました。おつりは いくらですか。"
           % (mono, tan, nedan, kazu, tan, harai))
    return "かいもの", 2, toi, _n(harai - nedan * kazu), "数"


def m_wariai2(r):
    moto = r.randint(4, 40) * 100
    biki = r.choice([10, 20, 25, 30, 40, 50])
    toi = ("定価 %d円の品が %d%%引きです。代金は いくらですか。" % (moto, biki))
    return "わりあい", 2, toi, _n(moto * (100 - biki) // 100), "数"


def m_hiduke2(r):
    y = 2026
    m = r.randint(1, 12)
    d = r.randint(1, 25)
    nochi = r.randint(8, 60)
    d0 = datetime.date(y, m, d)
    d1 = d0 + datetime.timedelta(days=nochi)
    if r.random() < 0.5:
        toi = ("%d年%d月%d日の %d日後は 何月何日ですか。「○月○日」の形で答えてください。"
               % (y, m, d, nochi))
        return "こよみ", 2, toi, "%d月%d日" % (d1.month, d1.day), "語"
    yb = YOUBI[d0.weekday()]
    toi = ("%d年%d月%d日は %s曜日です。その %d日後は 何曜日ですか。"
           "曜日の漢字1文字だけで答えてください。" % (y, m, d, yb, nochi))
    return "こよみ", 2, toi, YOUBI[d1.weekday()], "語"


def m_kazoe2(r):
    xs = r.sample(range(10, 100), 12)
    shu = r.choice(["ぐうすう", "3のばい", "50より大きい"])
    if shu == "ぐうすう":
        joken, ans = "偶数", sum(1 for x in xs if x % 2 == 0)
    elif shu == "3のばい":
        joken, ans = "3の倍数", sum(1 for x in xs if x % 3 == 0)
    else:
        joken, ans = "50より大きい数", sum(1 for x in xs if x > 50)
    toi = ("つぎの12個の数のうち %s は いくつありますか。 %s"
           % (joken, "、".join(str(x) for x in xs)))
    return "かぞえる", 2, toi, _n(ans), "数"


def m_heikin2(r):
    xs = [r.randint(2, 20) * 5 for _ in range(r.choice([4, 5]))]
    while sum(xs) % len(xs):
        xs[0] += 5
    toi = ("%s の 平均は いくつですか。" % "、".join(str(x) for x in xs))
    return "へいきん", 2, toi, _n(sum(xs) // len(xs)), "数"


# ══════════════════════════════════════════════════════════════
#  3段以上 ── 途中の数を2回以上つなぐ。ここで崩れ方が見える
# ══════════════════════════════════════════════════════════════
def m_keisan3(r):
    mono, tan = r.choice(MONO)
    a = r.randint(4, 12)
    b = r.randint(3, 9)
    hako = r.randint(6, 15)
    toi = ("%s が %d 箱あり、1箱に %d%s 入っています。"
           "そこから %d%s を配りました。のこりは 何%sですか。"
           % (mono, a, hako, tan, b * hako // 2, tan, tan))
    return "みつだん計算", 3, toi, _n(a * hako - b * hako // 2), "数"


def m_hayasa3(r):
    hayasa = r.choice([40, 45, 50, 60, 75, 80])
    fun = r.choice([30, 45, 60, 90, 120])
    yasumi = r.choice([10, 15, 20])
    kyori = hayasa * fun // 60
    toi = ("時速 %d キロメートルの車で %d分 走り、%d分 休みました。"
           "走った道のりは 何キロメートルですか。（休みの間は 走っていません）"
           % (hayasa, fun, yasumi))
    return "はやさ", 3, toi, _n(kyori), "数"


def m_ronri3(r):
    hito = r.sample(NA, 3)
    mono = [m[0] for m in r.sample(MONO, 3)]
    wari = list(mono)
    r.shuffle(wari)
    tsuki = dict(zip(hito, wari))
    # 3つの手がかりで一意に決まるようにする
    a, b, c = hito
    tegakari = [
        "%s は %s を持っていません。" % (a, tsuki[b]),
        "%s は %s を持っていません。" % (a, tsuki[c]),
        "%s は %s を持っています。" % (b, tsuki[b]),
    ]
    r.shuffle(tegakari)
    kiku = r.choice(hito)
    toi = ("%s の3人が %s を 1つずつ 持っています。\n%s\n"
           "%s が 持っているのは どれですか。品物の名前だけで答えてください。"
           % ("、".join(hito), "、".join(mono), "".join(tegakari), kiku))
    return "ろんり", 3, toi, tsuki[kiku], "語"


def m_suretsu3(r):
    hajime = r.randint(2, 9)
    sa = r.randint(3, 9)
    n = r.randint(8, 20)
    mieru = [hajime + sa * i for i in range(5)]
    toi = ("%s、… と ならんでいます。同じ決まりで つづけたとき、"
           "%d番目の数は いくつですか。" % ("、".join(str(x) for x in mieru), n))
    return "すうれつ", 3, toi, _n(hajime + sa * (n - 1)), "数"


def m_kaimono3(r):
    """合計 → 割引 → 支払い の3段。

    ★ ここで一度こけた: 「割り切れるまで値段を1円ずつ足す」書き方は
      **永久に止まらない**ことがある（足すたびに合計が偶数ずつ動くと、
      偶奇が一生変わらない）。**探して待つ形の作りかたをしない。**
      引く割合を 100の約数に限って、はじめから割り切れる合計を選ぶ。
    """
    mono1, t1 = r.choice(MONO)
    mono2, t2 = r.choice([m for m in MONO if m[0] != mono1])
    n1, n2 = r.randint(2, 8), r.randint(2, 8)
    biki = r.choice([10, 20, 25, 50])          # 100 の約数ぶんだけ引く
    # 合計は 100 の倍数にしておく。これなら どの割合でも必ず割り切れる。
    goukei = r.randint(6, 40) * 100
    # その合計になるように 値段を割り当てる（余りは1つ目に寄せる）
    p2 = r.randint(50, 300)
    nokori = goukei - n2 * p2
    while nokori < n1 * 30:                    # 1つ目が安すぎたら 2つ目を下げる
        p2 -= 10
        nokori = goukei - n2 * p2
    p1 = nokori // n1
    goukei = n1 * p1 + n2 * p2                 # 割り当ての端数ぶんを引き直す
    if goukei % (100 // __import__("math").gcd(100, 100 - biki)):
        goukei = n1 * p1 + n2 * p2             # 端数が出たら 割引を 50%（必ず割れる）に
        biki = 50 if goukei % 2 == 0 else 0
    harau = goukei * (100 - biki) // 100
    if biki == 0:
        toi = ("%s で %s を 1%s %d円で %d%s、%s を 1%s %d円で %d%s 買いました。"
               "はらう金額は いくらですか。"
               % (r.choice(MISE), mono1, t1, p1, n1, t1, mono2, t2, p2, n2, t2))
    else:
        toi = ("%s で %s を 1%s %d円で %d%s、%s を 1%s %d円で %d%s 買いました。"
               "合計から %d%% 引いてもらえます。はらう金額は いくらですか。"
               % (r.choice(MISE), mono1, t1, p1, n1, t1, mono2, t2, p2, n2, t2, biki))
    return "みつだんかいもの", 3, toi, _n(harau), "数"


TSUKURIKATA = {
    1: [m_keisan1, m_tani1, m_kurabe1],
    2: [m_kaimono2, m_wariai2, m_hiduke2, m_kazoe2, m_heikin2],
    3: [m_keisan3, m_hayasa3, m_ronri3, m_suretsu3, m_kaimono3],
}


def tsukuru(kazu=120, tane=20260907):
    r = random.Random(tane)
    dan_goto = kazu // 3
    deta, mita = [], set()
    for dan in (1, 2, 3):
        tsukuri = TSUKURIKATA[dan]
        n = 0
        muda = 0
        while n < dan_goto and muda < dan_goto * 60:
            f = tsukuri[n % len(tsukuri)]
            kata, d, toi, ans, katachi = f(r)
            if toi in mita:              # 同じ問題文は入れない
                muda += 1
                continue
            mita.add(toi)
            n += 1
            deta.append({"id": "d%d-%03d" % (dan, n), "型": kata, "段": d,
                         "問": toi, "答": ans, "答の形": katachi})
    return deta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--kazu", type=int, default=120)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "mondai.jsonl"))
    a = ap.parse_args()
    d = tsukuru(a.kazu)
    with open(a.out, "w", encoding="utf-8") as f:
        for x in d:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    from collections import Counter
    print("%d件 → %s" % (len(d), a.out))
    print("段:", dict(Counter(x["段"] for x in d)))
    print("型:", dict(Counter(x["型"] for x in d)))
