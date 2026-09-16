#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_me.py -- 物差し: 操作の輪の「目」（撮る＋読む）にかかる秒を測る。

  ★ なぜ（2026-09-16）
    頭が 1手を決める時間が 46〜122秒 → 3〜10秒 になったので、次の壁は 目（4〜8秒/手）。
    今は 全画面（Retina 2880×1800）を撮って Vision で正確に読んでいる。
    候補: ① 目当ての窓の枠だけ撮る（-R）  ② Vision の速い読み方（--fast）。
    どちらも「速いが文字を落とす」おそれがあるので、秒と 読めた文字の数を並べて見る。

  ★ 決めごと
    ・カーソルは動かさない。撮るだけ（画面の中身は手元に留め、終わったら消す）。
    ・画面収録の許可が無いと screencapture が "could not create image from display" で落ちる。
      そのときは 何も測れないので、そう言って終わる。

  使い方:  /usr/local/bin/python3 hakaru_me.py [アプリ名]   … 省略時は前にあるアプリの窓
"""
from __future__ import annotations
import os, sys, time, subprocess, tempfile
import os, sys
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel")
                                                if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import eyes, hands, sousa


def toru(rect=None):
    p = os.path.join(tempfile.gettempdir(), "kernel-hakaru-me.png")
    cmd = ["screencapture", "-x", "-t", "png"] + (["-R", "%d,%d,%d,%d" % rect] if rect else []) + [p]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    if r.returncode != 0 or not os.path.exists(p):
        raise SystemExit("画面を撮れません（%s）。システム設定 → プライバシーとセキュリティ → 画面収録 で、この端末（Claude / Terminal）を許可してください"
                         % (r.stderr or "").strip()[:60])
    return p


def hakaru(label, rect=None, fast=False, kai=2):
    byou_t, byou_y, kazu = [], [], 0
    for _ in range(kai):
        t0 = time.time(); p = toru(rect); t1 = time.time()
        d = eyes.read(p, fast=fast); t2 = time.time()
        os.remove(p)
        byou_t.append(t1 - t0); byou_y.append(t2 - t1); kazu = len(d.get("文字", []))
    print("  %-22s 撮る %.1f秒 ／ 読む %.1f秒 ／ 文字 %3d個" % (label, sorted(byou_t)[kai // 2], sorted(byou_y)[kai // 2], kazu))
    return kazu


def main():
    app = " ".join(sys.argv[1:]) or (hands.mae_no_app() or "")
    waku = sousa._mado(app) if app else None
    print("===== 目の物差し %s（前のアプリ %s ／ 窓 %s）=====" % (time.strftime("%m/%d %H:%M"), app or "不明", waku or "取れない"))
    a = hakaru("全画面・正確（今の形）")
    b = hakaru("全画面・速い", fast=True)
    if waku:
        c = hakaru("窓だけ・正確", rect=waku)
        d = hakaru("窓だけ・速い", rect=waku, fast=True)
        print("  ※ 窓だけ は文字が減って当たり前（窓の外を見ない）。比べるのは 秒。")
    print("  ※ 「速い」で文字が %d → %d に減るなら、落としているのは何かを見てから決める" % (a, b))
    return 0


if __name__ == "__main__":
    sys.exit(main())
