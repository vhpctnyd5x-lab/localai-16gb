#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shirushi.py -- 頭脳が実際に見た画面と選んだ手（sousa._kiroku の jsonl）に「正しい手」の印を付ける。

  ★ AI が AI を直す輪の、材料づくり（2026-09-16）
    輪が動くたびに ~/Library/Application Support/kernel-ai/kiroku/sousa.jsonl に 1手1行で溜まる。
    ここで印を付けた行は、hakaru_atama.py --kiroku がそのまま課題として使う（画面なしで再現できる）。
    印は人か Claude が付ける。頭脳自身には付けさせない（自分の答えを正解にしてしまう）。

  使い方:
    shirushi.py                … 一覧（番号・目当て・直前の手・頭脳の手・秒・印）
    shirushi.py 見る 12        … 12番の頼み文を全部見る
    shirushi.py つける 12 '{"手":"できた"}'      … 12番の正しい手を書く
    shirushi.py つける 12 '{"手":"キー","名前":"cmd+n"}'
    shirushi.py けす 12        … 12番の印を消す
"""
from __future__ import annotations
import json, os, sys

KIROKU = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "kernel-ai", "kiroku", "sousa.jsonl")


def yomu():
    if not os.path.exists(KIROKU):
        return []
    out = []
    with open(KIROKU, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
    return out


def kaku(rows):
    with open(KIROKU + ".tmp", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(KIROKU + ".tmp", KIROKU)


def main():
    a = sys.argv[1:]
    rows = yomu()
    if not a:
        print("記録: %d手 ／ 印つき: %d" % (len(rows), sum(1 for r in rows if r.get("正しい手"))))
        for i, r in enumerate(rows):
            mae = (r.get("履歴") or [""])[-1] if r.get("履歴") else "（最初）"
            print("%4d %s %-26s 前:%-28s 手:%-36s %4.0f秒 %s" % (
                i, r.get("時", "")[5:16], (r.get("目当て") or "")[:26], mae[:28],
                json.dumps(r.get("手"), ensure_ascii=False)[:36] if r.get("手") else ("×" + (r.get("つまずき") or "")[:30]),
                r.get("秒", 0), ("印:" + json.dumps(r["正しい手"], ensure_ascii=False)) if r.get("正しい手") else ""))
        return 0
    n = int(a[1])
    if a[0] == "見る":
        r = rows[n]
        print(json.dumps({k: v for k, v in r.items() if k not in ("画面",)}, ensure_ascii=False, indent=1))
        g = r.get("画面") or {}
        print("画面: 前のアプリ %s ／ 窓の題 %s ／ 文字 %d個: %s" % (g.get("アプリ"), g.get("窓の題"), len(g.get("文字") or []),
                                                         " / ".join(m["文"] for m in (g.get("文字") or [])[:60])))
    elif a[0] == "つける":
        te = json.loads(a[2])
        assert isinstance(te, dict) and te.get("手"), "正しい手は {\"手\": ...} の形"
        rows[n]["正しい手"] = te; kaku(rows); print("%d番に印: %s" % (n, json.dumps(te, ensure_ascii=False)))
    elif a[0] == "けす":
        rows[n]["正しい手"] = None; kaku(rows); print("%d番の印を消した" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
