#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tsukuru4.py -- 深さ2でも天井に当たりにくい、引き返し型の物差し。

6段版のように数字や手順をただ長くするのではなく、次の4軸を混ぜる。

  わな       : 値引きと消費税の順序を取り違えやすい
  場合分け   : 3種類の切手の組合せを漏れなく数える
  後戻り     : 最後の差から、移動を逆向きにたどる
  同文脈の数 : 同じ単位・仕事の数字を、計算に使う数と混ぜる

答えは生成器で確定するが、kenzan4.py は問題文を読み直して別経路で検算する。
問題データには生成時の中間値を保存しない。
"""
import argparse
import json
import os
import random
from collections import Counter


HERE = os.path.dirname(os.path.abspath(__file__))

PLACES = ["あおば商店", "こまち市場", "ひばり屋", "やまぶき堂", "みどり売店"]
ITEMS = [
    ("パン", "個"),
    ("ノート", "冊"),
    ("りんご", "個"),
    ("カード", "枚"),
    ("ボール", "個"),
]


def _stamp_count(a, b, c, target):
    """生成側の切手の方法数。検算側は3重ループで計算する。"""
    n = 0
    for na in range(target // a + 1):
        for nb in range((target - na * a) // b + 1):
            rest = target - na * a - nb * b
            if rest >= 0 and rest % c == 0:
                n += 1
    return n


def _make_trap(r):
    """先に値引き、後で税。税を先に掛ける誤答が生じるが、文面は一意。"""
    base = r.choice(range(1000, 9001, 100))
    discount = r.choice([10, 20, 25, 30, 40])
    tax = r.choice([8, 10])
    receipt = r.randint(100, 999)
    points = r.choice([12, 18, 24, 36, 48, 60, 72, 90])
    # 段階ごとに分数で計算し、整数になる値だけ採用する。
    after_discount = base * (100 - discount) // 100
    total = after_discount * (100 + tax) // 100
    if base * (100 - discount) % 100 or after_discount * (100 + tax) % 100:
        return None
    form = r.randrange(3)
    if form == 0:
        q = (f"{r.choice(PLACES)}で、ある商品の税抜き価格は{base}円です。"
             f"レシート番号は{receipt}で、会計前のポイント残高は{points}点でした。"
             f"会計では、税抜き価格から先に{discount}%値引きし、"
             f"その値引き後の価格に{tax}%の消費税を加えます。"
             "支払う金額は何円ですか。")
    elif form == 1:
        q = (f"{r.choice(PLACES)}の商品は本体価格が{base}円です。"
             f"同じレシートに、売り場番号{receipt}と付与予定ポイント{points}点も印字されます。"
             f"本体価格を{discount}%引きにしてから、割引後の金額だけに{tax}%の税を加えます。"
             "最終的な税込み金額は何円ですか。")
    else:
        q = (f"値札に税抜き{base}円とある商品を買います。商品コードは{receipt}、"
             f"この会計で使えるポイントは{points}点です。ポイントは使わず、"
             f"まず{discount}%を値引きし、残った金額に{tax}%の消費税を加えると、"
             "支払額はいくらになりますか。")
    return "わな_順序", q, str(total)


def _make_cases(r):
    """切手3種類の非負整数解を数える。順番は数えない。"""
    vals = sorted(r.sample([3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 15], 3))
    a, b, c = vals
    counts = [r.randint(1, 12), r.randint(1, 12), r.randint(1, 12)]
    target = a * counts[0] + b * counts[1] + c * counts[2]
    methods = _stamp_count(a, b, c, target)
    if not 2 <= methods <= 45:
        return None
    other_fee = r.randint(2, 9) * 10
    window = r.randint(1, 12)
    forms = [
        (f"郵便局で、{a}円、{b}円、{c}円の3種類の切手を使います。"
         f"同じ時間帯に別の郵便物から{other_fee}円の料金があり、受付は{window}番窓口でした。"
         f"この郵便物には3種類の切手をそれぞれ0枚以上使い、合計{target}円にします。"
         "同じ種類の切手の順番は区別しません。合計を作る方法は何通りありますか。"),
        (f"{r.choice(PLACES)}郵便窓口で、額面{a}円、{b}円、{c}円の切手を選びます。"
         f"別の客の郵便料金は{other_fee}円、窓口番号は{window}番でした。"
         f"3種類は何枚使わなくてもよいものとし、合計を{target}円にする組合せを数えます。"
         "切手を並べる順番の違いは同じ方法として、何通りありますか。"),
        (f"{a}円切手、{b}円切手、{c}円切手を郵便物1通に使います。"
         f"受付票には別件の料金{other_fee}円と窓口{window}番もあります。"
         f"各種類の枚数は0枚以上、合計は{target}円とするとき、"
         "枚数の組合せは何通りありますか。順番だけが違うものは1通りとします。"),
    ]
    return "場合分け_切手", r.choice(forms), str(methods)


def _make_backtrack(r):
    """最後の差から最後の2箱を復元し、移動を逆に戻る問題。"""
    total = r.randrange(60, 221, 2)
    diff = r.randrange(4, min(36, total - 4), 2)
    final_red = (total + diff) // 2
    final_white = total - final_red
    moved = r.randint(5, 24)
    returned = r.randint(2, moved - 1)
    initial_red = final_red + moved - returned
    initial_white = total - initial_red
    if initial_white <= 0 or final_white <= 0:
        return None
    item, unit = r.choice(ITEMS)
    code = r.randint(100, 999)
    shelf = r.randint(40, 180)
    forms = [
        (f"倉庫の赤箱と白箱に入っている{item}の合計は、作業中ずっと{total}{unit}です。"
         f"最初の状態から、赤箱から白箱へ{moved}{unit}移し、その後、白箱から赤箱へ"
         f"{returned}{unit}戻しました。最後には赤箱が白箱より{diff}{unit}多くなりました。"
         f"管理票番号は{code}、棚の幅は{shelf}cmです。最初に赤箱にあった{item}は何{unit}ですか。"),
        (f"赤い箱と白い箱の{item}は合わせて{total}{unit}あります。"
         f"作業ではまず赤箱の{moved}{unit}を白箱へ移し、続いて白箱から"
         f"{returned}{unit}を赤箱へ返しました。作業後は赤箱が白箱より{diff}{unit}多く、"
         f"記録番号は{code}、箱を置いた棚の高さは{shelf}cmでした。"
         f"作業前の赤箱の{item}は何{unit}でしたか。"),
        (f"{item}を赤箱と白箱に分けています。2箱の合計は{total}{unit}で変わりません。"
         f"赤箱から白箱へ{moved}{unit}運んだあと、白箱から赤箱へ{returned}{unit}運び戻しました。"
         f"最後の赤箱は白箱より{diff}{unit}多くなりました。伝票{code}番と棚番号{shelf}は"
         f"別の管理情報です。最初の赤箱には何{unit}ありましたか。"),
    ]
    return "後戻り_箱", r.choice(forms), str(initial_red)


def _make_context(r):
    """販売用の在庫と、同じ仕事・同じ単位の無関係な数を混ぜる。"""
    place = r.choice(PLACES)
    item, unit = r.choice(ITEMS)
    initial = r.randint(40, 180)
    boxes = r.randint(2, 9)
    each = r.randint(6, 28)
    received = boxes * each
    sold = r.randint(10, initial + received - 1)
    display = r.randint(3, 24)
    capacity = r.randint(received, received + 30)
    answer = initial + received - sold
    forms = [
        (f"{place}の販売棚には、販売用の{item}が{initial}{unit}あります。"
         f"{boxes}箱が届き、1箱には{each}{unit}入っています。午後に販売用から"
         f"{sold}{unit}売れました。同じ日の記録には、別の展示用として{display}{unit}を"
         f"取り分けたことと、配送車の最大積載数が{capacity}{unit}だったこともあります。"
         f"販売用として残っている{item}は何{unit}ですか。"),
        (f"{place}では、売るための{item}を最初に{initial}{unit}用意しました。"
         f"納品された{boxes}箱は1箱あたり{each}{unit}です。そこからお客さんに"
         f"{sold}{unit}売りました。帳簿には、別の棚の試食・展示用{item}が{display}{unit}、"
         f"運搬箱の表示上の上限が{capacity}{unit}とも書かれています。"
         f"売るための{item}の残りは何{unit}ですか。"),
        (f"{place}の倉庫に販売予定の{item}が{initial}{unit}あり、今日{boxes}箱を入荷しました。"
         f"1箱は{each}{unit}入りで、入荷後に{sold}{unit}を販売しました。"
         f"同じ納品書には、撮影用に別置きした{display}{unit}と、車両の積載上限{capacity}{unit}も"
         f"記録されています。販売予定分だけで、残りは何{unit}ですか。"),
    ]
    return "同文脈_在庫", r.choice(forms), str(answer)


MAKERS = (_make_trap, _make_cases, _make_backtrack, _make_context)


def tsukuru(kazu=128, tane=20260911):
    r = random.Random(tane)
    data = []
    seen = set()
    attempts = 0
    while len(data) < kazu and attempts < kazu * 500:
        maker = MAKERS[len(data) % len(MAKERS)]
        attempts += 1
        result = maker(r)
        if result is None:
            continue
        kind, question, answer = result
        if question in seen:
            continue
        seen.add(question)
        data.append({
            "id": "e7-%03d" % (len(data) + 1),
            "型": kind,
            "段": 7,
            "問": question,
            "答": answer,
            "答の形": "数",
        })
    if len(data) != kazu:
        raise RuntimeError("%d問しか作れませんでした（要求%d問）" % (len(data), kazu))
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kazu", type=int, default=128)
    ap.add_argument("--out", default=os.path.join(HERE, "mondai_7dan.jsonl"))
    ap.add_argument("--tane", type=int, default=20260911)
    a = ap.parse_args()
    data = tsukuru(a.kazu, a.tane)
    with open(a.out, "w", encoding="utf-8") as f:
        for row in data:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("%d問 → %s" % (len(data), a.out))
    print("型:", dict(Counter(row["型"] for row in data)))


if __name__ == "__main__":
    main()
