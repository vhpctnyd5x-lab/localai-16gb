#!/bin/bash
# Codex CLI に審査させる（読み取り専用・既定 gpt-6-sol・high。CODEX_MODEL・CODEX_EFFORT で変える）。使い方: dougu/shinsa.sh <名> "<頼み>" → kekka/shinsa_<名>.md
cd "$(dirname "$0")/.."; mkdir -p dougu/kekka
NAME="$1"; shift
codex exec --skip-git-repo-check -m "${CODEX_MODEL:-gpt-6-sol}" -c model_reasoning_effort="${CODEX_EFFORT:-high}" -s read-only -C "$PWD" -o "dougu/kekka/shinsa_${NAME}.md" "$*" < /dev/null > "dougu/kekka/shinsa_${NAME}.log" 2>&1
echo "審査おわり $(date +%T) → dougu/kekka/shinsa_${NAME}.md"
