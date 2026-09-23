#!/bin/bash
# 手順書あり／なしを 同じ問題で比べる（頭脳は 1本だけ立てて、終わったら消す）。
# 使い方: dougu/hashiru_tejun.sh <手順書ファイル | kazoeru（数え上げ電卓） | tehon（似た手本。外から KERNEL_KAZOERU=1 を渡せば両方に効く）> [問題=../monosashi/mondai_renshuu.jsonl] [名札=renshuu] [問数=0(全部)]
export LANG=en_US.UTF-8
if [ "$1" = kazoeru ] || [ "$1" = tehon ] || [ "$1" = keisan ] || [ "$1" = jikan ] || [ "$1" = narabe ]; then T=$1; else T=$(cd "$(dirname "$1")" && pwd)/$(basename "$1"); fi; Q=$(cd "$(dirname "${2:-$(dirname "$0")/../monosashi/mondai_renshuu.jsonl}")" && pwd)/$(basename "${2:-mondai_renshuu.jsonl}")
cd "$(dirname "$0")"; mkdir -p kekka; N=${3:-renshuu}; K=${4:-0}
M=Qwen3-30B-A3B-Q2_K; B="$HOME/LocalAI_mirror/llama-latest/build/bin"; export DYLD_LIBRARY_PATH="$B"
pgrep -f "[l]lama-server -m" >/dev/null && { echo "llama-server がもう動いています（1本だけの決まり）"; exit 2; }
"$B/llama-server" -m ~/LocalAI_mirror/models/$M.gguf -t 6 -ngl 0 -dev none -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off \
  --reasoning-format none --spec-type ngram-simple --spec-ngram-simple-size-m 16 --host 127.0.0.1 --port 8080 > kekka/llama_tejun.log 2>&1 &
P=$!
for i in $(seq 1 100); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; done
for x in ${DORE:-nashi ari}; do   # DORE=ari で「あり」だけ
  echo "===== $x はじめ $(date +%T) ====="
  unset KERNEL_TEJUN KERNEL_TEHON KERNEL_KEISAN KERNEL_JIKAN KERNEL_NARABE; [ "$T" = kazoeru ] && unset KERNEL_KAZOERU
  if [ $x = ari ]; then case "$T" in kazoeru) export KERNEL_KAZOERU=1;; tehon) export KERNEL_TEHON=1;; keisan) export KERNEL_KEISAN=1;; jikan) export KERNEL_JIKAN=1;; narabe) export KERNEL_NARABE=1;; *) export KERNEL_TEJUN="$T";; esac; fi
  caffeinate -i /usr/local/bin/python3 -u ../monosashi/hakaru.py --mondai "$Q" --fukasa 0 --narabi 1 --kagiri $K --nafuda "${N}_$x" --out kekka/tejun_${N}_$x.json > kekka/tejun_${N}_$x.log 2>&1; tail -4 kekka/tejun_${N}_$x.log
done
kill $P; wait $P 2>/dev/null; echo "===== おわり $(date +%T) ====="
