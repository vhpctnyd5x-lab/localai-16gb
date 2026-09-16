#!/bin/bash
export LANG=en_US.UTF-8
# 考える深さの物差し（monosashi/hakaru.py・120問・機械採点）を、今の server.py の起動指定で回す。
# 使い方: ./hashiru_fukasa120.sh 0 2            … 深さ0 と 深さ2（省略時）
#         ./hashiru_fukasa120.sh 2 --mondai ../monosashi/mondai_6dan.jsonl   … 難しい方（結果は fukasa6dan_f2.json）
#         深さ -1 は「おまかせ」（teachers.fukasa_miru と同じ決め方）
cd "$(dirname "$0")"; mkdir -p kekka
BIN="$HOME/LocalAI_mirror/llama-latest/build/bin"; [ -x "$BIN/llama-server" ] || BIN="/Volumes/Mac Windows/LocalAI/llama-latest/build/bin"; export DYLD_LIBRARY_PATH="$BIN"
pgrep -f llama-server >/dev/null && { echo "llama-server がもう動いています（1本だけの決まり）"; exit 2; }
FUKASA=(); REST=()
for a in "$@"; do case "$a" in [0-3]|-1) FUKASA+=("$a");; *) REST+=("$a");; esac; done
NAME=120; for ((i=0;i<${#REST[@]};i++)); do [ "${REST[$i]}" = "--mondai" ] && NAME=$(basename "${REST[$((i+1))]}" .jsonl | sed "s/^mondai_//; s/^mondai$/120/"); done
[ ${#FUKASA[@]} -eq 0 ] && FUKASA=(0 2)
OPTS=$(/usr/local/bin/python3 -c "
import os, sys; sys.path.insert(0, os.environ.get('KERNEL_DIR') or os.path.expanduser('~/LocalAI_mirror/kernel')); import server; print(' '.join(server.MODERU['local:main']['opts']+server._SPEC_OPTS()))")
"$BIN/llama-server" -m ~/LocalAI_mirror/models/Qwen3-30B-A3B-Q2_K.gguf $OPTS --host 127.0.0.1 --port 8080 > kekka/llama_fukasa.log 2>&1 &
for i in $(seq 1 100); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; done
echo "===== 深さの物差し $(date +%T) ／ 指定: $OPTS ====="
for f in "${FUKASA[@]}"; do
  echo "── 深さ $f $(date +%T)"
  # 途中（.tochuu.jsonl）が残っていれば続きから。やり直したいときは消してから
  caffeinate -i /usr/local/bin/python3 -u ../monosashi/hakaru.py --fukasa "$f" --narabi 1 --out "kekka/fukasa${NAME}_f$f.json" "${REST[@]}" 2>&1 | grep -vE "^\s+[0-9]+/[0-9]+ " 
done
pkill -f "llama-server -m" 2>/dev/null
for i in $(seq 1 20); do pgrep -f "llama-server -m" >/dev/null || break; sleep 1; done   # 消えるのを待つ（次の台本が「もう動いている」で止まらないように）
pgrep -f "llama-server -m" >/dev/null && pkill -9 -f "llama-server -m"
echo "===== おわり $(date +%T) ====="
