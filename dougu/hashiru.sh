#!/bin/bash
export LANG=en_US.UTF-8
# 表・文章の道具の物差し（20課題）。頭脳を立てて測り、終わったら片づける
cd "$(dirname "$0")"; BIN="$HOME/LocalAI_mirror/llama-latest/build/bin"; [ -x "$BIN/llama-server" ] || BIN="$HOME/LocalAI_mirror/llama-latest/build/bin"; [ -x "$BIN/llama-server" ] || BIN="/Volumes/Mac Windows/LocalAI/llama-latest/build/bin"; export DYLD_LIBRARY_PATH="$BIN"; mkdir -p kekka
curl -sf -m 2 http://127.0.0.1:8080/health >/dev/null 2>&1 || {
  "$BIN/llama-server" -m ~/LocalAI_mirror/models/Qwen3-30B-A3B-Q2_K.gguf $(/usr/local/bin/python3 -c "
import os, sys; sys.path.insert(0, os.environ.get('KERNEL_DIR') or os.path.expanduser('~/LocalAI_mirror/kernel')); import server; print(' '.join(server.MODERU['local:main']['opts']+server._SPEC_OPTS()))") --host 127.0.0.1 --port 8080 > kekka/llama.log 2>&1 &
  for i in $(seq 1 200); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; done; }
[ "$1" = "試す" ] && { echo "===== 3課題で試す ====="; /usr/local/bin/python3 hakaru.py 3; }
echo "===== 本番20課題 $(date +%T) ====="; /usr/local/bin/python3 hakaru.py
pkill -x llama-server 2>/dev/null; echo "===== おわり $(date +%T) ====="
