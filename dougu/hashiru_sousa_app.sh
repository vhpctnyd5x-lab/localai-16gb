#!/bin/bash
# 操作の課題を「動いているカーネル.app」に頼む。画面収録の許可はアプリ側にある。
# 合鍵は窓の引数から取る（書き置きしない）。
cd "$(dirname "$0")"; mkdir -p kekka
U=$(ps -axo command | grep "[k]ernel-window http" | grep -o "http://127.0.0.1:[0-9]*/?t=[A-Za-z0-9_-]*")
[ -z "$U" ] && { echo "カーネル.app が動いていません"; exit 2; }
for i in $(seq 1 100); do curl -sf -m 3 http://127.0.0.1:8080/health >/dev/null 2>&1 && break; sleep 3; done
echo "===== 操作の課題（アプリ経由） $(date +%T) ====="
# ★ 画面が眠ると screencapture が落ちる（2026-09-13 20:25 の正体）。caffeinate で眠らせない
KERNEL_URL="$U" caffeinate -dimsu /usr/local/bin/python3 -u hakaru_sousa_app.py 2>&1 | tee "kekka/sousa_app_$(date +%m%d_%H%M).log"
echo "===== おわり $(date +%T) ====="
