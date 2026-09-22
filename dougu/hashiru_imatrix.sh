#!/bin/bash
# 頭脳を 1本立てて 7段（深さ0）を測り、終わったら消す。使い方: dougu/hashiru_imatrix.sh [モデル名] [問数=0(全部)] [名札の足し] [llama-server の追加指定...]
export LANG=en_US.UTF-8; cd "$(dirname "$0")"; mkdir -p kekka
M=${1:-Qwen3-30B-A3B-Q2_K-imatrix}; K=${2:-0}; N=${3:-}; shift $(( $# < 3 ? $# : 3 )); TSUIKA="$*"; B="$HOME/LocalAI_mirror/llama-latest/build/bin"; export DYLD_LIBRARY_PATH="$B"
pgrep -f "[l]lama-server -m" >/dev/null && { echo "llama-server がもう動いています（1本だけの決まり）"; exit 2; }
"$B/llama-server" -m ~/LocalAI_mirror/models/$M.gguf -t 6 -ngl 0 -dev none -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off \
  --reasoning-format none ${TSUIKA:---spec-type ngram-simple --spec-ngram-simple-size-m 16} --host 127.0.0.1 --port 8080 > kekka/llama_$M$N.log 2>&1 &
P=$!
for i in $(seq 1 100); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; done
echo "===== はじめ $(date +%T) $M $N 問数=$K 追加=[$TSUIKA] ====="
caffeinate -i /usr/local/bin/python3 -u ../monosashi/hakaru.py --mondai ../monosashi/mondai_7dan.jsonl --fukasa 0 --kagiri $K --narabi 1 --nafuda "$M$N" --out kekka/7dan_$M$N.json 2>&1 | tail -14
kill $P; wait $P 2>/dev/null; echo "===== おわり $(date +%T) ====="
