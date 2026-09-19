#!/bin/bash
# imatrix つき Q2_K を 7段 128問（深さ0）で測る。頭脳を 1本立てて、終わったら消す。使い方: dougu/hashiru_imatrix.sh [モデル名=Qwen3-30B-A3B-Q2_K-imatrix]
export LANG=en_US.UTF-8; cd "$(dirname "$0")"; mkdir -p kekka
M=${1:-Qwen3-30B-A3B-Q2_K-imatrix}; B="$HOME/LocalAI_mirror/llama-latest/build/bin"; export DYLD_LIBRARY_PATH="$B"
pgrep -f "[l]lama-server -m" >/dev/null && { echo "llama-server がもう動いています（1本だけの決まり）"; exit 2; }
"$B/llama-server" -m ~/LocalAI_mirror/models/$M.gguf -t 6 -ngl 0 -dev none -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off \
  --reasoning-format none --spec-type ngram-simple --host 127.0.0.1 --port 8080 > kekka/llama_$M.log 2>&1 &
P=$!
for i in $(seq 1 100); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; done
echo "===== はじめ $(date +%T) $M ====="
caffeinate -i /usr/local/bin/python3 -u ../monosashi/hakaru.py --mondai ../monosashi/mondai_7dan.jsonl --fukasa 0 --kagiri 0 --narabi 1 --nafuda "$M" --out kekka/7dan_$M.json 2>&1 | tail -14
kill $P; wait $P 2>/dev/null; echo "===== おわり $(date +%T) ====="
