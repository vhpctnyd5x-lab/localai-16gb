#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
council_bench.py -- 「長く考えると、どれだけ解けるようになるか」を測る

  ひとりで探すと、どの手から試すかで当たり外れが出る。
  試せる通り数（＝考える時間）を絞って、
  ひとり と 5人の合議 で、解ける数がどう変わるかを見る。
"""
import os, sys, io, time, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kernel, council

CASES = [
    {"動作": "移動", "場所": "Desktop", "種類": "画像", "時期": "去年"},
    {"動作": "移動", "場所": "Downloads", "種類": "PDF", "時期": "去年"},
    {"動作": "数える", "場所": "Desktop", "種類": "画像", "時期": "去年"},
    {"動作": "一覧",  "場所": "Downloads", "種類": "PDF"},
    {"動作": "重複",  "場所": "Desktop"},
    {"動作": "大きさ", "場所": "Desktop", "種類": "画像"},
    {"動作": "移動", "場所": "Desktop", "種類": "書類", "行き先": "しょるい"},
    {"動作": "数える", "場所": "Desktop", "除く": "画像"},
    {"動作": "一覧",  "場所": "Desktop", "種類": "画像", "並べ方": "大きい順"},
    {"動作": "移動", "場所": "Desktop"},
]


def solves(fn, budget, depth):
    # 実績（policy.json）が残っていると、あとの回ほど有利になって
    # 比べものにならない。毎回まっさらから測る
    pj = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy.json")
    if os.path.exists(pj):
        os.remove(pj)
    kernel._policy.cache_clear()
    ok, t0 = 0, time.time()
    for slots in CASES:
        with contextlib.redirect_stdout(io.StringIO()):
            kernel.make_demo()
            try:
                plan = fn(slots, budget, depth)
            except Exception:
                plan = None
        ok += bool(plan)
    return ok, (time.time() - t0) * 1000


def one(slots, budget, depth):
    p, _st = kernel.solve(slots, verbose=False, budget=budget, max_depth=depth)
    return p


def many(slots, budget, depth):
    p, _st, _lg = council.deliberate(slots, per_view=3, budget=budget,
                                     max_depth=depth, verbose=False)
    return p


if __name__ == "__main__":
    n = len(CASES)
    print(f"  問題 {n} 問。「試せる通り数」を絞って、解ける数を見る\n")
    print(f"  {'考える量':<12}{'ひとり':<14}{'6人で合議':<14}{'ひとり・6倍考える':<14}")
    print("  " + "─" * 62)
    for budget in (8, 12, 20, 40, 80, 300):
        a, ta = solves(one, budget, 6)
        b, tb = solves(many, budget, 6)
        c, tc = solves(one, budget * 6, 6)
        print(f"  {budget:>4}通りまで   {a}/{n} ({ta:5.0f}ms)   "
              f"{b}/{n} ({tb:5.0f}ms)   {c}/{n} ({tc:5.0f}ms)")
    print("\n  ※ どれも掛け算は0回。変えているのは考える時間だけ")
