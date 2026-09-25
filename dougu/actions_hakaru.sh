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
  KVK8V4=""; FA1=""; NOMMAP=""; MLOCK=""; SPD06=""
  KERNEL_KAZOERU=""; KERNEL_JIKAN=""; KERNEL_NARABE=""; KERNEL_ERABI=""
  KERNEL_HAYASA=""; KERNEL_KEISAN=""; KERNEL_TEHON=""; KERNEL_LORA=""; ATAMA=""
  BURE=""; SAMPLE_TEMP="0"; SAMPLE_TOP_P=""; SAMPLE_TOP_K=""; SAMPLE_SEED=""
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
  has kvk8v4 && KVK8V4=1; has fa1 && FA1=1; has nommap && NOMMAP=1; has mlock && MLOCK=1; has spd06 && SPD06=1
  if [[ "$b" =~ (^|-)bure([0-9]+)(-|$) ]]; then
    BURE="${BASH_REMATCH[2]}"; SAMPLE_TEMP="0.7"; SAMPLE_TOP_P="0.8"; SAMPLE_TOP_K="20"; SAMPLE_SEED="$BURE"
  fi
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
  printf 'UB=%s KVQ=%s JIKKEN=%s PPLONLY=%s KVK8V4=%s FA1=%s NOMMAP=%s MLOCK=%s SPD06=%s\n' "${UB:-}" "${KVQ:-}" "${JIKKEN:-}" "${PPLONLY:-}" "${KVK8V4:-}" "${FA1:-}" "${NOMMAP:-}" "${MLOCK:-}" "${SPD06:-}"
  printf 'BURE=%s SAMPLE_TEMP=%s SAMPLE_TOP_P=%s SAMPLE_TOP_K=%s SAMPLE_SEED=%s\n' "${BURE:-}" "${SAMPLE_TEMP:-0}" "${SAMPLE_TOP_P:-}" "${SAMPLE_TOP_K:-}" "${SAMPLE_SEED:-}"
  exit 0
fi
NAFUDA="${1:-$(uname -m)}"; REF_NAME="${GITHUB_REF_NAME:-hakaru}"
# hakaru* の枝だけ 枝の名から読む。hyou.yml（GSM8K の錨）は DAN・KERNEL_* を環境で渡すので そのまま使う（9/24 Claude）
if [[ "$REF_NAME" == hakaru* ]]; then parse_branch "$REF_NAME"; else DAN="${DAN:-7}"; KAGIRI="${KAGIRI:-0}"; EXPERTS=""; QUANT=""; MEM_GB=""; UB=""; KVQ=""; KVK8V4=""; FA1=""; NOMMAP=""; MLOCK=""; SPD06=""; JIKKEN="${JIKKEN:-}"; PPLONLY="${PPLONLY:-}"; HENKA_FILE="${HENKA_FILE:-}"; fi
# 道具の切り替えは hakaru.py が環境変数で読む。export しないと子に渡らない（9/24 道具が 1度も動かずに測っていた）
export KERNEL_KAZOERU KERNEL_JIKAN KERNEL_NARABE KERNEL_ERABI KERNEL_HAYASA KERNEL_KEISAN KERNEL_TEHON KERNEL_LORA
export KOUKAI_SAMPLE_TEMP="${SAMPLE_TEMP:-0}" KOUKAI_SAMPLE_TOP_P="${SAMPLE_TOP_P:-}" KOUKAI_SAMPLE_TOP_K="${SAMPLE_TOP_K:-}" KOUKAI_SAMPLE_SEED="${SAMPLE_SEED:-}"
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
    [[ "$line" =~ ^[[:space:]]*(#.*)?$ ]] && continue   # 説明の行と空行は読み飛ばす（9/24 base.env が止まった）
    if [[ "$line" =~ ^(KOUKAI_[A-Z_]+)=([A-Za-z0-9,._/-]+)$ ]]; then :
    elif [[ "$line" =~ ^(KOUKAI_QTT)=([A-Za-z0-9,._:/-]+)$ ]]; then :
    else echo "不正な実験設定: $JIKKEN_ENV:$line_no" >&2; exit 2; fi
    key="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"
    printf -v "$key" '%s' "$value"; export "$key"
  done < "$JIKKEN_ENV"
  if [[ -n "${KOUKAI_TRANSFORM:-}" ]]; then
    [[ "$KOUKAI_TRANSFORM" =~ ^[A-Za-z0-9_]+\.py$ && -f "$K/dougu/$KOUKAI_TRANSFORM" ]] || { echo "変換台本は dougu 内の .py を指定: $KOUKAI_TRANSFORM" >&2; exit 2; }
    TRANSFORM="$KOUKAI_TRANSFORM"
  fi
  if [[ "${KOUKAI_BI_DUMP:-}" == 1 ]]; then BI_DUMP_PATH=1; fi
  [[ -z "${KOUKAI_QTYPE:-}" || "${KOUKAI_QTYPE}" =~ ^[A-Za-z0-9_]+$ ]] || { echo "不正な KOUKAI_QTYPE" >&2; exit 2; }
  [[ -z "${KOUKAI_QOUT:-}" || "${KOUKAI_QOUT}" =~ ^[A-Za-z0-9_]+$ ]] || { echo "不正な KOUKAI_QOUT" >&2; exit 2; }
  [[ -z "${KOUKAI_QEMB:-}" || "${KOUKAI_QEMB}" =~ ^[A-Za-z0-9_]+$ ]] || { echo "不正な KOUKAI_QEMB" >&2; exit 2; }
  if [[ -n "${KOUKAI_QTT:-}" ]]; then
    [[ "$KOUKAI_QTT" =~ ^[A-Za-z0-9_.]+:[A-Za-z0-9_]+(,[A-Za-z0-9_.]+:[A-Za-z0-9_]+)*$ ]] || { echo "不正な KOUKAI_QTT" >&2; exit 2; }
  fi
  [[ -z "${KOUKAI_PRUNE_KEEP:-}" || "${KOUKAI_PRUNE_KEEP}" =~ ^[0-9]+$ ]] || { echo "不正な KOUKAI_PRUNE_KEEP" >&2; exit 2; }
  [[ -z "${KOUKAI_PRUNE_NEURONS:-}" || "${KOUKAI_PRUNE_NEURONS}" =~ ^(0(\.[0-8][0-9]*)?|0\.9(0*)?)$ ]] || { echo "KOUKAI_PRUNE_NEURONS は 0〜0.9" >&2; exit 2; }
  if [[ -n "${KOUKAI_PRUNE_NEURONS:-}" ]]; then
    [[ -n "${KOUKAI_QTYPE:-}" ]] || { echo "PRUNE_NEURONS は QTYPE が必要" >&2; exit 2; }
    [[ -f "$K/dougu/asshuku/prune_neurons.py" ]] || { echo "dougu/asshuku/prune_neurons.py がない" >&2; exit 2; }
  fi
  for key in KOUKAI_SWA_LAYERS KOUKAI_SWA_WINDOW KOUKAI_HEAD_MASK; do
    if [[ -n "${!key:-}" ]]; then
      grep -q "$key" "$K/llama_patch/koukai.patch" 2>/dev/null || { echo "$key を使うカーネル実装がない" >&2; exit 2; }
    fi
  done
  [[ -z "${KOUKAI_DROP_LAYERS:-}" || "${KOUKAI_DROP_LAYERS}" =~ ^[0-9]+(,[0-9]+)*$ ]] || { echo "不正な KOUKAI_DROP_LAYERS" >&2; exit 2; }
  if [[ -n "${KOUKAI_QOUT:-}${KOUKAI_QEMB:-}${KOUKAI_QTT:-}" && -z "${KOUKAI_QTYPE:-}" ]]; then
    echo "QOUT/QEMB/QTT は QTYPE（再量子化）が必要" >&2; exit 2
  fi
  if [[ -n "${KOUKAI_QTYPE:-}" && ( -n "${QUANT:-}" || "${ATAMA:-}" == 2507 ) ]]; then
    echo "QTYPE は -q / -m2507 と併用できない" >&2; exit 2
  fi
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
  REBUILD_QTYPE="${KOUKAI_QTYPE:-}"
  case "${QUANT:-}" in
    iq1s) MF=Qwen3-30B-A3B-UD-IQ1_S.gguf;; iq1m) MF=Qwen3-30B-A3B-UD-IQ1_M.gguf;;
    iq2xxs) MF=Qwen3-30B-A3B-UD-IQ2_XXS.gguf;; iq2m) MF=Qwen3-30B-A3B-UD-IQ2_M.gguf;;
    q2kxl) MF=Qwen3-30B-A3B-UD-Q2_K_XL.gguf;; *) MF=Qwen3-30B-A3B-Q2_K.gguf;;
  esac
  if [[ -n "$REBUILD_QTYPE" ]]; then
    SOURCE_MF=Qwen3-30B-A3B-Q8_0.gguf
    MF="Qwen3-30B-A3B-${REBUILD_QTYPE}.gguf"
  elif [[ -n "${QUANT:-}" ]]; then
    :
  fi
  if [[ -n "${REBUILD_QTYPE:-}" ]]; then
    HF_META=$(curl -fsSL "https://huggingface.co/api/models/$REPO/tree/$HF_REV?recursive=true&expand=true")
    HF_SHA=$(python3 -c 'import json,sys; rows=json.load(sys.stdin); row=next((x for x in rows if x.get("path")==sys.argv[1]), None); print(row["lfs"]["oid"] if row and row.get("lfs",{}).get("oid") else "")' "$SOURCE_MF" <<< "$HF_META")
    IMATRIX_SHA=$(python3 -c 'import json,sys; rows=json.load(sys.stdin); row=next((x for x in rows if x.get("path")=="imatrix_unsloth.dat"), None); print(row["lfs"]["oid"] if row and row.get("lfs",{}).get("oid") else "")' <<< "$HF_META")
    [[ "$HF_SHA" =~ ^[0-9a-f]{64}$ && "$IMATRIX_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "Q8_0 または imatrix の lfs.oid が取れない" >&2; exit 1; }
  elif [[ -n "${QUANT:-}" ]]; then
    HF_SHA=$(curl -fsSL "https://huggingface.co/api/models/$REPO/tree/$HF_REV?recursive=true&expand=true" | python3 -c 'import json,sys; name=sys.argv[1]; rows=json.load(sys.stdin); row=next((x for x in rows if x.get("path")==name), None); print(row["lfs"]["oid"] if row and row.get("lfs",{}).get("oid") else "")' "$MF")
    [[ "$HF_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "量子化ファイルの lfs.oid が取れない: $MF" >&2; exit 1; }
  else
    HF_SHA=db3ce897ccc9e7d9dbf17fe083cae7880a2092aa473b45eba8b77715aa9ca170
  fi
fi
if [[ -n "${REBUILD_QTYPE:-}" ]]; then M="$W/$SOURCE_MF"; else M="$W/$MF"; fi
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
[[ -n "${KVK8V4:-}" ]] && NAFUDA="${NAFUDA}_kvk8v4"
[[ -n "${FA1:-}" ]] && NAFUDA="${NAFUDA}_fa1"
[[ -n "${NOMMAP:-}" ]] && NAFUDA="${NAFUDA}_nommap"
[[ -n "${MLOCK:-}" ]] && NAFUDA="${NAFUDA}_mlock"
[[ -n "${SPD06:-}" ]] && NAFUDA="${NAFUDA}_spd06"
[[ -n "${PPLONLY:-}" ]] && NAFUDA="${NAFUDA}_pplonly"
[[ -z "${BURE:-}" ]] || NAFUDA="${NAFUDA}_bure${BURE}"
# ふるい（-pplonly）は x64 の 1台で足りる。ARM の台はすぐ終えて 同時 20台の枠を空ける（9/24）
if [[ -n "${PPLONLY:-}" && "$(uname -m)" == aarch64 ]]; then echo "ふるいは x64 だけで測る（ARM は飛ばす）"; exit 0; fi
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
NP=$(nproc); P=""; DL=""; DL_IMATRIX=""; DL_BASE=""
CGROOT="/sys/fs/cgroup/koukai-actions-$(id -u)-$$"; SERVER_CG=""; SERVER_PID=""
new_cgroup(){
  local name="$1"; local path="$CGROOT-$name-$$"   # 1つの local の中で name はまだ使えない（set -u で落ちた 9/24）
  sudo mkdir "$path"
  sudo sh -c 'echo "$1" > "$2/memory.max"; echo 0 > "$2/memory.swap.max"' sh "$((MEM_GB * 1024 * 1024 * 1024))" "$path"
  # 頭脳のファイルは 落としたときに 外の組で読み込み済み（ページキャッシュ）。空にしないと 上限の外で数えられる
  #（9/24 memory.peak 0.26GB・大きなページフォールト 2回で、8GB の絞りが効いていなかった）
  sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null
  printf '%s' "$path"
}
run_in_cgroup(){
  local path="$1" uid gid keep; shift; uid=$(id -u); gid=$(id -g)
  keep=$(compgen -e | grep '^KOUKAI_' | paste -sd, || true)
  local rc=0
  if [[ -n "$keep" ]]; then
    sudo --preserve-env="$keep" bash -c 'echo $$ > "$1/cgroup.procs"; shift; uid="$1"; gid="$2"; shift 2; exec setpriv --reuid="$uid" --regid="$gid" --init-groups -- "$@"' _ "$path" "$uid" "$gid" "$@" || rc=$?
  else
    sudo bash -c 'echo $$ > "$1/cgroup.procs"; shift; uid="$1"; gid="$2"; shift 2; exec setpriv --reuid="$uid" --regid="$gid" --init-groups -- "$@"' _ "$path" "$uid" "$gid" "$@" || rc=$?
  fi
  if (( rc == 137 )) && [[ "${MEM_GB:-}" == 8 ]]; then
    CG_KILLED=1
    [[ -z "${W:-}" ]] || : > "$W/cgroup-killed"
    echo '8GB に載らない（Killed、exit 137）' >> "$OUT"
    return 0
  fi
  return "$rc"
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
  kill $P $DL ${DL_IMATRIX:-} ${DL_BASE:-} 2>/dev/null || true
  [ -z "$P" ] || wait "$P" 2>/dev/null || true
  [ -z "$DL" ] || wait "$DL" 2>/dev/null || true
  [ -z "$DL_IMATRIX" ] || wait "$DL_IMATRIX" 2>/dev/null || true
  [ -z "$DL_BASE" ] || wait "$DL_BASE" 2>/dev/null || true
  [ -z "$SERVER_CG" ] || cgroup_report "$SERVER_CG" llama-server
}
trap cleanup EXIT
on_error(){
  local rc=$?; trap - ERR
  echo "失敗: exit=$rc 行=${BASH_LINENO[0]:-?} 命令=${BASH_COMMAND}" | tee -a "${OUT:-/dev/stderr}" >&2
  [[ -z "${W:-}" || ! -f "$W/llama.log" ]] || { echo 'llama-server の末尾:' >> "$OUT"; tail -30 "$W/llama.log" >> "$OUT"; }
  [[ -z "${W:-}" || ! -f "$W/perplexity.log" ]] || { echo 'llama-perplexity の末尾:' >> "$OUT"; tail -30 "$W/perplexity.log" >> "$OUT"; }
  exit "$rc"
}
trap on_error ERR
{ echo "# $NAFUDA  $(date -u +%FT%TZ)"; echo '```'
  echo "llama.cpp $COMMIT / koukai $(git rev-parse --short HEAD) / 問題 $(sha256sum "$QF" | cut -c1-12) / 頭脳 ${HF_SHA:0:12}"
  [[ -z "${PATCH_SHA:-}" ]] || echo "llama patch sha256 ${PATCH_SHA:0:12}"
  [[ -z "${JIKKEN:-}" ]] || echo "実験 $JIKKEN_ENV"
  [[ -z "$TRANSFORM" ]] || echo "変換 $TRANSFORM"
  [[ -z "$BI_DUMP_PATH" ]] || echo "BI dump $BI_DUMP_PATH"
  [[ -z "$VOCAB_KEEP_PATH" ]] || echo "vocab keep $VOCAB_KEEP_PATH"
  [[ -z "${EXPERTS:-}" ]] || echo "専門家数 $EXPERTS"
  [[ -z "${MEM_GB:-}" ]] || echo "メモリ上限 ${MEM_GB} GB（swap なし、mmap ページキャッシュを含む）"
  if [[ -n "${BURE:-}" ]]; then echo "生成設定 temperature=$SAMPLE_TEMP top_p=$SAMPLE_TOP_P top_k=$SAMPLE_TOP_K seed=$SAMPLE_SEED"; else echo '生成設定 temperature=0'; fi
  echo "runner $(grep -m1 VERSION= /etc/os-release | cut -d= -f2) $(gcc --version | head -1)"
  echo "cores $NP"; grep -m1 -i 'model name' /proc/cpuinfo || lscpu | grep -i 'model name\|vendor' | head -2
  free -g | head -2; df -h / | tail -1; echo '```'; } > "$OUT"

# 1. 盤の空きを確かめる
FREE=$(df -B1 --output=avail / | tail -1)
NEED_GB=15; [[ -z "${REBUILD_QTYPE:-}" ]] || NEED_GB=55
[ "$FREE" -gt $((NEED_GB*1024*1024*1024)) ] || { echo "盤が足りない（${NEED_GB}GiB 必要）: $FREE" >> "$OUT"; exit 1; }

# 2. 頭脳を落とす（作りながら並行。途中から再開できる .part → sha256 が合ったら名前を変える）
( curl -fsSL -C - --retry 5 --retry-delay 10 --retry-all-errors -o "$M.part" \
  "https://huggingface.co/$REPO/resolve/$HF_REV/${SOURCE_MF:-$MF}" ) &
DL=$!
BASE_M=""
if [[ -n "${REBUILD_QTYPE:-}" ]]; then
  BASE_M="$W/base-Q2_K.gguf"
  ( curl -fsSL -C - --retry 5 --retry-delay 10 --retry-all-errors -o "$BASE_M.part" \
    "https://huggingface.co/unsloth/Qwen3-30B-A3B-GGUF/resolve/d5b1d57bd0b504ac62ae6c725904e96ef228dc74/Qwen3-30B-A3B-Q2_K.gguf" ) &
  DL_BASE=$!
else DL_BASE=""; fi
if [[ -n "${REBUILD_QTYPE:-}" ]]; then
  IMATRIX="$W/imatrix_unsloth.dat"
  ( curl -fsSL -C - --retry 5 --retry-delay 10 --retry-all-errors -o "$IMATRIX.part" \
    "https://huggingface.co/$REPO/resolve/$HF_REV/imatrix_unsloth.dat" ) &
  DL_IMATRIX=$!
else DL_IMATRIX=""; fi

# 3. llama.cpp を手元と同じ commit で作る
git clone -q --filter=blob:none https://github.com/ggml-org/llama.cpp "$W/llama.cpp"
git -C "$W/llama.cpp" checkout -q "$COMMIT"
if [[ -f "$K/llama_patch/koukai.patch" ]]; then
  git -C "$W/llama.cpp" apply "$K/llama_patch/koukai.patch"
fi
cmake -S "$W/llama.cpp" -B "$W/build" -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF >/dev/null
TARGETS=(llama-server llama-bench llama-perplexity); [[ -z "${REBUILD_QTYPE:-}" ]] || TARGETS+=(llama-quantize)
cmake --build "$W/build" -j"$NP" --target "${TARGETS[@]}" >/dev/null
B="$W/build/bin"; log "作った"
PYTHON="$W/venv/bin/python"
if [[ -n "${KOUKAI_TRANSFORM:-}" || ( -n "${KOUKAI_PRUNE_NEURONS:-}" && ! "${KOUKAI_PRUNE_NEURONS}" =~ ^0(\.0*)?$ ) ]]; then
  python3 -m venv "$W/venv"
  "$PYTHON" -m pip install --disable-pip-version-check numpy
  "$PYTHON" -m pip install --disable-pip-version-check "$W/llama.cpp/gguf-py"
  PYTHONPATH="$W/llama.cpp/gguf-py${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" -c 'import numpy, gguf; print("変換依存 numpy / llama.cpp gguf-py OK")'
fi
MMAP_ARGS=(); [[ -z "${NOMMAP:-}" ]] || MMAP_ARGS+=(--no-mmap)
[[ -z "${MLOCK:-}" ]] || MMAP_ARGS+=(--mlock)
if [[ -n "${SPD06:-}" ]]; then
  DRAFT_REPO=Qwen/Qwen3-0.6B-GGUF; DRAFT_MF=Qwen3-0.6B-Q8_0.gguf
  DRAFT_REV=$(curl -fsSL "https://huggingface.co/api/models/$DRAFT_REPO" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
  [[ "$DRAFT_REV" =~ ^[0-9a-f]{40}$ ]] || { echo "草稿 revision が取れない" >&2; exit 1; }
  DRAFT_SHA=$(curl -fsSL "https://huggingface.co/api/models/$DRAFT_REPO/tree/$DRAFT_REV?recursive=true&expand=true" | python3 -c 'import json,sys; rows=json.load(sys.stdin); name=sys.argv[1]; row=next((x for x in rows if x.get("path")==name), None); print(row.get("lfs",{}).get("oid", "") if row else "")' "$DRAFT_MF")
  [[ "$DRAFT_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "草稿 lfs.oid が取れない" >&2; exit 1; }
  DRAFT_M="$W/$DRAFT_MF"
  curl -fsSL -C - --retry 5 --retry-delay 10 --retry-all-errors -o "$DRAFT_M.part" "https://huggingface.co/$DRAFT_REPO/resolve/$DRAFT_REV/$DRAFT_MF"
  echo "$DRAFT_SHA  $DRAFT_M.part" | sha256sum -c --quiet || { echo "草稿の sha256 が違う" >&2; exit 1; }
  mv "$DRAFT_M.part" "$DRAFT_M"
  SERVER_HELP=$("$B/llama-server" --help 2>&1)
  grep -q -- '-md' <<< "$SERVER_HELP" || { echo '草稿指定に未対応: -md' >&2; exit 1; }
  grep -q -- '--spec-draft-n-max' <<< "$SERVER_HELP" || { echo '草稿指定に未対応: --spec-draft-n-max' >&2; exit 1; }
  SPEC_ARGS=(-md "$DRAFT_M" --spec-draft-n-max 8)
  if grep -q -- '--spec-type' <<< "$SERVER_HELP" && grep -q -- 'ngram-simple' <<< "$SERVER_HELP"; then
    if grep -q -- 'comma-separated list of types' <<< "$SERVER_HELP" && grep -q -- 'draft-simple' <<< "$SERVER_HELP"; then
      SPEC_ARGS+=(--spec-type draft-simple,ngram-simple --spec-ngram-simple-size-m 16)
    else
      SPEC_ARGS+=(--spec-type draft-simple)
    fi
  fi
  echo "草稿 $DRAFT_REV / sha256 ${DRAFT_SHA:0:12} / 指定 ${SPEC_ARGS[*]}" >> "$OUT"
else SPEC_ARGS=(--spec-type ngram-simple --spec-ngram-simple-size-m 16); fi
wait $DL; DL=""
echo "$HF_SHA  $M.part" | sha256sum -c --quiet || { echo "頭脳の sha256 が違う" >> "$OUT"; exit 1; }
mv "$M.part" "$M"; log "頭脳 $(du -h "$M" | cut -f1) 落とした（lfs.oid sha256 一致）"
if [[ -n "$DL_BASE" ]]; then
  wait "$DL_BASE"; DL_BASE=""
  echo "db3ce897ccc9e7d9dbf17fe083cae7880a2092aa473b45eba8b77715aa9ca170  $BASE_M.part" | sha256sum -c --quiet || { echo "基準頭脳 Q2_K の sha256 が違う" >> "$OUT"; exit 1; }
  mv "$BASE_M.part" "$BASE_M"
fi
# 改造前の同じ頭脳を同じ runner で測る。KOUKAI_* は外して既定動作に戻す。
COMPARE_BASELINE=0
[[ -n "${JIKKEN:-}${QUANT:-}${EXPERTS:-}${MEM_GB:-}${UB:-}${KVQ:-}${KVK8V4:-}${FA1:-}${NOMMAP:-}${MLOCK:-}${SPD06:-}" ]] && COMPARE_BASELINE=1
if (( COMPARE_BASELINE )); then
  [[ -n "$BASE_M" ]] || BASE_M="$M"
  BASE_ENV=(env); while IFS= read -r key; do BASE_ENV+=(-u "$key"); done < <(compgen -e | grep '^KOUKAI_' || true)
  echo; echo '## 基準（同じ機械）pp512 / tg128' >> "$OUT"
  if ! "${BASE_ENV[@]}" "$B/llama-bench" -m "$BASE_M" -t "$NP" -p 512 -n 128 -r 3 -o md > "$W/baseline-bench.md" 2>&1; then
    cat "$W/baseline-bench.md" >> "$OUT"; echo '基準 llama-bench 失敗' >> "$OUT"; exit 1
  fi
  cat "$W/baseline-bench.md" >> "$OUT"
  BASE_PP=$(sed -nE 's/.*pp512[^|]*\|[[:space:]]*([0-9.]+).*/\1/p' "$W/baseline-bench.md" | head -1)
  BASE_TG=$(sed -nE 's/.*tg128[^|]*\|[[:space:]]*([0-9.]+).*/\1/p' "$W/baseline-bench.md" | head -1)
fi
if [[ -n "${REBUILD_QTYPE:-}" ]]; then
  wait "$DL_IMATRIX"; DL_IMATRIX=""
  echo "$IMATRIX_SHA  $IMATRIX.part" | sha256sum -c --quiet || { echo "imatrix の sha256 が違う" >> "$OUT"; exit 1; }
  mv "$IMATRIX.part" "$IMATRIX"
  if [[ -n "${KOUKAI_PRUNE_NEURONS:-}" && ! "${KOUKAI_PRUNE_NEURONS}" =~ ^0(\.0*)?$ ]]; then
    PRUNED_M="$W/pruned_q8.gguf"; PRUNED_IMATRIX="$W/pruned_imatrix.dat"
    PRUNE_TIME="$W/prune-time.log"; TIMEV=(); [[ -x /usr/bin/time ]] && TIMEV=(/usr/bin/time -v)   # time が無い runner でも止めない
    if PYTHONPATH="$W/llama.cpp/gguf-py${PYTHONPATH:+:$PYTHONPATH}" "${TIMEV[@]}" "$PYTHON" "$K/dougu/asshuku/prune_neurons.py" --imatrix "$IMATRIX" --imatrix-out "$PRUNED_IMATRIX" --frac "$KOUKAI_PRUNE_NEURONS" "$M" "$PRUNED_M" 2> "$PRUNE_TIME"; then
      :
    else
      rc=$?; cat "$PRUNE_TIME" >> "$OUT"; exit "$rc"
    fi
    awk '/Maximum resident set size \(kbytes\):/ {printf "剪定の最大メモリ: %.2f GiB（%s KiB）\n", $NF / 1048576, $NF}' "$PRUNE_TIME" >> "$OUT"
    rm -f "$M" "$IMATRIX"; M="$PRUNED_M"; IMATRIX="$PRUNED_IMATRIX"
    echo "ニューロン剪定 ${KOUKAI_PRUNE_NEURONS}: $(du -h "$M" | cut -f1)" >> "$OUT"
  fi
  QARGS=(--allow-requantize --imatrix "$IMATRIX")
  [[ -z "${KOUKAI_QOUT:-}" ]] || QARGS+=(--output-tensor-type "$KOUKAI_QOUT")
  [[ -z "${KOUKAI_QEMB:-}" ]] || QARGS+=(--token-embedding-type "$KOUKAI_QEMB")
  if [[ -n "${KOUKAI_QTT:-}" ]]; then
    IFS=',' read -ra QTT_ITEMS <<< "$KOUKAI_QTT"
    for item in "${QTT_ITEMS[@]}"; do QARGS+=(--tensor-type "${item/:/=}"); done
  fi
  FINAL_M="$W/$MF"
  QUANT_T0=$(date +%s)
  "$B/llama-quantize" "${QARGS[@]}" "$M" "$FINAL_M" "$REBUILD_QTYPE"
  echo "作り直し: ${REBUILD_QTYPE} / $(du -h "$FINAL_M" | cut -f1) / 所要 $(( $(date +%s) - QUANT_T0 ))秒" >> "$OUT"
  rm -f "$M" "$IMATRIX"; M="$FINAL_M"; log "Q8_0 と imatrix を消去"
fi
if [[ -n "${KOUKAI_PRUNE_KEEP:-}" ]]; then
  NEXT_M="$W/prune_experts.gguf"
  python3 "$K/dougu/asshuku/prune_experts.py" --in "$M" --out "$NEXT_M" --scores "$K/dougu/jikken/keep_fair_jce.tsv" --keep "$KOUKAI_PRUNE_KEEP"
  echo "専門家を ${KOUKAI_PRUNE_KEEP} 個に手術: $(du -h "$NEXT_M" | cut -f1)" >> "$OUT"
  rm -f "$M"; M="$NEXT_M"
fi
if [[ -n "${KOUKAI_DROP_LAYERS:-}" ]]; then
  NEXT_M="$W/prune_layers.gguf"
  python3 "$K/dougu/asshuku/prune_layers.py" --in "$M" --out "$NEXT_M" --drop "$KOUKAI_DROP_LAYERS"
  echo "層 ${KOUKAI_DROP_LAYERS} を手術: $(du -h "$NEXT_M" | cut -f1)" >> "$OUT"
  rm -f "$M"; M="$NEXT_M"
fi
if [[ -n "$TRANSFORM" ]]; then
  NEW_M="$W/transform_${JIKKEN}.gguf"
  PYTHONPATH="$W/llama.cpp/gguf-py${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" "$K/dougu/$TRANSFORM" "$M" "$NEW_M"
  rm -f "$M"; M="$NEW_M"; log "変換済み頭脳を使う: $TRANSFORM"
fi

# 4. 速さ（読み込み pp512・書き出し tg128、3回）
OVERRIDE_ARGS=(); [[ -n "${EXPERTS:-}" ]] && OVERRIDE_ARGS+=(--override-kv "qwen3moe.expert_used_count=int:$EXPERTS")
BENCH_ARGS=(); [[ -z "${NOMMAP:-}" ]] || BENCH_ARGS+=(-mmp 0)
[[ -n "${UB:-}" ]] && BENCH_ARGS+=(-ub "$UB")
if [[ -n "${KVQ:-}" ]]; then BENCH_ARGS+=(-ctk "q${KVQ}_0" -ctv "q${KVQ}_0" -fa on); fi
[[ -z "${KVK8V4:-}" ]] || BENCH_ARGS+=(-ctk q8_0 -ctv q4_0 -fa on)
[[ -z "${FA1:-}" ]] || BENCH_ARGS+=(-fa on)
{ echo; echo "## 速さ（llama-bench -t $NP）"; } >> "$OUT"
[[ -z "${MLOCK:-}" ]] || echo 'llama-bench は mlock 非対応。速さは 探り（llama-server）で' >> "$OUT"
BENCH_OUT="$W/experiment-bench.md"
bench_with_trace(){
  local rc; if "$@" > "$BENCH_OUT" 2>&1; then cat "$BENCH_OUT" >> "$OUT"; return 0; else rc=$?; cat "$BENCH_OUT" >> "$OUT"; echo "llama-bench 失敗: exit=$rc" >> "$OUT"; fi
  if (( rc == 139 )); then
    if ! command -v gdb >/dev/null 2>&1; then sudo apt-get update -qq && sudo apt-get install -y -qq gdb; fi
    if command -v gdb >/dev/null 2>&1; then
      echo '## 逆追跡（gdb）' >> "$OUT"
      if [[ "$1" == run_in_cgroup ]]; then gdb -batch -ex run -ex bt --args "${@:3}" >> "$OUT" 2>&1 || true
      else gdb -batch -ex run -ex bt --args "$@" >> "$OUT" 2>&1 || true; fi
    else echo '逆追跡できず: gdb を導入できなかった' >> "$OUT"; fi
  fi
  return "$rc"
}
if [[ -n "${MEM_GB:-}" ]]; then
  BENCH_CG=$(new_cgroup bench)
  if ! bench_with_trace run_in_cgroup "$BENCH_CG" "$B/llama-bench" -m "$M" -t "$NP" -p 512 -n 128 -r 3 -o md "${BENCH_ARGS[@]}"; then echo "$MEM_GB GB で落ちた（llama-bench）" >> "$OUT"; fi
  cgroup_report "$BENCH_CG" llama-bench
else
  bench_with_trace "$B/llama-bench" -m "$M" -t "$NP" -p 512 -n 128 -r 3 -o md "${BENCH_ARGS[@]}" || true
fi
if (( COMPARE_BASELINE )); then
  EXP_PP=$(sed -nE 's/.*pp512[^|]*\|[[:space:]]*([0-9.]+).*/\1/p' "$BENCH_OUT" | head -1)
  EXP_TG=$(sed -nE 's/.*tg128[^|]*\|[[:space:]]*([0-9.]+).*/\1/p' "$BENCH_OUT" | head -1)
  python3 - "$BASE_PP" "$BASE_TG" "$EXP_PP" "$EXP_TG" >> "$OUT" <<'PY'
import sys
base_pp,base_tg,exp_pp,exp_tg=sys.argv[1:]
for label,b,e in [('pp512',base_pp,exp_pp),('tg128',base_tg,exp_tg)]:
    if b and e and float(b): print(f'基準比 {label}: {float(e)/float(b):.3f}（実験 / 基準）')
    else: print(f'基準比 {label}: 算出できず（ベンチ値不足）')
PY
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
        d = json.loads(line); parts.append(d.get("question") or d.get("問"))   # 手元の GSM8K は「問」（9/24 KeyError で全部止まった）
out.write_text("\n".join(parts) + "\n", encoding="utf-8")
PY
fi
{ echo; echo '## PPL（llama-perplexity -c 512 --chunks 16）'; } >> "$OUT"
PPL_LOG="$W/perplexity.log"
PPL_ARGS=( -ctk f16 -ctv f16 ); [[ -n "${KVQ:-}" ]] && PPL_ARGS=( -ctk "q${KVQ}_0" -ctv "q${KVQ}_0" -fa on )
[[ -z "${KVK8V4:-}" ]] || PPL_ARGS=( -ctk q8_0 -ctv q4_0 -fa on )
[[ -z "${FA1:-}" ]] || PPL_ARGS+=( -fa on )
if [[ -n "${MEM_GB:-}" ]]; then
  PPL_CG=$(new_cgroup perplexity)
  if run_in_cgroup "$PPL_CG" "$B/llama-perplexity" -m "$M" -f "$PPL_FILE" -c 512 --chunks 16 "${PPL_ARGS[@]}" "${MMAP_ARGS[@]}" > "$PPL_LOG" 2>&1; then :
  else echo "$MEM_GB GB で落ちた（llama-perplexity）" >> "$OUT"; tail -20 "$PPL_LOG" >> "$OUT"; fi
  cgroup_report "$PPL_CG" llama-perplexity
else
  "$B/llama-perplexity" -m "$M" -f "$PPL_FILE" -c 512 --chunks 16 "${PPL_ARGS[@]}" "${MMAP_ARGS[@]}" > "$PPL_LOG" 2>&1 || { echo 'llama-perplexity failed' >> "$OUT"; tail -20 "$PPL_LOG" >> "$OUT"; }
fi
grep -E 'PPL' "$PPL_LOG" | tail -1 >> "$OUT" || echo 'PPL: 取れなかった' >> "$OUT"

# 5. 頭脳を立てて 7段の物差し（指定は kernel/server.py の local:main と同じ。-t だけ runner の数）
#    HENKA_FILE があれば 1行ずつ「名前|投機・KV の指定」を差し替えて同じ問題を測り、表にする（起動指定の比べ）
tateru(){ # $1=差し替える指定
  local ub_value=256; [[ -z "${UB:-}" ]] || ub_value="$UB"
  local fa_value=off; local -a kv_args=()
  if [[ -n "${KVQ:-}" ]]; then fa_value=on; kv_args=(-ctk "q${KVQ}_0" -ctv "q${KVQ}_0"); fi
  if [[ -n "${KVK8V4:-}" ]]; then fa_value=on; kv_args=(-ctk q8_0 -ctv q4_0); fi
  [[ -z "${FA1:-}" ]] || fa_value=on
  local -a server_args=("$B/llama-server" -m "$M" -t "$NP" -ngl 0 -dev none -c 8192 -np 1 -cb -ub "$ub_value" --cache-reuse 16 -fa "$fa_value" "${kv_args[@]}" "${MMAP_ARGS[@]}"
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
  if [[ -n "${CG_KILLED:-}" || -e "$W/cgroup-killed" ]]; then
    echo '8GB に載らない（Killed）'; [[ -z "$SERVER_CG" ]] || { cgroup_report "$SERVER_CG" llama-server; SERVER_CG=""; }; exit 0
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
  tateru "${SPEC_ARGS[*]}"
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
  tateru "${SPEC_ARGS[*]}"
  { echo; echo "## 7段 深さ${FUKASA} ${KAGIRI}問（0=全部）"; echo '```'; } >> "$OUT"
  hakaru ""; { tail -12 "$W/7dan.log"; echo '```'; } >> "$OUT"
  kill "$SERVER_PID" 2>/dev/null || true; wait $P 2>/dev/null || true; P=""; SERVER_PID=""
  if [[ -n "$SERVER_CG" ]]; then cgroup_report "$SERVER_CG" llama-server; SERVER_CG=""; fi
fi
echo "所要 $(( $(date +%s) - T0 ))秒" >> "$OUT"; log "おわり"; cat "$OUT"
