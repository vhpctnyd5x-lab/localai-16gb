#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enzan_sokutei.py -- 「もっと安い掛け算」は本当に要るのか、測る

  ユーザーの問い:
    「ものすごい低コストでできる掛け算・足し算はないんですかね」

  ふつうの掛け算と、ビットでやる掛け算（XOR + 1の数を数える）で、
  同じ「ベクトルの照合」を何回できるか比べる。
"""
import time, random

DIM = 10000


def hakaru(name, fn, byou=1.0):
    """1秒あたり何回できるか"""
    n, t0 = 0, time.time()
    while time.time() - t0 < byou:
        for _ in range(50):
            fn()
        n += 50
    return name, int(n / (time.time() - t0))


def main():
    print(f"■ 1万次元のベクトルを1回照合するのに、何回/秒できるか\n")

    # ① ふつうの掛け算（Python の float の内積）
    a = [random.random() for _ in range(DIM)]
    b = [random.random() for _ in range(DIM)]
    def kakezan():
        return sum(x * y for x, y in zip(a, b))

    # ② 掛け算をやめて足し算だけ（差の絶対値の合計）
    def tashizan():
        return sum(abs(x - y) for x, y in zip(a, b))

    # ③ ビットでやる（XOR して 1 の数を数える）= いまのカーネルの方法
    A = random.getrandbits(DIM)
    B = random.getrandbits(DIM)
    def bit():
        return (A ^ B).bit_count()

    kekka = []
    for nm, fn in (("① ふつうの掛け算（内積）", kakezan),
                   ("② 足し算だけ（差の合計）", tashizan),
                   ("③ ビット（XOR + 1の数）", bit)):
        kekka.append(hakaru(nm, fn))

    osoi = min(k[1] for k in kekka)
    for nm, n in kekka:
        print(f"  {nm:　<26} {n:>12,} 回/秒   （①の {n/kekka[0][1]:>7,.0f} 倍）")

    print(f"\n■ これが何を意味するか")
    hayasa = kekka[2][1] / kekka[0][1]
    print(f"  ビットのやり方は、掛け算の {hayasa:,.0f} 倍 速い。")
    print(f"  そしてカーネルは、すでにこれを使っている（hdv.py）。")

    # 4B のモデルを1文字出すのに要る掛け算の回数と比べる
    print(f"\n■ ではLLMは何をしているか")
    para = 4_000_000_000
    ichimoji = para * 2          # 1文字につき、だいたい パラメータ数 × 2 回
    byou_kake = ichimoji / kekka[0][1]
    byou_bit  = ichimoji / kekka[2][1]
    print(f"  40億パラメータのモデルは、1文字出すのに約 {ichimoji:,} 回の掛け算をする")
    print(f"    ふつうの掛け算でやると : {byou_kake:>15,.0f} 秒 / 1文字")
    print(f"    ビットのやり方でやると : {byou_bit:>15,.0f} 秒 / 1文字")
    print(f"\n  ビットにしても、まだ 1文字に {byou_bit:,.0f} 秒 かかる。")
    print(f"  足りないのは「安さ」ではなく「桁」だった。")


if __name__ == "__main__":
    main()
