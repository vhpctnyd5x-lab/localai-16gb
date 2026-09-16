#!/bin/bash
export LANG=en_US.UTF-8
# 深さの決め方の物差し。モデルも画面も要らない
cd "$(dirname "$0")"
echo "===== 深さの決め方 $(date +%T) ====="
/usr/local/bin/python3 -u hakaru_fukasa_sousa.py
echo "===== おわり $(date +%T) ====="
