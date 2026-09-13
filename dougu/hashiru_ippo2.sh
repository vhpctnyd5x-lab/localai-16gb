#!/bin/bash
# 1手の秒を 目と頭に分ける。押さない・打たないので安全
cd "$(dirname "$0")"
curl -sf -m 3 http://127.0.0.1:8080/health >/dev/null 2>&1 || { echo "手元のモデルが動いていません"; exit 2; }
echo "===== 1手の内訳 $(date +%T) ====="
/usr/local/bin/python3 -u hakaru_ippo.py
echo "===== おわり $(date +%T) ====="
