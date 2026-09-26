#!/usr/bin/env python3
"""評価ファイルを読まず、同じ数値・途中計算の日英較正文を固定の種で作る。

imatrix用（学習用ではない）。32×512トークンで切るので、言語間で使用される
末尾の問題は一致しない。種・テンプレート・順序・トークン予算を固定して比べる。
"""
import argparse
import random
from pathlib import Path


def documents(language):
    rng = random.Random(260926)
    for i in range(512):
        boxes, each = rng.randint(7, 61), rng.randint(13, 97)
        used = rng.randint(1, boxes * each - 1)
        extra = rng.randint(11, 109)
        total = boxes * each
        rest = total - used
        final = rest + extra
        groups = rng.randint(3, 17)
        quotient, remainder = divmod(final, groups)
        if language == "ja":
            yield (
                f"記録{i + 1}。工房に部品の箱が{boxes}箱あり、各箱に{each}個入っています。"
                f"作業で{used}個を使い、別便で{extra}個を受け取りました。残った部品を"
                f"{groups}組に同じ個数ずつ配ると、各組の個数と余りはいくつですか。\n"
                f"最初の個数は箱数と一箱の個数の積で、{boxes} × {each} = {total}個です。\n"
                f"使用した分を引くと、{total} - {used} = {rest}個です。\n"
                f"届いた分を足すと、{rest} + {extra} = {final}個です。\n"
                f"割り算は、{final} = {groups} × {quotient} + {remainder}となります。\n"
                f"検算すると、配った数{groups * quotient}と余り{remainder}の和は{final}です。\n"
                f"答え: 各組{quotient}個、余り{remainder}個。"
            )
        else:
            yield (
                f"Record {i + 1}. A workshop has {boxes} boxes with {each} parts in each. "
                f"It uses {used} parts and receives {extra} more. The remaining parts are "
                f"shared equally among {groups} groups. How many parts does each group "
                "receive, and how many are left over?\n"
                f"Multiply the number of boxes by the parts per box: {boxes} * {each} = {total}.\n"
                f"Subtract the parts used: {total} - {used} = {rest}.\n"
                f"Add the delivery: {rest} + {extra} = {final}.\n"
                f"Divide with a remainder: {final} = {groups} * {quotient} + {remainder}.\n"
                f"Check: the distributed {groups * quotient} plus the remainder {remainder} equals {final}.\n"
                f"Answer: {quotient} per group, with {remainder} left over."
            )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--language", choices=("ja", "en"), required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.write_text("\n\n".join(documents(args.language)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
