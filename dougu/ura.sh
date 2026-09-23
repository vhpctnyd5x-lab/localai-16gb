#!/bin/bash
# 裏で動いているこの仕事場の処理を一覧（隠れた処理を残さない）。使い方: dougu/ura.sh [止める]
P='tsukuru_|llama-server|codex exec|hakaru\.py|hashiru_|actions_matsu'
ps -axo pid,etime,command | grep -E "$P" | grep -v -E "grep|caffeinate|ura\.sh" | cut -c1-120 || true
N=$(ps -axo command | grep -E "$P" | grep -v -E "grep|caffeinate|ura\.sh" | wc -l | tr -d ' ')
echo "── 裏の処理 $N 件"
if [ "${1:-}" = 止める ] && [ "$N" != 0 ]; then pkill -f "$P"; sleep 1; echo "止めた"; fi
