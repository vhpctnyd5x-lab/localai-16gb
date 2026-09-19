#!/bin/bash
# GitHub Actions の runner（公開 repo は無料・無制限）で頭脳を立てて物差しを走らせる台。Mac の資源を使わない。
# 使い方: bash dougu/actions_hakaru.sh <名札>   結果 → kekka_actions/<名札>.md（枝 kekka にも積む）
# 環境: KAGIRI=問題数（0=全部）  LLAMA_COMMIT=手元と同じ commit
set -u; export LANG=C.UTF-8
NAFUDA="${1:-$(uname -m)}"; KAGIRI="${KAGIRI:-3}"; COMMIT="${LLAMA_COMMIT:-b31b71f}"
cd "$(dirname "$0")/.."; K="$PWD"
OUT="$K/kekka_actions/${NAFUDA}.md"; mkdir -p "$K/kekka_actions"
W="${RUNNER_TEMP:-/tmp}/hakaru"; mkdir -p "$W"; M="$W/Qwen3-30B-A3B-Q2_K.gguf"
T0=$(date +%s); log(){ echo "[$(( $(date +%s) - T0 ))s] $*"; }
NP=$(nproc)
{ echo "# $NAFUDA  $(date -u +%FT%TZ)  commit $COMMIT"; echo '```'
  echo "cores $NP"; grep -m1 -i 'model name' /proc/cpuinfo || lscpu | grep -i 'model name\|vendor' | head -2
  free -g | head -2; df -h / | tail -1; echo '```'; } > "$OUT"

# 1. 盤を空ける（既定の空き 14GB では 11.3GB の頭脳が窮屈）
sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /usr/local/.ghcup /opt/hostedtoolcache/CodeQL /usr/share/swift /usr/local/share/powershell 2>/dev/null
log "盤の空き $(df -h / | tail -1 | awk '{print $4}')"

# 2. 頭脳を落とす（作りながら並行）
( curl -sSL --retry 5 --retry-delay 10 -o "$M" \
  "https://huggingface.co/unsloth/Qwen3-30B-A3B-GGUF/resolve/main/Qwen3-30B-A3B-Q2_K.gguf" ) &
DL=$!

# 3. llama.cpp を手元と同じ commit で作る
git clone -q --filter=blob:none https://github.com/ggml-org/llama.cpp "$W/llama.cpp" \
  && git -C "$W/llama.cpp" checkout -q "$COMMIT" || { echo "llama.cpp を取れない" >> "$OUT"; exit 1; }
cmake -S "$W/llama.cpp" -B "$W/build" -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF >/dev/null \
  && cmake --build "$W/build" -j"$NP" --target llama-server llama-bench >/dev/null || { echo "作れない" >> "$OUT"; exit 1; }
B="$W/build/bin"; log "作った"
wait $DL; SZ=$(stat -c %s "$M" 2>/dev/null || echo 0)
[ "$SZ" = 11258610240 ] || { echo "頭脳の大きさが違う: $SZ" >> "$OUT"; exit 1; }
log "頭脳 11.3GB 落とした"

# 4. 速さ（読み込み pp512・書き出し tg128）
{ echo; echo "## 速さ（llama-bench -t $NP）"; "$B/llama-bench" -m "$M" -t "$NP" -p 512 -n 128 -r 2 -o md 2>/dev/null; } >> "$OUT"
log "速さ測った"

# 5. 頭脳を立てて 7段の物差し（指定は kernel/server.py の local:main と同じ。-t だけ runner の数）
"$B/llama-server" -m "$M" -t "$NP" -ngl 0 -dev none -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off \
  --reasoning-format none --spec-type ngram-simple --host 127.0.0.1 --port 8080 > "$W/llama.log" 2>&1 &
P=$!
for i in $(seq 1 200); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && break; done
export KERNEL_LOCAL_URL=http://127.0.0.1:8080
{ echo; echo "## 7段 深さ0 ${KAGIRI}問"; echo '```'
  python3 -u "$K/monosashi/hakaru.py" --mondai "$K/monosashi/mondai_7dan.jsonl" --fukasa 0 --kagiri "$KAGIRI" --narabi 1 \
    --nafuda "actions-$NAFUDA" --out "$K/kekka_actions/7dan_${NAFUDA}.json" 2>&1 | tail -12; echo '```'; } >> "$OUT"
kill $P 2>/dev/null; wait $P 2>/dev/null
echo "所要 $(( $(date +%s) - T0 ))秒" >> "$OUT"; log "おわり"; cat "$OUT"
