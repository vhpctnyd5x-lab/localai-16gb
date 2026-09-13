#!/bin/bash
# 承認の札の物差し。画面もモデルも要らない（部品は差し替えて測る）
cd "$(dirname "$0")"
echo "===== 承認の札 $(date +%T) ====="
/usr/local/bin/python3 hakaru_shounin.py < /dev/null
echo "===== おわり $(date +%T) ====="
