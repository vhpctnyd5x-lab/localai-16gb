#!/bin/bash
export LANG=en_US.UTF-8
# Bonsai 2 27B（3値・PrismML のフォーク llama.cpp）を 8080 に立てて、速さと 3問を測り、消す。
#   使い方: ./hashiru_bonsai.sh [PQ2_0|PTQ1_0] [hakaru_bonsai.py の引数…]
#   今の頭脳と同じ土俵（-t 6・CPU だけ・-c 8192）。比べる相手は ./hashiru_bonsai.sh --ima（今の頭脳を同じ物差しで）
cd "$(dirname "$0")"; mkdir -p kekka
pgrep -f "[l]lama-server -m" >/dev/null && { echo "llama-server がもう動いています（1本だけの決まり）"; exit 2; }
if [ "$1" = "--ima" ]; then shift
  BIN="$HOME/LocalAI_mirror/llama-latest/build/bin"; MODEL="$HOME/LocalAI_mirror/models/Qwen3-30B-A3B-Q2_K.gguf"; NAFUDA="ima-Qwen3-30B-A3B-Q2_K"
  OPTS=$(/usr/local/bin/python3 -c "
import os, sys; sys.path.insert(0, os.path.expanduser('~/LocalAI_mirror/kernel')); import server; print(' '.join(server.MODERU['local:main']['opts']+server._SPEC_OPTS()))")
else
  Q="${1:-PQ2_0}"; case "$Q" in PQ2_0|PTQ1_0) shift;; *) Q=PQ2_0;; esac
  BIN="$HOME/LocalAI_mirror/llama-bonsai/build/bin"; MODEL="$HOME/LocalAI_mirror/models/Ternary-Bonsai-2-27B-$Q.gguf"; NAFUDA="Bonsai2-27B-$Q"
  OPTS="-t 6 -ngl 0 -dev none -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off --reasoning-format none"
  "$BIN/llama-server" --help 2>&1 | grep -q -- "--spec-type" && OPTS="$OPTS --spec-type ngram-simple"
fi
export DYLD_LIBRARY_PATH="$BIN"
echo "===== $NAFUDA $(date +%T) ／ $OPTS ====="
"$BIN/llama-server" -m "$MODEL" $OPTS --host 127.0.0.1 --port 8080 > "kekka/llama_bonsai_$NAFUDA.log" 2>&1 &
P=$!
for i in $(seq 1 200); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; kill -0 $P 2>/dev/null || { echo "立たなかった（kekka/llama_bonsai_$NAFUDA.log）"; tail -5 "kekka/llama_bonsai_$NAFUDA.log"; exit 3; }; done
echo "立った $(date +%T)"
/usr/local/bin/python3 hakaru_bonsai.py --nafuda "$NAFUDA" "$@"
kill $P; wait $P 2>/dev/null; echo "===== おわり $(date +%T) ====="
