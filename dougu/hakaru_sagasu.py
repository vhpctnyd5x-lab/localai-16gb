#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""web.sagasu の物差し。答えが一語で決まる10問を上位5件で確かめる。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

KERNEL = os.environ.get("KERNEL_DIR") or next(
    (d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"),
                 "/Volumes/Mac Windows/LocalAI/kernel")
     if os.path.isfile(os.path.join(d, "server.py"))),
    "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import web

HI = "2026-09-17"
KADAI = [
    ("富士山の標高は何メートル？", ("3776", "3,776")),
    ("日本の首都はどこ？", ("東京",)),
    ("琵琶湖がある都道府県は？", ("滋賀",)),
    ("日本で最も北にある都道府県は？", ("北海道",)),
    ("世界で最も高い山は？", ("エベレスト", "Everest", "チョモランマ")),
    ("金の元素記号は？", ("Au", "AU")),
    ("水の化学式は？", ("H2O", "H₂O")),
    ("徒然草の作者は？", ("吉田兼好", "兼好法師")),
    ("源氏物語の作者は？", ("紫式部",)),
    ("走れメロスの作者は？", ("太宰治",)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=len(KADAI))
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()
    n = max(0, min(args.limit, len(KADAI)))
    kekka = []
    print("===== 探す物差し %s / %d問 =====" % (HI, n), flush=True)
    for i, (toi, kitai) in enumerate(KADAI[:n], 1):
        t0 = time.monotonic()
        r = web.sagasu(toi, timeout=args.timeout)
        sec = time.monotonic() - t0
        shiryou = " ".join(dai + " " + batsu for dai, _url, batsu in r)
        ok = len(r) == 5 and any(x.casefold() in shiryou.casefold() for x in kitai)
        print("%2d %s %5.1f秒 期待=%s 上位=%r" %
              (i, "○" if ok else "×", sec, "/".join(kitai), r[0][0][:70] if r else "結果なし"),
              flush=True)
        kekka.append({
            "日付": HI, "問": toi, "期待": list(kitai), "○": ok,
            "秒": round(sec, 2), "検索結果数": len(r),
            "検索結果": [{"題": dai, "URL": url, "抜粋": batsu} for dai, url, batsu in r],
        })
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kekka")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "sagasu_%s_%02d.json" % (HI.replace("-", ""), n))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(kekka, f, ensure_ascii=False, indent=1)
    score = sum(1 for x in kekka if x["○"])
    print("探す: %d/%d（この1回の数字）" % (score, len(kekka)))
    print("→", out)
    return 0 if score == len(kekka) else 1


if __name__ == "__main__":
    raise SystemExit(main())
