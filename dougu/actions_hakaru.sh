#!/bin/bash
# GitHub Actions の runner（公開 repo は無料・無制限）で頭脳を立てて物差しを走らせる台。Mac の資源を使わない。
# 使い方: bash dougu/actions_hakaru.sh <名札>   結果 → kekka_actions/<名札>.md（枝 kekka にも積む）
# 環境: KAGIRI=問題数（0=全部）  LLAMA_COMMIT=手元と同じ commit
# 途中で落ちた結果には末尾の「所要」の行が無い（＝正式な数字ではない）。
set -Eeuo pipefail; export LANG=C.UTF-8
NAFUDA="${1:-$(uname -m)}"; KAGIRI="${KAGIRI:-3}"; FUKASA="${FUKASA:-0}"; COMMIT="${LLAMA_COMMIT:-b31b71f}"
[[ "$KAGIRI" =~ ^[0-9]+$ && "$FUKASA" =~ ^[0-9]+$ ]] || { echo "KAGIRI/FUKASA は整数"; exit 2; }
cd "$(dirname "$0")/.."; K="$PWD"
NAFUDA="${NAFUDA}_f${FUKASA}"; OUT="$K/kekka_actions/${NAFUDA}.md"; mkdir -p "$K/kekka_actions"
W="${RUNNER_TEMP:-/tmp}/hakaru"; mkdir -p "$W"; M="$W/Qwen3-30B-A3B-Q2_K.gguf"
# 頭脳は HF の revision と sha256 で固定（手元の物と同じ 11,258,610,240 バイト）
HF_REV=d5b1d57bd0b504ac62ae6c725904e96ef228dc74
HF_SHA=db3ce897ccc9e7d9dbf17fe083cae7880a2092aa473b45eba8b77715aa9ca170
T0=$(date +%s); log(){ echo "[$(( $(date +%s) - T0 ))s] $*"; }
NP=$(nproc); P=""; DL=""
trap 'kill $P $DL 2>/dev/null || true' EXIT
{ echo "# $NAFUDA  $(date -u +%FT%TZ)"; echo '```'
  echo "llama.cpp $COMMIT / koukai $(git rev-parse --short HEAD) / 問題 $(sha256sum monosashi/mondai_7dan.jsonl | cut -c1-12) / 頭脳 ${HF_SHA:0:12}"
  echo "runner $(grep -m1 VERSION= /etc/os-release | cut -d= -f2) $(gcc --version | head -1)"
  echo "cores $NP"; grep -m1 -i 'model name' /proc/cpuinfo || lscpu | grep -i 'model name\|vendor' | head -2
  free -g | head -2; df -h / | tail -1; echo '```'; } > "$OUT"

# 1. 盤の空きを確かめる（頭脳 11.3GB ＋ 作る分 3GB）
FREE=$(df -B1 --output=avail / | tail -1)
[ "$FREE" -gt $((15*1024*1024*1024)) ] || { echo "盤が足りない: $FREE" >> "$OUT"; exit 1; }

# 2. 頭脳を落とす（作りながら並行。途中から再開できる .part → sha256 が合ったら名前を変える）
( curl -fsSL -C - --retry 5 --retry-delay 10 --retry-all-errors -o "$M.part" \
  "https://huggingface.co/unsloth/Qwen3-30B-A3B-GGUF/resolve/$HF_REV/Qwen3-30B-A3B-Q2_K.gguf" ) &
DL=$!

# 3. llama.cpp を手元と同じ commit で作る
git clone -q --filter=blob:none https://github.com/ggml-org/llama.cpp "$W/llama.cpp"
git -C "$W/llama.cpp" checkout -q "$COMMIT"
cmake -S "$W/llama.cpp" -B "$W/build" -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF >/dev/null
cmake --build "$W/build" -j"$NP" --target llama-server llama-bench >/dev/null
B="$W/build/bin"; log "作った"
wait $DL; DL=""
echo "$HF_SHA  $M.part" | sha256sum -c --quiet || { echo "頭脳の sha256 が違う" >> "$OUT"; exit 1; }
mv "$M.part" "$M"; log "頭脳 11.3GB 落とした（sha256 一致）"

# 4. 速さ（読み込み pp512・書き出し tg128、3回）
{ echo; echo "## 速さ（llama-bench -t $NP）"; "$B/llama-bench" -m "$M" -t "$NP" -p 512 -n 128 -r 3 -o md 2>/dev/null; } >> "$OUT"
log "速さ測った"

# 5. 頭脳を立てて 7段の物差し（指定は kernel/server.py の local:main と同じ。-t だけ runner の数）
#    HENKA_FILE があれば 1行ずつ「名前|投機・KV の指定」を差し替えて同じ問題を測り、表にする（起動指定の比べ）
tateru(){ # $1=差し替える指定
  "$B/llama-server" -m "$M" -t "$NP" -ngl 0 -dev none -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off \
    --reasoning-format none $1 --host 127.0.0.1 --port 8080 > "$W/llama.log" 2>&1 &
  P=$!
  OK=""; for i in $(seq 1 200); do sleep 3; kill -0 $P 2>/dev/null || break
    curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && { OK=1; break; }; done
  [ -n "$OK" ] || { echo "頭脳が立たない"; tail -20 "$W/llama.log"; echo "頭脳が立たない: $1" >> "$OUT"; exit 1; }
}
hakaru(){ # $1=名札の付け足し
  python3 -u "$K/monosashi/hakaru.py" --mondai "$K/monosashi/mondai_7dan.jsonl" --fukasa "$FUKASA" --kagiri "$KAGIRI" --narabi 1 \
    --nafuda "actions-$NAFUDA$1" --out "$K/kekka_actions/7dan_${NAFUDA}$1.json" > "$W/7dan$1.log" 2>&1 \
    || { tail -20 "$W/7dan$1.log" | tee -a "$OUT"; echo '```' >> "$OUT"; exit 1; }
}
export LLAMA_URL=http://127.0.0.1:8080
if [ -n "${HENKA_FILE:-}" ] && [ -f "$HENKA_FILE" ]; then
  { echo; echo "## 起動指定の比べ（7段 深さ${FUKASA} ${KAGIRI}問ずつ、同じ問題）"; echo "| 名前 | 指定 | 正解率 | 平均秒 |"; echo "|---|---|---|---|"; } >> "$OUT"
  while IFS='|' read -r NA SHITEI; do
    [ -n "$NA" ] || continue
    tateru "$SHITEI"; hakaru "_$NA"; kill $P; wait $P 2>/dev/null || true; P=""
    python3 - "$K/kekka_actions/7dan_${NAFUDA}_$NA.json" "$NA" "$SHITEI" >> "$OUT" <<'PY'
import json,sys; d=json.load(open(sys.argv[1])).get("まとめ", {}); print("| %s | `%s` | %s | %s |" % (sys.argv[2], sys.argv[3], d.get("正解率"), d.get("平均秒")))
PY
    log "$NA 測った"
  done < <(grep -v '^#' "$HENKA_FILE")
else
  tateru "--spec-type ngram-simple"
  { echo; echo "## 7段 深さ${FUKASA} ${KAGIRI}問（0=全部）"; echo '```'; } >> "$OUT"
  hakaru ""; { tail -12 "$W/7dan.log"; echo '```'; } >> "$OUT"
  kill $P; wait $P 2>/dev/null || true; P=""
fi
echo "所要 $(( $(date +%s) - T0 ))秒" >> "$OUT"; log "おわり"; cat "$OUT"
