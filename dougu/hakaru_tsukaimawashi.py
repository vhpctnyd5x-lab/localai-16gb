#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_tsukaimawashi.py -- 頼み文の前半が どれだけ使い回せているか測る。

画面は占領しない（見るだけ・押さない）。手が増えていく様子だけ真似て、
頭脳を3回呼び、llama.log の f_sim（前半の一致ぐあい）と 秒を見る。
"""
from __future__ import annotations
import os, re, sys, time
sys.path.insert(0, "/Volumes/Mac Windows/LocalAI/kernel")
import sousa

LOG = os.path.expanduser("~/Library/Application Support/kernel-ai/llama.log")
_FSIM = re.compile(r"f_sim_best = ([0-9.]+)")


def _fsim_ato(ichi: int):
    with open(LOG, errors="replace") as f:
        f.seek(ichi)
        return [float(m) for m in _FSIM.findall(f.read())]


def main():
    g = sousa._gamen(None)
    print("  見えている文字: %d個" % len(g["文字"]))
    rireki = []
    for ban in range(1, 4):
        ichi = os.path.getsize(LOG)
        t = time.time()
        te, ng = sousa._te_wo_kimeru("メモを開いて、新しいメモに カーネル試験0913 と書いて",
                                     rireki, g, 180, fukasa=0)
        byou = time.time() - t
        f = _fsim_ato(ichi)
        print("  %d回目: %5.1f秒 ／ 前半の使い回し %s ／ 返し %s"
              % (ban, byou, ("%.3f" % f[-1]) if f else "（記録なし）",
                 (str(te) if te else ng)[:60]))
        rireki.append("アプリ「Notes」を前に出す" if ban == 1 else "キー cmd+n を押す")
    print("\n  ※ 1回目は前の話の続きなので低くて当たり前。2回目以降が高ければ、前半を読み直していない")
    return 0


if __name__ == "__main__":
    sys.exit(main())
