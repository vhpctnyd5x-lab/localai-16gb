#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_fukasa_sousa.py -- 物差し: 操作の輪が「深さ」を自分で決められるか。

モデルも画面も要らない。決め方（純粋な関数）だけを測る。
  ふつうは 1（安い）。**困った跡があるときだけ** 2（高い）。
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/Volumes/Mac Windows/LocalAI/kernel")
import sousa

T, K = sousa.FUKASA_TE, sousa.FUKASA_KOMATTA

MONDAI = [
    ("はじめの1手（跡なし）→ 安いまま",                {},                       0, T),
    ("ちがう手を1回ずつ → 安いまま",                  {("押す","ok"):1, ("打つ","a"):1}, 0, T),
    ("同じ手を2回くり返した → 深くする",              {("押す","ok"):2},        0, K),
    ("手が読めなかった直後 → 深くする",               {},                       1, K),
    ("読めなかったのが続く → 深いまま",               {("押す","ok"):1},        3, K),
    ("読めて、くり返しも無い → 安いに戻る",           {("押す","ok"):1},        0, T),
]


def main():
    maru = 0
    for midashi, kazu, tsumazuki, machi in MONDAI:
        deta = sousa._fukasa_wo_kimeru(kazu, tsumazuki)
        ok = deta == machi
        maru += ok
        print("  %s  %s（深さ %d ／ 期待 %d）" % ("○" if ok else "×", midashi, deta, machi))
    print("\n  深さの決め方: %d/%d" % (maru, len(MONDAI)))
    return 0 if maru == len(MONDAI) else 1


if __name__ == "__main__":
    sys.exit(main())
