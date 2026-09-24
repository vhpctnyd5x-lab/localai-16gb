#!/bin/bash
# GitHub Actions の runner（公開 repo は無料・無制限）で頭脳を立てて物差しを走らせる台。Mac の資源を使わない。
# 使い方: bash dougu/actions_hakaru.sh <名札>   結果 → kekka_actions/<名札>.md（枝 kekka にも積む）
# 環境: KAGIRI=問題数（0=全部）  LLAMA_COMMIT=手元と同じ commit
# 途中で落ちた結果には末尾の「所要」の行が無い（＝正式な数字ではない）。
set -Eeuo pipefail; export LANG=C.UTF-8
parse_branch(){
  local b="$1" token
  has(){ [[ "$b" =~ (^|-)${1}(-|$) ]]; }
  DAN=7; FUKASA=0; EXPERTS=""; QUANT=""; MEM_GB=""; UB=""; KVQ=""; JIKKEN=""; PPLONLY=""
  KERNEL_KAZOERU=""; KERNEL_JIKAN=""; KERNEL_NARABE=""; KERNEL_ERABI=""
  KERNEL_HAYASA=""; KERNEL_KEISAN=""; KERNEL_TEHON=""; KERNEL_LORA=""; ATAMA=""
  for token in k j n s v c t l; do has "$token" && case "$token" in
    k) KERNEL_KAZOERU=1;; j) KERNEL_JIKAN=1;; n) KERNEL_NARABE=1;; s) KERNEL_ERABI=1;;
    v) KERNEL_HAYASA=1;; c) KERNEL_KEISAN=1;; t) KERNEL_TEHON=1;; l) KERNEL_LORA=1;; esac
  done
  for token in 8 9 10 11 12; do has "d${token}" && DAN="$token"; done
  has f1 && FUKASA=1; has f2 && FUKASA=2
  has m2507 && ATAMA=2507
  if [[ "$b" =~ (^|-)e([4-7])(-|$) ]]; then EXPERTS="${BASH_REMATCH[2]}"; fi
  if [[ "$b" =~ (^|-)q(iq1s|iq1m|iq2xxs|iq2m|q2kxl)(-|$) ]]; then QUANT="${BASH_REMATCH[2]}"; fi
  if [[ "$b" =~ (^|-)g([1-9][0-9]*)(-|$) ]]; then MEM_GB="${BASH_REMATCH[2]}"; fi
  if [[ "$b" =~ (^|-)ub([1-9][0-9]*)(-|$) ]]; then UB="${BASH_REMATCH[2]}"; fi
  if [[ "$b" =~ (^|-)x([A-Za-z0-9_]+)(-|$) ]]; then JIKKEN="${BASH_REMATCH[2]}"; fi
  has kvq8 && KVQ=8; has kvq4 && KVQ=4; has pplonly && PPLONLY=1
  if [[ -n "$QUANT" && -n "$ATAMA" ]]; then echo '-q and -m2507 cannot be combined' >&2; return 2; fi
  if [[ "${b:0:12}" == hakaru-henka && "$b" =~ (^|-)henka(-|$) ]]; then HENKA_FILE=dougu/actions_henka.txt; else HENKA_FILE=""; fi
  if [[ -z "${KAGIRI:-}" ]]; then
    if [[ "$b" =~ ^hakaru-zenbu(-|$) ]]; then KAGIRI=0
    elif [[ -n "$HENKA_FILE" ]]; then KAGIRI=16
    else KAGIRI=3; fi
  fi
}
if [[ "${1:-}" == --parse-branch ]]; then
  parse_branch "${2:?branch name required}"
  printf 'DAN=%s FUKASA=%s EXPERTS=%s QUANT=%s MEM_GB=%s KAGIRI=%s ATAMA=%s KERNEL_KAZOERU=%s KERNEL_JIKAN=%s KERNEL_NARABE=%s KERNEL_ERABI=%s KERNEL_HAYASA=%s KERNEL_KEISAN=%s KERNEL_TEHON=%s KERNEL_LORA=%s HENKA_FILE=%s\n' \
    "$DAN" "$FUKASA" "$EXPERTS" "$QUANT" "$MEM_GB" "$KAGIRI" "$ATAMA" \
    "${KERNEL_KAZOERU:-}" "${KERNEL_JIKAN:-}" "${KERNEL_NARABE:-}" "${KERNEL_ERABI:-}" \
    "${KERNEL_HAYASA:-}" "${KERNEL_KEISAN:-}" "${KERNEL_TEHON:-}" "${KERNEL_LORA:-}" "${HENKA_FILE:-}"
  printf 'UB=%s KVQ=%s JIKKEN=%s PPLONLY=%s\n' "${UB:-}" "${KVQ:-}" "${JIKKEN:-}" "${PPLONLY:-}"
  exit 0
fi
NAFUDA="${1:-$(uname -m)}"; REF_NAME="${GITHUB_REF_NAME:-hakaru}"
# hakaru* の枝だけ 枝の名から読む。hyou.yml（GSM8K の錨）は DAN・KERNEL_* を環境で渡すので そのまま使う（9/24 Claude）
if [[ "$REF_NAME" == hakaru* ]]; then parse_branch "$REF_NAME"; else DAN="${DAN:-7}"; KAGIRI="${KAGIRI:-0}"; EXPERTS=""; QUANT=""; MEM_GB=""; UB=""; KVQ=""; JIKKEN=""; PPLONLY=""; HENKA_FILE="${HENKA_FILE:-}"; fi
FUKASA="${FUKASA:-0}"; COMMIT="${LLAMA_COMMIT:-b31b71f}"
[[ "$KAGIRI" =~ ^[0-9]+$ && "$FUKASA" =~ ^[0-9]+$ ]] || { echo "KAGIRI/FUKASA は整数"; exit 2; }
cd "$(dirname "$0")/.."; K="$PWD"
JIKKEN_ENV=""; TRANSFORM=""; BI_DUMP_PATH=""; VOCAB_KEEP_PATH=""
if [[ -n "${JIKKEN:-}" ]]; then
  JIKKEN_ENV="$K/dougu/jikken/$JIKKEN.env"
  [[ -f "$JIKKEN_ENV" ]] || { echo "実験設定がない: dougu/jikken/$JIKKEN.env" >&2; exit 2; }
  line_no=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    ((line_no += 1))
    [[ "$line" =~ ^(KOUKAI_[A-Z_]+)=([A-Za-z0-9,._/-]+)$ ]] || { echo "不正な実験設定: $JIKKEN_ENV:$line_no" >&2; exit 2; }
    key="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"
    printf -v "$key" '%s' "$value"; export "$key"
  done < "$JIKKEN_ENV"
  if [[ -n "${KOUKAI_TRANSFORM:-}" ]]; then
    [[ "$KOUKAI_TRANSFORM" =~ ^[A-Za-z0-9_]+\.py$ && -f "$K/dougu/$KOUKAI_TRANSFORM" ]] || { echo "変換台本は dougu 内の .py を指定: $KOUKAI_TRANSFORM" >&2; exit 2; }
    TRANSFORM="$KOUKAI_TRANSFORM"
  fi
  if [[ "${KOUKAI_BI_DUMP:-}" == 1 ]]; then BI_DUMP_PATH=1; fi
  if [[ -n "${KOUKAI_VOCAB_KEEP:-}" ]]; then
    [[ "$KOUKAI_VOCAB_KEEP" =~ ^[A-Za-z0-9_.-]+$ && -f "$K/dougu/jikken/$KOUKAI_VOCAB_KEEP" ]] || { echo "語彙ファイルは dougu/jikken 内のファイル名を指定: $KOUKAI_VOCAB_KEEP" >&2; exit 2; }
    VOCAB_KEEP_PATH="$K/dougu/jikken/$KOUKAI_VOCAB_KEEP"
    export KOUKAI_VOCAB_KEEP="$VOCAB_KEEP_PATH"
  fi
fi
W="${RUNNER_TEMP:-/tmp}/hakaru"; mkdir -p "$W"
# 頭脳は HF の revision と sha256 で固定。ATAMA=2507 で Instruct-2507 版。
if [ "${ATAMA:-}" = 2507 ]; then
  REPO=unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF; MF=Qwen3-30B-A3B-Instruct-2507-Q2_K.gguf; NAFUDA="${NAFUDA}_m2507"
  HF_REV=eea7b2be5805a5f151f8847ede8e5f9a9284bf77
  HF_SHA=50a46f567cf1f4d687f9d5b8d4641654e71a4cfb7b02baab479dedc0bd05d3d3
else
  REPO=unsloth/Qwen3-30B-A3B-GGUF
  HF_REV=d5b1d57bd0b504ac62ae6c725904e96ef228dc74
  case "${QUANT:-}" in
    iq1s) MF=Qwen3-30B-A3B-UD-IQ1_S.gguf;; iq1m) MF=Qwen3-30B-A3B-UD-IQ1_M.gguf;;
    iq2xxs) MF=Qwen3-30B-A3B-UD-IQ2_XXS.gguf;; iq2m) MF=Qwen3-30B-A3B-UD-IQ2_M.gguf;;
    q2kxl) MF=Qwen3-30B-A3B-UD-Q2_K_XL.gguf;; *) MF=Qwen3-30B-A3B-Q2_K.gguf;;
  esac
  if [[ -n "${QUANT:-}" ]]; then
    HF_SHA=$(curl -fsSL "https://huggingface.co/api/models/$REPO/tree/$HF_REV?recursive=true&expand=true" | python3 -c 'import json,sys; name=sys.argv[1]; rows=json.load(sys.stdin); row=next((x for x in rows if x.get("path")==name), None); print(row["lfs"]["oid"] if row and row.get("lfs",{}).get("oid") else "")' "$MF")
    [[ "$HF_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "量子化ファイルの lfs.oid が取れない: $MF" >&2; exit 1; }
  else
    HF_SHA=db3ce897ccc9e7d9dbf17fe083cae7880a2092aa473b45eba8b77715aa9ca170
  fi
fi
M="$W/$MF"
[ "${KERNEL_KAZOERU:-}" = 1 ] && NAFUDA="${NAFUDA}_k"
[ "${KERNEL_TEHON:-}" = 1 ] && NAFUDA="${NAFUDA}_t"
[ "${KERNEL_KEISAN:-}" = 1 ] && NAFUDA="${NAFUDA}_c"
[ "${KERNEL_JIKAN:-}" = 1 ] && NAFUDA="${NAFUDA}_j"
[ "${KERNEL_NARABE:-}" = 1 ] && NAFUDA="${NAFUDA}_n"
[ "${KERNEL_ERABI:-}" = 1 ] && NAFUDA="${NAFUDA}_s"
[ "${KERNEL_HAYASA:-}" = 1 ] && NAFUDA="${NAFUDA}_v"
LORA=""; [ "${KERNEL_LORA:-}" = 1 ] && { NAFUDA="${NAFUDA}_l"; LORA="--lora $K/lora/tehon-lora.gguf"; }
DAN="${DAN:-7}"; [ "$DAN" = 7 ] || NAFUDA="${NAFUDA}_d$DAN"
[[ -n "${EXPERTS:-}" ]] && NAFUDA="${NAFUDA}_e$EXPERTS"
[[ -n "${QUANT:-}" ]] && NAFUDA="${NAFUDA}_q$QUANT"
[[ -n "${MEM_GB:-}" ]] && NAFUDA="${NAFUDA}_g$MEM_GB"
[[ -n "${JIKKEN:-}" ]] && NAFUDA="${NAFUDA}_x$JIKKEN"
[[ -n "${UB:-}" ]] && NAFUDA="${NAFUDA}_ub$UB"
[[ -n "${KVQ:-}" ]] && NAFUDA="${NAFUDA}_kvq$KVQ"
[[ -n "${PPLONLY:-}" ]] && NAFUDA="${NAFUDA}_pplonly"
if [[ "$BI_DUMP_PATH" == 1 ]]; then
  BI_DUMP_PATH="$K/kekka_actions/bi_${NAFUDA}.tsv"
  export KOUKAI_BI_DUMP="$BI_DUMP_PATH"
  export KOUKAI_BI_DUMP_PATH="$BI_DUMP_PATH"
fi
QF="$K/monosashi/mondai_${DAN}dan.jsonl"; [ -f "$QF" ] || QF="$K/monosashi/mondai_${DAN}.jsonl"   # 公式の物差し（gsm8k 等）
[ -n "${BUBUN:-}" ] && NAFUDA="${NAFUDA}_b${BUBUN/\//of}"
NAFUDA="${NAFUDA}_f${FUKASA}"; OUT="$K/kekka_actions/${NAFUDA}.md"; mkdir -p "$K/kekka_actions"
T0=$(date +%s); log(){ echo "[$(( $(date +%s) - T0 ))s] $*"; }
PATCH_SHA=""
[[ ! -f "$K/llama_patch/koukai.patch" ]] || PATCH_SHA=$(sha256sum "$K/llama_patch/koukai.patch" | cut -c1-64)
NP=$(nproc); P=""; DL=""
CGROOT="/sys/fs/cgroup/koukai-actions-$(id -u)-$$"; SERVER_CG=""; SERVER_PID=""
new_cgroup(){
  local name="$1"; local path="$CGROOT-$name-$$"   # 1つの local の中で name はまだ使えない（set -u で落ちた 9/24）
  sudo mkdir "$path"
  sudo sh -c 'echo "$1" > "$2/memory.max"; echo 0 > "$2/memory.swap.max"' sh "$((MEM_GB * 1024 * 1024 * 1024))" "$path"
  printf '%s' "$path"
}
run_in_cgroup(){
  local path="$1" uid gid keep; shift; uid=$(id -u); gid=$(id -g)
  keep=$(compgen -e | grep '^KOUKAI_' | paste -sd, || true)
  if [[ -n "$keep" ]]; then
    sudo --preserve-env="$keep" bash -c 'echo $$ > "$1/cgroup.procs"; shift; uid="$1"; gid="$2"; shift 2; exec setpriv --reuid="$uid" --regid="$gid" --init-groups -- "$@"' _ "$path" "$uid" "$gid" "$@"
  else
    sudo bash -c 'echo $$ > "$1/cgroup.procs"; shift; uid="$1"; gid="$2"; shift 2; exec setpriv --reuid="$uid" --regid="$gid" --init-groups -- "$@"' _ "$path" "$uid" "$gid" "$@"
  fi
}
cgroup_report(){
  local path="$1" label="$2" peak="?" major="?" oom=0
  [ -n "$path" ] || return 0
  peak=$(sudo cat "$path/memory.peak" 2>/dev/null || echo '?')
  major=$(sudo awk '$1=="pgmajfault" {print $2}' "$path/memory.stat" 2>/dev/null || true); major="${major:-?}"
  oom=$(sudo awk '$1=="oom_kill" {print $2}' "$path/memory.events" 2>/dev/null || echo 0)
  echo "$label cgroup memory.peak: $peak bytes; pgmajfault: $major" >> "$OUT"
  if (( oom > 0 )); then echo "$MEM_GB GB で落ちた（$label、OOM kill）" >> "$OUT"; fi
  sudo rmdir "$path" 2>/dev/null || true
}
cleanup(){
  [ -z "$SERVER_PID" ] || kill "$SERVER_PID" 2>/dev/null || true
  kill $P $DL 2>/dev/null || true
  [ -z "$P" ] || wait "$P" 2>/dev/null || true
  [ -z "$DL" ] || wait "$DL" 2>/dev/null || true
  [ -z "$SERVER_CG" ] || cgroup_report "$SERVER_CG" llama-server
}
trap cleanup EXIT
{ echo "# $NAFUDA  $(date -u +%FT%TZ)"; echo '```'
  echo "llama.cpp $COMMIT / koukai $(git rev-parse --short HEAD) / 問題 $(sha256sum "$QF" | cut -c1-12) / 頭脳 ${HF_SHA:0:12}"
  [[ -z "${PATCH_SHA:-}" ]] || echo "llama patch sha256 ${PATCH_SHA:0:12}"
  [[ -z "${JIKKEN:-}" ]] || echo "実験 $JIKKEN_ENV"
  [[ -z "$TRANSFORM" ]] || echo "変換 $TRANSFORM"
  [[ -z "$BI_DUMP_PATH" ]] || echo "BI dump $BI_DUMP_PATH"
  [[ -z "$VOCAB_KEEP_PATH" ]] || echo "vocab keep $VOCAB_KEEP_PATH"
  [[ -z "${EXPERTS:-}" ]] || echo "専門家数 $EXPERTS"
  [[ -z "${MEM_GB:-}" ]] || echo "メモリ上限 ${MEM_GB} GB（swap なし、mmap ページキャッシュを含む）"
  echo "runner $(grep -m1 VERSION= /etc/os-release | cut -d= -f2) $(gcc --version | head -1)"
  echo "cores $NP"; grep -m1 -i 'model name' /proc/cpuinfo || lscpu | grep -i 'model name\|vendor' | head -2
  free -g | head -2; df -h / | tail -1; echo '```'; } > "$OUT"

# 1. 盤の空きを確かめる（頭脳 11.3GB ＋ 作る分 3GB）
FREE=$(df -B1 --output=avail / | tail -1)
[ "$FREE" -gt $((15*1024*1024*1024)) ] || { echo "盤が足りない: $FREE" >> "$OUT"; exit 1; }

# 2. 頭脳を落とす（作りながら並行。途中から再開できる .part → sha256 が合ったら名前を変える）
( curl -fsSL -C - --retry 5 --retry-delay 10 --retry-all-errors -o "$M.part" \
  "https://huggingface.co/$REPO/resolve/$HF_REV/$MF" ) &
DL=$!

# 3. llama.cpp を手元と同じ commit で作る
git clone -q --filter=blob:none https://github.com/ggml-org/llama.cpp "$W/llama.cpp"
git -C "$W/llama.cpp" checkout -q "$COMMIT"
if [[ -f "$K/llama_patch/koukai.patch" ]]; then
  git -C "$W/llama.cpp" apply "$K/llama_patch/koukai.patch"
fi
cmake -S "$W/llama.cpp" -B "$W/build" -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF >/dev/null
cmake --build "$W/build" -j"$NP" --target llama-server llama-bench llama-perplexity >/dev/null
B="$W/build/bin"; log "作った"
wait $DL; DL=""
echo "$HF_SHA  $M.part" | sha256sum -c --quiet || { echo "頭脳の sha256 が違う" >> "$OUT"; exit 1; }
mv "$M.part" "$M"; log "頭脳 11.3GB 落とした（sha256 一致）"
if [[ -n "$TRANSFORM" ]]; then
  NEW_M="$W/${MF%.gguf}_x${JIKKEN}.gguf"
  PYTHONPATH="$W/llama.cpp/gguf-py${PYTHONPATH:+:$PYTHONPATH}" python3 "$K/dougu/$TRANSFORM" "$M" "$NEW_M"
  M="$NEW_M"; log "変換済み頭脳を使う: $TRANSFORM"
fi

# 4. 速さ（読み込み pp512・書き出し tg128、3回）
OVERRIDE_ARGS=(); [[ -n "${EXPERTS:-}" ]] && OVERRIDE_ARGS+=(--override-kv "qwen3moe.expert_used_count=int:$EXPERTS")
BENCH_ARGS=(); [[ -n "${UB:-}" ]] && BENCH_ARGS+=(-ub "$UB")
if [[ -n "${KVQ:-}" ]]; then BENCH_ARGS+=(-ctk "q${KVQ}_0" -ctv "q${KVQ}_0" -fa on); fi
{ echo; echo "## 速さ（llama-bench -t $NP）"; } >> "$OUT"
if [[ -n "${MEM_GB:-}" ]]; then
  BENCH_CG=$(new_cgroup bench)
  if run_in_cgroup "$BENCH_CG" "$B/llama-bench" -m "$M" -t "$NP" -p 512 -n 128 -r 3 -o md "${BENCH_ARGS[@]}" >> "$OUT" 2>/dev/null; then :
  else echo "$MEM_GB GB で落ちた（llama-bench）" >> "$OUT"; fi
  cgroup_report "$BENCH_CG" llama-bench
else
  "$B/llama-bench" -m "$M" -t "$NP" -p 512 -n 128 -r 3 -o md "${BENCH_ARGS[@]}" >> "$OUT" 2>/dev/null
fi
# llama-bench は --override-kv を受け付けない（9/24）。専門家の数を変えた速さは 頭脳を立てた後の「探り」で測る
[[ -n "${EXPERTS:-}" ]] && echo "（上の llama-bench は 専門家 8人のまま。$EXPERTS 人の速さは 下の「探り」）" >> "$OUT"
log "速さ測った"

# 4.5 問題文の PPL（初回に一度作った文面は以後固定）
PPL_FILE="$K/monosashi/kousei.txt"
if [[ ! -f "$PPL_FILE" ]]; then
  python3 - "$K/monosashi" "$PPL_FILE" <<'PY'
import json, pathlib, sys
root, out = map(pathlib.Path, sys.argv[1:])
parts = []
for dan in range(7, 13):
    with (root / f"mondai_{dan}dan.jsonl").open(encoding="utf-8") as f:
        parts.extend(json.loads(line)["問"] for line in f if line.strip())
with (root / "mondai_gsm8k.jsonl").open(encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i == 200: break
        parts.append(json.loads(line)["question"])
out.write_text("\n".join(parts) + "\n", encoding="utf-8")
PY
fi
{ echo; echo '## PPL（llama-perplexity -c 512 --chunks 16）'; } >> "$OUT"
PPL_LOG="$W/perplexity.log"
if [[ -n "${MEM_GB:-}" ]]; then
  PPL_CG=$(new_cgroup perplexity)
  if run_in_cgroup "$PPL_CG" "$B/llama-perplexity" -m "$M" -f "$PPL_FILE" -c 512 --chunks 16 > "$PPL_LOG" 2>&1; then :
  else echo "$MEM_GB GB で落ちた（llama-perplexity）" >> "$OUT"; fi
  cgroup_report "$PPL_CG" llama-perplexity
else
  "$B/llama-perplexity" -m "$M" -f "$PPL_FILE" -c 512 --chunks 16 > "$PPL_LOG" 2>&1 || echo 'llama-perplexity failed' >> "$OUT"
fi
grep -E 'PPL' "$PPL_LOG" | tail -1 >> "$OUT" || echo 'PPL: 取れなかった' >> "$OUT"

# 5. 頭脳を立てて 7段の物差し（指定は kernel/server.py の local:main と同じ。-t だけ runner の数）
#    HENKA_FILE があれば 1行ずつ「名前|投機・KV の指定」を差し替えて同じ問題を測り、表にする（起動指定の比べ）
tateru(){ # $1=差し替える指定
  local ub_value=256; [[ -z "${UB:-}" ]] || ub_value="$UB"
  local fa_value=off; local -a kv_args=()
  if [[ -n "${KVQ:-}" ]]; then fa_value=on; kv_args=(-ctk "q${KVQ}_0" -ctv "q${KVQ}_0"); fi
  local -a server_args=("$B/llama-server" -m "$M" -t "$NP" -ngl 0 -dev none -c 8192 -np 1 -cb -ub "$ub_value" --cache-reuse 16 -fa "$fa_value" "${kv_args[@]}"
    --reasoning-format none)
  [[ -n "$LORA" ]] && server_args+=(--lora "$K/lora/tehon-lora.gguf")
  server_args+=("${OVERRIDE_ARGS[@]}"); read -r -a HENKA_ARGS <<< "$1"; server_args+=("${HENKA_ARGS[@]}" --host 127.0.0.1 --port 8080)
  if [[ -n "${MEM_GB:-}" ]]; then
    SERVER_CG=$(new_cgroup server)
    run_in_cgroup "$SERVER_CG" "${server_args[@]}" > "$W/llama.log" 2>&1 &
  else
    "${server_args[@]}" > "$W/llama.log" 2>&1 &
  fi
  P=$!
  SERVER_PID="$P"
  if [[ -n "$SERVER_CG" ]]; then
    for _ in $(seq 1 50); do SERVER_PID=$(sudo cat "$SERVER_CG/cgroup.procs" 2>/dev/null | head -1 || true); [[ -n "$SERVER_PID" ]] && break; sleep 0.1; done
  fi
  OK=""; for i in $(seq 1 200); do sleep 3; kill -0 $P 2>/dev/null || break
    curl -sf -m 3 http://127.0.0.1:8080/health 2>/dev/null | grep -q ok && { OK=1; break; }; done
  if [ -n "$OK" ]; then   # 探り: 同じ頼みで 128字書かせて 読み・書きの t/s を残す（専門家の数・メモリ上限の違いを比べる）
    grep -Ei 'compute buffer|KV (cache|buffer)' "$W/llama.log" >> "$OUT" || true
    curl -s -m 900 http://127.0.0.1:8080/completion -H 'Content-Type: application/json' \
      -d '{"prompt":"日本の四季について、それぞれの特徴を詳しく説明してください。","n_predict":128,"temperature":0}' \
      | python3 -c 'import json,sys; t=json.load(sys.stdin)["timings"]; print("探り: 読み %.1f t/s（%d字）・書き %.1f t/s（%d字）" % (t["prompt_per_second"], t["prompt_n"], t["predicted_per_second"], t["predicted_n"]))' >> "$OUT" 2>/dev/null || echo "探り: 取れなかった" >> "$OUT"
  fi
  [ -n "$OK" ] || { echo "頭脳が立たない"; tail -20 "$W/llama.log"; echo "頭脳が立たない: $1" >> "$OUT"; if [[ -n "$SERVER_CG" ]]; then cgroup_report "$SERVER_CG" llama-server; SERVER_CG=""; [[ -n "${MEM_GB:-}" ]] && echo "$MEM_GB GB で落ちた（llama-server 起動）" >> "$OUT"; fi; exit 1; }
}
hakaru(){ # $1=名札の付け足し
  python3 -u "$K/monosashi/hakaru.py" --mondai "$QF" ${BUBUN:+--bubun $BUBUN} --fukasa "$FUKASA" --kagiri "$KAGIRI" --narabi 1 \
    --nafuda "actions-$NAFUDA$1" --out "$K/kekka_actions/7dan_${NAFUDA}$1.json" > "$W/7dan$1.log" 2>&1 \
    || { tail -20 "$W/7dan$1.log" | tee -a "$OUT"; [[ -z "${MEM_GB:-}" ]] || echo "$MEM_GB GB で落ちた（物差し中）" >> "$OUT"; echo '```' >> "$OUT"; exit 1; }
}
export LLAMA_URL=http://127.0.0.1:8080
if [[ -n "${PPLONLY:-}" ]]; then
  tateru "--spec-type ngram-simple --spec-ngram-simple-size-m 16"
  kill "$SERVER_PID" 2>/dev/null || true; wait "$P" 2>/dev/null || true; P=""; SERVER_PID=""
  if [[ -n "$SERVER_CG" ]]; then cgroup_report "$SERVER_CG" llama-server; SERVER_CG=""; fi
elif [ -n "${HENKA_FILE:-}" ] && [ -f "$HENKA_FILE" ]; then
  { echo; echo "## 起動指定の比べ（7段 深さ${FUKASA} ${KAGIRI}問ずつ、同じ問題）"; echo "| 名前 | 指定 | 正解率 | 平均秒 |"; echo "|---|---|---|---|"; } >> "$OUT"
  while IFS='|' read -r NA SHITEI; do
    [ -n "$NA" ] || continue
    tateru "$SHITEI"; hakaru "_$NA"; kill "$SERVER_PID" 2>/dev/null || true; wait $P 2>/dev/null || true; P=""; SERVER_PID=""
    if [[ -n "$SERVER_CG" ]]; then cgroup_report "$SERVER_CG" llama-server; SERVER_CG=""; fi
    python3 - "$K/kekka_actions/7dan_${NAFUDA}_$NA.json" "$NA" "$SHITEI" >> "$OUT" <<'PY'
import json,sys; d=json.load(open(sys.argv[1])).get("まとめ", {}); print("| %s | `%s` | %s | %s |" % (sys.argv[2], sys.argv[3], d.get("正解率"), d.get("平均秒")))
PY
    log "$NA 測った"
  done < <(grep -v '^#' "$HENKA_FILE")
else
  tateru "--spec-type ngram-simple --spec-ngram-simple-size-m 16"
  { echo; echo "## 7段 深さ${FUKASA} ${KAGIRI}問（0=全部）"; echo '```'; } >> "$OUT"
  hakaru ""; { tail -12 "$W/7dan.log"; echo '```'; } >> "$OUT"
  kill "$SERVER_PID" 2>/dev/null || true; wait $P 2>/dev/null || true; P=""; SERVER_PID=""
  if [[ -n "$SERVER_CG" ]]; then cgroup_report "$SERVER_CG" llama-server; SERVER_CG=""; fi
fi
echo "所要 $(( $(date +%s) - T0 ))秒" >> "$OUT"; log "おわり"; cat "$OUT"
