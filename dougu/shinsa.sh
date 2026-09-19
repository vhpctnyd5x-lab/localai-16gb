#!/bin/bash
# Codex CLI に審査させる（読み取り専用・gpt-5.6-terra・max）。使い方: dougu/shinsa.sh <名> "<頼み>" → kekka/shinsa_<名>.md
cd "$(dirname "$0")/.."; mkdir -p dougu/kekka
NAME="$1"; shift
codex exec -m gpt-5.6-terra -c model_reasoning_effort=max -s read-only -C "$PWD" -o "dougu/kekka/shinsa_${NAME}.md" "$*" > "dougu/kekka/shinsa_${NAME}.log" 2>&1
echo "審査おわり $(date +%T) → dougu/kekka/shinsa_${NAME}.md"
