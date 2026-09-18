#!/bin/bash
export LANG=en_US.UTF-8
# 頭脳に言い方を作らせる（tsukuru_iikata.py）。8080 に立てて、終わったら消す。
cd "$(dirname "$0")"; mkdir -p kekka
BIN="$HOME/LocalAI_mirror/llama-latest/build/bin"; export DYLD_LIBRARY_PATH="$BIN"
pgrep -f "[l]lama-server -m" >/dev/null && { echo "llama-server がもう動いています（1本だけの決まり）"; exit 2; }
OPTS=$(/usr/local/bin/python3 -c "
import os, sys; sys.path.insert(0, os.path.expanduser('~/LocalAI_mirror/kernel')); import server; print(' '.join(server.MODERU['local:main']['opts']+server._SPEC_OPTS()))")
"$BIN/llama-server" -m ~/LocalAI_mirror/models/Qwen3-30B-A3B-Q2_K.gguf $OPTS --host 127.0.0.1 --port 8080 > kekka/llama_iikata.log 2>&1 &
P=$!
for i in $(seq 1 100); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; done
/usr/local/bin/python3 -u tsukuru_iikata.py "$@"
kill $P; wait $P 2>/dev/null; echo "===== おわり $(date +%T) ====="
