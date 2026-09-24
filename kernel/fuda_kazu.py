#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fuda_kazu.py -- 札の言葉が、世の中でどれくらい ありふれているか を数える

  【なぜ要るか】実測した失敗:
      「机の上の画像の枚数を教えて」→ 数えるはずが 一覧 になった
  札には「教えて→一覧」と「枚数を教えて→数える」の両方がある。
  いまは SEED に書いた順で先に見たほうが勝つ。順番は理由になっていない。

  【考え方】
  「教えて」は何にでも付く言葉。だから 何も決めない。
  「枚数を教えて」は そうそう言わない言葉。だから 強く決める。
  ありふれている＝弱い。珍しい＝強い。これを 数えるだけ で出す。

  【掛け算なし】
  資料に何回出たかを数える。大小を比べるだけ。割り算も log も使わない。
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fuda_kazu.json")


def kazoeru(corpus_path, verbose=True):
    sys.path.insert(0, HERE)
    import kernel
    text = open(corpus_path, encoding="utf-8").read()
    kazu = {}
    for i, key in enumerate(kernel.SEED):
        n, k, w = 0, 0, len(key)
        while True:
            k = text.find(key, k)
            if k < 0:
                break
            n += 1
            k += w
        kazu[key] = n
        if verbose and i % 20 == 0:
            print(f"\r  {i}/{len(kernel.SEED)}", end="", flush=True)
    if verbose:
        print(f"\r  {len(kazu)} 語 数え終わり")
    json.dump({"字数": len(text), "回数": kazu}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    return kazu


_yomi = [None]


def yomu():
    """{札の言葉: 出た回数}。無ければ空。読み込みは一度だけ"""
    if _yomi[0] is None:
        try:
            _yomi[0] = json.load(open(OUT, encoding="utf-8"))["回数"]
        except Exception:
            _yomi[0] = {}
    return _yomi[0]


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "corpus_snap_A.txt")
    kazu = kazoeru(p)
    ari = sorted(kazu.items(), key=lambda x: -x[1])
    print("\n■ ありふれている札（＝弱いはず）")
    for k, n in ari[:12]:
        print(f"  {k:　<10} {n:>7}")
    print("\n■ 珍しい札（＝強いはず）")
    for k, n in ari[-12:]:
        print(f"  {k:　<10} {n:>7}")
