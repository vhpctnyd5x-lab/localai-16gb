#!/bin/bash
# 9/17 夜の測定（2）: 前の台本で llama-server が消える前に次が始まって飛んだ分をやり直す。段ごとに消えるのを待つ
cd "$(dirname "$0")"
matsu() { for i in $(seq 1 30); do pgrep -f "[l]lama-server" >/dev/null || return 0; sleep 2; done; pkill -9 -f "[l]lama-server"; sleep 2; }
matsu; echo "===== 書き出し 深い $(date +%T) =====";   /usr/local/bin/python3 hakaru_kaki.py --nagai a b
matsu; echo "===== 雑談の並び $(date +%T) =====";     ./hashiru_zatsudan.sh
matsu; echo "===== 通し試験 $(date +%T) =====";       ./tooshi.sh
matsu; echo "===== 道具（端末・Web） $(date +%T) ====="; ./hashiru_dougu2.sh
matsu; echo "===== 頭脳が道具を選ぶ $(date +%T) =====";  ./hashiru_erabu.sh
matsu; echo "===== おわり $(date +%T) ====="
