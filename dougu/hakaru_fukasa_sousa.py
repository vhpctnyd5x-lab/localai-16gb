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
    # (見出し, くり返しの数, つまずき回数, 前のつまずき方, 期待)
    ("はじめの1手（跡なし）→ 速いまま",            {},                       0, "",                  T),
    ("ちがう手を1回ずつ → 速いまま",              {("押す","ok"):1, ("打つ","a"):1}, 0, "", T),
    ("同じ手を2回くり返した → 考えさせる",         {("押す","ok"):2},        0, "",                  K),
    ("形が壊れた直後（HTTP 500）→ 考えさせる",     {},                       1, "HTTP 500: ...",     K),
    ("★時間切れの直後 → 深くしない（逆効果）",     {},                       1, "TimeoutError: timed out", T),
    ("★時間切れ＋くり返し → それでも深くしない",   {("押す","ok"):2},        2, "TimeoutError: timed out", T),
    ("読めて、くり返しも無い → 速いに戻る",        {("押す","ok"):1},        0, "",                  T),
]


def main():
    maru = 0
    for midashi, kazu, tsumazuki, ng, machi in MONDAI:
        deta = sousa._fukasa_wo_kimeru(kazu, tsumazuki, ng)
        ok = deta == machi
        maru += ok
        print("  %s  %s（深さ %d ／ 期待 %d）" % ("○" if ok else "×", midashi, deta, machi))
    print("\n  深さの決め方: %d/%d" % (maru, len(MONDAI)))

    # 頭脳の言い換えを 輪の語彙に直せるか（2026-09-13: {"手":"完了"} が通じず空回りした）
    iikae = [({"手": "完了", "報告": "x"}, "できた"), ({"手": "done"}, "できた"),
             ({"手": "無理"}, "できない"), ({"手": "押す", "文字": "a"}, "押す")]
    m2 = 0
    print()
    for te, machi in iikae:
        deta = sousa._te_no_iikae(te)["手"]
        m2 += deta == machi
        print("  %s  言い換え %s → %s（期待 %s）" % ("○" if deta == machi else "×", te["手"], deta, machi))
    print("\n  言い換え: %d/%d" % (m2, len(iikae)))
    return 0 if (maru == len(MONDAI) and m2 == len(iikae)) else 1


if __name__ == "__main__":
    sys.exit(main())
