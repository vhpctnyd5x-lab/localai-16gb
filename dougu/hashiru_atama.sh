#!/bin/bash
export LANG=en_US.UTF-8
# 頭の物差し（画面なし・14問・十数分）。8080 に頭脳が居ればそれを使い、居なければ 8090 に立てて後で消す。
cd "$(dirname "$0")"; mkdir -p kekka
BIN="$HOME/LocalAI_mirror/llama-latest/build/bin"; [ -x "$BIN/llama-server" ] || BIN="/Volumes/Mac Windows/LocalAI/llama-latest/build/bin"; export DYLD_LIBRARY_PATH="$BIN"
TATETA=""
if curl -sf -m 2 http://127.0.0.1:8080/health >/dev/null 2>&1; then
  export KERNEL_LOCAL_URL=http://127.0.0.1:8080
else
  pgrep -f llama-server >/dev/null && { echo "別の llama-server が動いています（1本だけの決まり）"; exit 2; }
  export KERNEL_LOCAL_URL=http://127.0.0.1:8090
  # ★ 指定は kernel/server.py の local:main と同じにしておく（違う指定で測ると別のものを測ることになる）
  "$BIN/llama-server" -m ~/LocalAI_mirror/models/Qwen3-30B-A3B-Q2_K.gguf $(/usr/local/bin/python3 -c "
import os, sys; sys.path.insert(0, os.environ.get('KERNEL_DIR') or os.path.expanduser('~/LocalAI_mirror/kernel')); import server; print(' '.join(server.MODERU['local:main']['opts']+server._SPEC_OPTS()))") \
    --host 127.0.0.1 --port 8090 > kekka/llama_atama.log 2>&1 &
  TATETA=$!
  for i in $(seq 1 100); do sleep 3; curl -sf -m 3 http://127.0.0.1:8090/health 2>/dev/null | grep -q ok && break; done
fi
caffeinate -i /usr/local/bin/python3 -u hakaru_atama.py "$@" 2>&1 | tee "kekka/atama_$(date +%m%d_%H%M).log"
[ -n "$TATETA" ] && { kill "$TATETA" 2>/dev/null; sleep 2; pkill -f "llama-server.*--port 8090" 2>/dev/null; }
echo "===== おわり $(date +%T) ====="
