#!/bin/bash
# 操作の輪を実際に動かす試験（画面を乗っ取る）。本人の許しがあるときだけ。頭脳を立てて試し、終わったら片づける
cd "$(dirname "$0")"; BIN="/Volumes/Mac Windows/LocalAI/LocalAI改良/tools/llama.cpp/build/bin"; export DYLD_LIBRARY_PATH="$BIN"; mkdir -p kekka
curl -sf -m 2 http://127.0.0.1:8080/health >/dev/null 2>&1 || {
  "$BIN/llama-server" -m ~/LocalAI_mirror/models/Qwen3-30B-A3B-Q2_K.gguf -t 12 -ngl 0 -c 8192 -np 1 -cb -ub 256 --spec-type ngram-simple -ctk q8_0 -ctv q8_0 --host 127.0.0.1 --port 8080 > kekka/llama.log 2>&1 &
  for i in $(seq 1 200); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; done; }
echo "===== 操作の実動作 $(date +%T) ====="; /usr/local/bin/python3 sousa_jissou.py "$@"
pkill -x llama-server 2>/dev/null; echo "===== おわり $(date +%T) ====="
