#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tsukuru3.py -- **6段**の物差し。

★ なぜ作るか
  4段・5段（tsukuru2.py）でも、深さ2の 30B-A3B が 96.7%。**まだ天井が近い。**
  天井の近くでは、量子化を変えても枝刈りしても **差が測れない**。
  「どのビット数から推論が壊れるか」を測るには、
  **正解率が 50〜80% に落ちる物差し**が要る。

★ 6段で足した軸（4段・5段の4軸に追加）
  (5) **前の結果をもう一度使う**（合計を出してから、その合計に対して割合をかける、を2回）
  (6) **単位や表現をまたぐ回数を増やす**（分↔時、％↔比、個↔箱）

★ 変えていない原則
  ・答えは **Python が確定させる**。AIには一切書かせない。
  ・答えは1つに決まる整数。曖昧なら物差しではない。
  ・**別経路の検算器**（kenzan3.py）で作った端から検査する。
"""
import argparse, json, random, os
from collections import Counter

NA = ["さとし", "ゆかり", "たけし", "みさき", "けんじ", "あやこ",
      "りょう", "なおみ", "しんじ", "ともこ", "はるか", "だいち"]
MONO = [("えんぴつ", "本"), ("ノート", "冊"), ("りんご", "個"), ("かん詰め", "缶"),
        ("シール", "枚"), ("ボール", "個"), ("パン", "個"), ("消しゴム", "個")]
MISE = ["みどり倉庫", "やまぶき商会", "こまち市場", "あおば工場", "ひばり屋"]
EKI = ["みどり駅", "やまぶき駅", "こまち駅", "あおば駅", "ひばり駅", "つばめ駅"]
JAMA = [
    "その日の気温は{a}度でした。",
    "倉庫の天井の高さは{a}メートルです。",
    "受付には{a}人が並んでいました。",
    "駐車場には車が{a}台とまっていました。",
    "看板には{a}という数字が書かれていました。",
]


def jama(r):
    return r.choice(JAMA).format(a=r.randint(3, 39))


def waru(r, n, kouho=(10, 20, 25, 40, 50, 60, 75, 80)):
    """n を割り切る割合(%)だけ返す。割り切れない割合は 答えを小数にしてしまう。"""
    ok = [p for p in kouho if (n * p) % 100 == 0]
    return r.choice(ok) if ok else None


# ══════════════════════════════════════════════════════════
#  6段(1) 在庫 ── 入荷 → 出荷% → 返品 → 単価 → 手数料%
# ══════════════════════════════════════════════════════════
def y_zaiko6(r):
    for _ in range(200):
        s0 = r.randrange(40, 200, 2)
        hako, ko = r.randint(3, 9), r.randrange(10, 40, 2)
        s1 = s0 + hako * ko
        p = waru(r, s1)
        if p is None:
            continue
        s2 = s1 - s1 * p // 100
        henpin = r.randint(2, 12)
        s3 = s2 + henpin
        tanka = r.randrange(60, 400, 10)
        uriage = s3 * tanka
        q = waru(r, uriage, (10, 20, 25, 40, 50))
        if q is None:
            continue
        kotae = uriage - uriage * q // 100
        mono, tan = r.choice(MONO)
        toi = ("{mise} には {mono} が {s0}{tan} あります。そこへ {hako}箱ぶん"
               "（1箱 {ko}{tan}）が とどきました。{j}"
               "そのあと ぜんぶの {p}% を 出荷しました。"
               "出荷した中から {henpin}{tan} が こわれていて もどってきました。"
               "いま倉庫にある ぶんを 1{tan} {tanka}円で ぜんぶ売り、"
               "売れた金額の {q}% を 手数料として はらいます。"
               "手もとに のこるのは いくらですか。").format(
            mise=r.choice(MISE), mono=mono, tan=tan, s0=s0, hako=hako, ko=ko,
            j=jama(r), p=p, henpin=henpin, tanka=tanka, q=q)
        return "ざいこ6段", 6, toi, str(kotae), "数"
    return None


# ══════════════════════════════════════════════════════════
#  6段(2) ダイヤ ── 速さ→分 ×2 + 待ち + 徒歩 → 到着時刻
# ══════════════════════════════════════════════════════════
def y_daiya6(r):
    for _ in range(200):
        v1, v2 = r.choice([30, 40, 45, 60]), r.choice([30, 36, 45, 60])
        d1 = v1 * r.randint(1, 5) // 4
        d2 = v2 * r.randint(1, 5) // 4
        if d1 * 60 % v1 or d2 * 60 % v2:
            continue
        t1, t2 = d1 * 60 // v1, d2 * 60 // v2
        if t1 < 10 or t2 < 10:
            continue
        machi, aruki = r.randrange(5, 40, 5), r.randint(4, 25)
        h, m = r.randint(6, 20), r.randrange(0, 60, 5)
        goukei = t1 + machi + t2 + aruki
        fun = h * 60 + m + goukei
        hh, mm = (fun // 60) % 24, fun % 60
        kotae = hh * 100 + mm
        a, b, c = r.sample(EKI, 3)
        toi = ("{a} を {h}時{m}分に 出る電車に のります。{a} から {b} までは "
               "{d1}km を 時速{v1}km で 走ります。{j}"
               "{b} で {machi}分 待って のりかえ、{b} から {c} までは "
               "{d2}km を 時速{v2}km で 走ります。"
               "{c} に ついてから 目的地まで {aruki}分 歩きます。"
               "目的地に つくのは 何時何分ですか。"
               "答えは 時と分を つないだ数で 書いてください"
               "（9時5分なら 905、14時30分なら 1430）。").format(
            a=a, b=b, c=c, h=h, m=("%02d" % m), d1=d1, v1=v1, d2=d2, v2=v2,
            machi=machi, aruki=aruki, j=jama(r))
        return "ダイヤ6段", 6, toi, str(kotae), "数"
    return None


# ══════════════════════════════════════════════════════════
#  6段(3) 数列 ── 差が毎回ふえる → n項目 → 引く → あまり
# ══════════════════════════════════════════════════════════
def y_suretsu6(r):
    for _ in range(200):
        s = r.randint(3, 20)
        d0 = r.randint(2, 9)
        e = r.randint(1, 6)
        n = r.randint(7, 11)
        a, d = s, d0
        retsu = [a]
        for _i in range(n - 1):
            a += d
            d += e
            retsu.append(a)
        hiku = r.randint(5, 40)
        mod = r.choice([7, 9, 11, 12, 13])
        if a - hiku <= 0:
            continue
        kotae = (a - hiku) % mod
        if kotae == 0:
            continue
        toi = ("ある数の ならびは {r0}, {r1}, {r2}, {r3}, ... と つづきます。{j}"
               "となりとの 差は 毎回 {e} ずつ 大きくなります。"
               "この ならびの {n}番目の数から {hiku} を 引いて、"
               "{mod} で 割ったときの あまりは いくつですか。").format(
            r0=retsu[0], r1=retsu[1], r2=retsu[2], r3=retsu[3],
            e=e, n=n, hiku=hiku, mod=mod, j=jama(r))
        return "すうれつ6段", 6, toi, str(kotae), "数"
    return None


# ══════════════════════════════════════════════════════════
#  6段(4) 分配 ── 比で分ける → わたす → % でわたす → 差
# ══════════════════════════════════════════════════════════
def y_bunpai6(r):
    for _ in range(200):
        x, y, z = r.sample([2, 3, 4, 5, 6, 7], 3)
        g = r.randrange(8, 40, 2)
        t = (x + y + z) * g
        A, B, C = x * g, y * g, z * g
        watasu = r.randint(3, min(20, max(3, A - 1)))
        A -= watasu
        B += watasu
        p = waru(r, C, (10, 20, 25, 50))
        if p is None:
            continue
        ido = C * p // 100
        C -= ido
        A += ido
        kotae = max(A, B, C) - min(A, B, C)
        if kotae == 0:
            continue
        na = r.sample(NA, 3)
        mono, tan = r.choice(MONO)
        toi = ("{mono} が ぜんぶで {t}{tan} あります。{j}"
               "これを {n0}さん、{n1}さん、{n2}さん で {x}:{y}:{z} の 割合に なるように"
               " 分けました。そのあと {n0}さんが {n1}さんに {w}{tan} わたし、"
               "{n2}さんは 自分の ぶんの {p}% を {n0}さんに わたしました。"
               "いちばん多い人と いちばん少ない人の 差は いくつですか。").format(
            mono=mono, tan=tan, t=t, n0=na[0], n1=na[1], n2=na[2],
            x=x, y=y, z=z, w=watasu, p=p, j=jama(r))
        return "ぶんぱい6段", 6, toi, str(kotae), "数"
    return None


TSUKURIKATA = [y_zaiko6, y_daiya6, y_suretsu6, y_bunpai6]


def tsukuru(kazu=120, tane=20260910):
    r = random.Random(tane)
    deta, mita = [], set()
    n = muda = 0
    while n < kazu and muda < kazu * 200:
        res = TSUKURIKATA[n % len(TSUKURIKATA)](r)
        if res is None:
            muda += 1
            continue
        kata, d, toi, ans, kt = res
        if toi in mita:
            muda += 1
            continue
        mita.add(toi)
        n += 1
        deta.append({"id": "e6-%03d" % n, "型": kata, "段": d,
                     "問": toi, "答": ans, "答の形": kt})
    return deta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--kazu", type=int, default=120)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "mondai_6dan.jsonl"))
    ap.add_argument("--tane", type=int, default=20260910)
    a = ap.parse_args()
    d = tsukuru(a.kazu, a.tane)
    with open(a.out, "w", encoding="utf-8") as f:
        for x in d:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("%d件 → %s" % (len(d), a.out))
    print("型:", dict(Counter(x["型"] for x in d)))
