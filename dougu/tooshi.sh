#!/bin/bash
export LANG=en_US.UTF-8
# 通し試験（入口→振り分け→道具）。頭脳を立てて試し、終わったら片づける。起動の指定は kernel/server.py と同じもの
cd "$(dirname "$0")"; BIN="$HOME/LocalAI_mirror/llama-latest/build/bin"; [ -x "$BIN/llama-server" ] || BIN="$HOME/LocalAI_mirror/llama-latest/build/bin"; [ -x "$BIN/llama-server" ] || BIN="/Volumes/Mac Windows/LocalAI/llama-latest/build/bin"; export DYLD_LIBRARY_PATH="$BIN"; mkdir -p kekka
OWN_PID=""
katazuke() {
  if [ -n "$OWN_PID" ] && kill -0 "$OWN_PID" 2>/dev/null; then
    kill "$OWN_PID" 2>/dev/null
    wait "$OWN_PID" 2>/dev/null
  fi
}
trap katazuke EXIT
curl -sf -m 2 http://127.0.0.1:8080/health >/dev/null 2>&1 || {
  "$BIN/llama-server" -m ~/LocalAI_mirror/models/Qwen3-30B-A3B-Q2_K.gguf $(/usr/local/bin/python3 -c "
import os, sys; sys.path.insert(0, os.environ.get('KERNEL_DIR') or os.path.expanduser('~/LocalAI_mirror/kernel')); import server; print(' '.join(server.MODERU['local:main']['opts']+server._SPEC_OPTS()))") --host 127.0.0.1 --port 8080 > kekka/llama.log 2>&1 &
  OWN_PID=$!
  for i in $(seq 1 200); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; done; }
echo "===== 通し $(date +%T) ====="; /usr/local/bin/python3 tooshi.py "$@" 2>&1 | grep -v "^  \(仕事\|数え上げ\|Web\|ターミナル\):\|^    "
STATUS=${PIPESTATUS[0]}
echo "===== おわり $(date +%T) ====="
exit "$STATUS"
