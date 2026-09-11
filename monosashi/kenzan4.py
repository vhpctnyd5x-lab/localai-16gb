#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kenzan4.py -- 7段物差しの独立検算器。

生成器が保持していた式や中間値は参照しない。JSONLの「問」だけを正規表現で
読み取り、型ごとに別の道筋で答えを出す。分数は Fraction で扱い、問題文の
数字が割り切れない場合も黙って丸めずに失敗として報告する。
"""
import io
import json
import os
import re
import sys
from fractions import Fraction as F
from collections import Counter


HERE = os.path.dirname(os.path.abspath(__file__))


class Dame(str):
    """問題が成立しない、または独立検算できないことを表す。"""


def _int(pattern, text, label):
    m = re.search(pattern, text)
    if not m:
        raise ValueError("%s が読めない: %s" % (label, pattern))
    return int(m.group(1))


def _integer(value, label):
    if value.denominator != 1:
        return Dame("%s が割り切れない (%s)" % (label, value))
    return int(value)


def _trap(text):
    base = _int(r"(?:税抜き価格は|本体価格が|税抜き)\s*(\d+)円", text, "税抜き価格")
    discount = _int(r"(\d+)%\s*(?:を\s*)?(?:値引き|引き)", text, "値引き率")
    tax = _int(r"(\d+)%\s*(?:の)?(?:消費税|の税)", text, "税率")
    # 生成側の1行の式を再利用せず、値引き額→割引後→税額の順で求める。
    discount_amount = F(base * discount, 100)
    discounted = F(base) - discount_amount
    if discounted.denominator != 1:
        return Dame("値引き後の価格が整数でない")
    tax_amount = discounted * tax / 100
    return _integer(discounted + tax_amount, "税込み金額")


def _cases(text):
    m = re.search(r"(\d+)円(?:切手)?、(\d+)円(?:切手)?、(\d+)円(?:の3種類の切手|の切手|切手)", text)
    if not m:
        raise ValueError("切手の額面が読めない")
    a, b, c = map(int, m.groups())
    target = _int(r"(?:合計(?:を|は)?|合計は)(\d+)円", text, "合計額")
    # 問題文を読み直した独立経路。a,b,c の全範囲を三重に調べ、順番は数えない。
    count = 0
    for na in range(target // a + 1):
        for nb in range(target // b + 1):
            for nc in range(target // c + 1):
                if na * a + nb * b + nc * c == target:
                    count += 1
    return count


def _backtrack(text):
    total = _int(r"(?:合計は、作業中ずっと|合計は|合わせて|2箱の合計は)\s*(\d+)[個冊枚本]", text, "合計")
    moved = _int(r"赤箱(?:から白箱へ|の)\s*(\d+)[個冊枚本]", text, "最初の移動")
    returned = _int(r"白箱から(?:赤箱へ)?\s*(\d+)[個冊枚本](?:を赤箱へ|戻|運び戻)", text, "戻した数")
    diff = _int(r"赤箱(?:は|が)白箱より\s*(\d+)[個冊枚本]多く", text, "最後の差")
    if (total + diff) % 2:
        return Dame("最後の2箱を整数に分けられない")
    # 最後の差と合計から最後の赤箱を復元してから、作業を逆順に戻す。
    final_red = (total + diff) // 2
    final_white = total - final_red
    if final_red <= 0 or final_white <= 0:
        return Dame("最後の箱の数が正でない")
    before_return = final_red - returned
    before_move = before_return + moved
    if before_return <= 0 or before_move <= 0:
        return Dame("逆算途中で箱の数が正でない")
    return before_move


def _context(text):
    initial = _int(r"(?:販売用の|売るための|販売予定の)(?:パン|ノート|りんご|カード|ボール)(?:が|を最初に)\s*(\d+)", text, "初期在庫")
    boxes = _int(r"(\d+)箱(?:が届|を入荷|は1箱)", text, "入荷箱数")
    each = _int(r"1箱(?:には|は|あたり)\s*(\d+)[個冊枚本]入?", text, "1箱の数量")
    # 3つの文型から販売数を拾い、どの無関係な数にも触れない。
    sold_match = re.search(
        r"(?:販売用から|そこから|入荷後に)\s*(\d+)[個冊枚本](?:売れ|売りました|を販売)|"
        r"(?:に|を)\s*(\d+)[個冊枚本]売りました",
        text,
    )
    if not sold_match:
        raise ValueError("販売数が読めない")
    sold = int(next(group for group in sold_match.groups() if group is not None))
    answer = initial + boxes * each - sold
    if answer < 0:
        return Dame("販売用在庫がマイナスになる")
    return answer


def kenzan(row):
    text = row["問"]
    kind = row["型"]
    if kind == "わな_順序":
        return _trap(text)
    if kind == "場合分け_切手":
        return _cases(text)
    if kind == "後戻り_箱":
        return _backtrack(text)
    if kind == "同文脈_在庫":
        return _context(text)
    return Dame("知らない型: %s" % kind)


ZEN = str.maketrans("０１２３４５６７８９，．", "0123456789,.")


def _answer_line(output):
    """答え: <値> の最後の行だけを取り出す。"""
    if not output:
        return None
    lines = [line.strip() for line in output.translate(ZEN).splitlines() if line.strip()]
    hits = re.findall(r"^答え\s*[:：]\s*([^\n]+)$", "\n".join(lines), re.M)
    return hits[-1].strip() if hits else None


def seikai(answer, output):
    """採点関数。正例・負例は self_test() で先に検査する。"""
    got = _answer_line(output)
    if got is None:
        return False
    try:
        return int(got.replace(",", "")) == int(str(answer))
    except ValueError:
        return got == str(answer)


def self_test():
    cases = [
        ("42", "説明\n答え: 42", True),
        ("42", "答え: 41", False),
        ("42", "答え 42", False),
        ("42", "答え: ４２", True),
        ("42", "", False),
    ]
    for answer, output, expected in cases:
        actual = seikai(answer, output)
        if actual != expected:
            raise AssertionError("採点関数の自己検査失敗: %r -> %r" % (output, actual))


def main():
    self_test()
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "mondai_7dan.jsonl")
    rows = [json.loads(line) for line in io.open(path, encoding="utf-8") if line.strip()]
    bad = []
    for row in rows:
        try:
            got = kenzan(row)
        except Exception as exc:  # 検算不能も食い違いとして記録する
            bad.append((row.get("id"), row.get("型"), "検算できず", "%s: %s" % (type(exc).__name__, exc)))
            continue
        if isinstance(got, Dame):
            bad.append((row.get("id"), row.get("型"), "問題が成り立たない", str(got)))
            continue
        try:
            mismatch = int(got) != int(row["答"])
        except (TypeError, ValueError):
            mismatch = str(got) != str(row["答"])
        if mismatch:
            bad.append((row.get("id"), row.get("型"), row.get("答"), got))
    print("%d問を問題文から独立検算" % len(rows))
    print("  採点関数の正例・負例: OK")
    print("  食い違い: %d 件" % len(bad))
    if bad:
        print("  型ごと:", dict(Counter(row[1] for row in bad)))
        for item in bad[:10]:
            print("   ", item)
    else:
        print("  → ★ 全問、答えが一致")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
