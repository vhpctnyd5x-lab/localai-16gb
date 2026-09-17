#!/bin/bash
# 9/17 夜の測定（前の測定が終わるのを待ってから）: 読み込み -t 6、書き出し 下書き役、雑談の並び、通し試験、道具の物差し
cd "$(dirname "$0")"
for i in $(seq 1 1080); do pgrep -f "[h]ashiru_fukasa120|[m]onosashi/hakaru" >/dev/null || break; sleep 10; done
for i in $(seq 1 30); do pgrep -f "[l]lama-server -m" >/dev/null || break; sleep 2; done
echo "===== 読み込み L vs N $(date +%T) =====";  ./hashiru_yomi.sh L N
echo "===== 書き出し 浅い $(date +%T) =====";   /usr/local/bin/python3 hakaru_kaki.py a b i j k
echo "===== 書き出し 深い $(date +%T) =====";   /usr/local/bin/python3 hakaru_kaki.py --nagai a b i
echo "===== 雑談の並び $(date +%T) =====";     ./hashiru_zatsudan.sh
echo "===== 通し試験 $(date +%T) =====";       ./tooshi.sh
echo "===== 道具（端末・Web） $(date +%T) ====="; ./hashiru_dougu2.sh
echo "===== 夜の測定 おわり $(date +%T) ====="
