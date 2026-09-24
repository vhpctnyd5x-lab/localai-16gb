#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
moji_shuu.py -- 一文字予想の「材料」を集める

  文字の切れ目を、迷いの多さだけで当てるには、量が要る。
  14万字では、カタカナ語の途中で切れてしまった（実測）。
  Wikipedia から、話題を選ばずに広く集める。

  ・話題を選ばない（選ぶと、その話題の言い回ししか覚えない）
  ・相手のサーバーに迷惑をかけないよう、間をあける
  ・取ったものは 生の文章 のまま置く。加工はしない
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wiki

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "corpus_moji.txt")


def atsumeru(hon=300, verbose=True):
    """でたらめに選んだ記事を hon 本ぶん集める"""
    mita = set()
    if os.path.exists(OUT):
        # すでに取った題は飛ばす
        for line in open(OUT, encoding="utf-8"):
            if line.startswith("\x01"):
                mita.add(line[1:].strip())
    f = open(OUT, "a", encoding="utf-8")
    ji = 0
    try:
        machi = 1.0          # 1回ごとに空ける間（秒）
        kotowarare = 0       # 続けて断られた回数
        while len(mita) < hon:
            try:
                d = wiki._get({"action": "query", "generator": "random",
                               "grnnamespace": 0, "grnlimit": 10,
                               "prop": "extracts", "explaintext": 1,
                               "exlimit": 10})
            except Exception as e:
                # 断られたら諦めずに、長く待って出直す。
                # 前は例外がそのまま外へ出て、集める仕事ごと死んでいた（実測: 429）
                kotowarare += 1
                if kotowarare > 12:
                    if verbose:
                        print(f"\n  何度も断られたので、ここで止めます（{e}）")
                    break
                matsu = min(300.0, 10.0 * (2 ** (kotowarare - 1)))
                machi = min(10.0, machi * 1.5)   # 次からは、もっと間を空ける
                if verbose:
                    print(f"\n  断られました。{matsu:.0f}秒 待ちます（{kotowarare}回目）",
                          flush=True)
                time.sleep(matsu)
                continue
            kotowarare = 0
            pages = d.get("query", {}).get("pages", {})
            if not pages:
                break
            for p in pages.values():
                t, body = p.get("title", ""), p.get("extract", "")
                if not t or t in mita or len(body) < 400:
                    continue
                mita.add(t)
                f.write("\x01" + t + "\n" + body + "\n")
                ji += len(body)
            if verbose:
                print(f"\r  {len(mita)} 本 / {ji:,} 字", end="", flush=True)
            f.flush()
            time.sleep(machi)     # 相手のサーバーに迷惑をかけない
    except KeyboardInterrupt:
        pass
    finally:
        f.close()
    if verbose:
        print()
    return len(mita), ji


def yomu():
    """集めたものを、記事ごとに返す"""
    if not os.path.exists(OUT):
        return []
    out, buf = [], []
    for line in open(OUT, encoding="utf-8"):
        if line.startswith("\x01"):
            if buf:
                out.append("".join(buf)); buf = []
        else:
            buf.append(line)
    if buf:
        out.append("".join(buf))
    return [t for t in out if len(t) > 200]


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    print(f"Wikipedia から {n} 本 集めます")
    hon, ji = atsumeru(n)
    print(f"できあがり: {hon} 本 / {ji:,} 字 / {os.path.getsize(OUT)/1e6:.1f} MB")
