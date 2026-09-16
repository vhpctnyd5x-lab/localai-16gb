#!/bin/bash
# 内蔵の正（~/LocalAI_mirror の kernel と koukai）を 外部SSD に写す。片方向（内蔵 → SSD）。
# ★ 2026-09-16: 外部SSDが日に何度も切れるので、動かすもの・直すものは内蔵に置き、SSD は写し置き場にした。
export LANG=en_US.UTF-8
S="/Volumes/Mac Windows/LocalAI"; M="$HOME/LocalAI_mirror"
[ -f "$S/kernel/server.py" ] || { echo "外部SSDが見えません（$S）。写さずに終わります"; exit 2; }
rsync -a --exclude __pycache__ --exclude bench_results "$M/kernel/" "$S/kernel/" && echo "kernel  → SSD に写した"
rsync -a --exclude __pycache__ "$M/koukai/" "$S/LocalAI改良/koukai/" && echo "koukai  → SSD に写した"
