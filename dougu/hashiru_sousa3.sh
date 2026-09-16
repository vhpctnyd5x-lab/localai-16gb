#!/bin/bash
export LANG=en_US.UTF-8
# 操作の課題を3回まわして中央値を見る。1回の数字は1回の数字にすぎないため。
cd "$(dirname "$0")"; mkdir -p kekka
curl -sf -m 3 http://127.0.0.1:8080/health >/dev/null 2>&1 || { echo "手元のモデルが動いていません"; exit 2; }
OUT="kekka/sousa3_$(date +%m%d_%H%M).log"
for i in 1 2 3; do
  echo "========== $i 回目  $(date +%T) =========="
  caffeinate -dimsu /usr/local/bin/python3 -u hakaru_sousa2.py
done 2>&1 | tee "$OUT"
echo "===== まとめ ====="
grep -E "^   [○×]" "$OUT" | sed 's/^   //'
echo "○の数: $(grep -c '^   ○' "$OUT") / $(grep -cE '^   [○×]' "$OUT")"
