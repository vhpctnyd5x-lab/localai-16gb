#!/bin/bash
export LANG=en_US.UTF-8
# GUI の本番（本人が席を外している 22:57〜24:00）: 目の速さ → 操作の課題 3問×3回。頭脳は server.py と同じ指定で 8080 に立てる
cd "$(dirname "$0")"; mkdir -p kekka
BIN="$HOME/LocalAI_mirror/llama-latest/build/bin"; export DYLD_LIBRARY_PATH="$BIN"
pgrep -f "[l]lama-server -m" >/dev/null && { echo "llama-server がもう動いています"; exit 2; }
OPTS=$(/usr/local/bin/python3 -c "
import os, sys; sys.path.insert(0, os.path.expanduser('~/LocalAI_mirror/kernel')); import server; print(' '.join(server.MODERU['local:main']['opts']+server._SPEC_OPTS()))")
"$BIN/llama-server" -m ~/LocalAI_mirror/models/Qwen3-30B-A3B-Q2_K.gguf $OPTS --host 127.0.0.1 --port 8080 > kekka/llama_gui.log 2>&1 &
P=$!
for i in $(seq 1 100); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; done
echo "===== 目の速さ $(date +%T) =====";   caffeinate -dimsu /usr/local/bin/python3 -u hakaru_me.py
echo "===== 操作 3問×3回 $(date +%T) ====="; ./hashiru_sousa3.sh
kill $P; wait $P 2>/dev/null
echo "===== GUI おわり $(date +%T) ====="
