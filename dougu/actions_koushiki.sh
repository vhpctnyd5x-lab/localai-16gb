#!/bin/bash
# 公式ベンチマークを GitHub Actions の 1台で測る（koushiki.yml から 20台ぶん呼ばれる）。Mac の資源を使わない。
# 環境: KIJUN=mmlu_pro|ifeval|math500|aime25|gpqa  BUBUN=i/n  KAGIRI=問題数（0=全部）
# 結果 → kekka_actions/koushiki_<KIJUN>_b<i>of<n>.jsonl（1問1行。途中で止まっても そこまでは残る）
set -Eeuo pipefail; export LANG=C.UTF-8
cd "$(dirname "$0")/.."; K="$PWD"; W="${RUNNER_TEMP:-/tmp}/koushiki"; mkdir -p "$W" "$K/kekka_actions"
COMMIT="${LLAMA_COMMIT:-b31b71f}"; NP=$(nproc)
REPO=unsloth/Qwen3-30B-A3B-GGUF; MF=Qwen3-30B-A3B-Q2_K.gguf   # 手元と同じ頭脳（sha256 で固定）
HF_REV=d5b1d57bd0b504ac62ae6c725904e96ef228dc74
HF_SHA=db3ce897ccc9e7d9dbf17fe083cae7880a2092aa473b45eba8b77715aa9ca170
M="$W/$MF"; OUT="$K/kekka_actions/koushiki_${KIJUN}_b${BUBUN/\//of}.jsonl"
T0=$(date +%s); log(){ echo "[$(( $(date +%s) - T0 ))s] $*"; }
P=""; DL=""; trap 'kill $P $DL 2>/dev/null || true' EXIT

( curl -fsSL -C - --retry 5 --retry-delay 10 --retry-all-errors -o "$M.part" "https://huggingface.co/$REPO/resolve/$HF_REV/$MF" ) &
DL=$!
pip -q install datasets math-verify "lm_eval[ifeval]" >/dev/null 2>&1 &
PI=$!
git clone -q --filter=blob:none https://github.com/ggml-org/llama.cpp "$W/llama.cpp"
git -C "$W/llama.cpp" checkout -q "$COMMIT"
cmake -S "$W/llama.cpp" -B "$W/build" -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF >/dev/null
cmake --build "$W/build" -j"$NP" --target llama-server >/dev/null; log "作った"
wait $PI; wait $DL; DL=""
echo "$HF_SHA  $M.part" | sha256sum -c --quiet || { echo "頭脳の sha256 が違う"; exit 1; }
mv "$M.part" "$M"; log "頭脳 落とした（sha256 一致）"

# 考える問題（AIME など）は 4万字まで。KV を 8bit にして 16GB に収める
"$W/build/bin/llama-server" -m "$M" -t "$NP" -ngl 0 -dev none -c 40960 -np 1 -fa on -ctk q8_0 -ctv q8_0 --jinja \
  --reasoning-format none --host 127.0.0.1 --port 8080 > "$W/llama.log" 2>&1 &
P=$!
for i in $(seq 1 200); do sleep 3; curl -sf -m 3 http://127.0.0.1:8080/health | grep -q ok && break
  kill -0 $P 2>/dev/null || { tail -20 "$W/llama.log"; exit 1; }; done
log "頭脳が立った"

# 1台 6時間の上限の前（5時間20分）で止め、そこまでの結果を必ず上げる
timeout 19200 python3 -u "$K/monosashi/koushiki.py" --kijun "$KIJUN" --bubun "$BUBUN" --kagiri "${KAGIRI:-0}" --out "$OUT" \
  || log "時間切れか しくじり（ここまでの $(wc -l < "$OUT" 2>/dev/null || echo 0) 問は残す）"
log "おわり $(wc -l < "$OUT" 2>/dev/null || echo 0) 問"
