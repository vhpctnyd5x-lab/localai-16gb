#!/bin/bash
export LANG=en_US.UTF-8
# 手元のモデルの「読み込み」の速さを、起動の指定ごとに測る。画面は使わない。1時間ほど。
# モデルは 8090 で自分で立てて消す。カーネル.app（8080）が動いていると始めない（1本だけの決まり）。
cd "$(dirname "$0")"; mkdir -p kekka
pgrep -f llama-server >/dev/null && { echo "llama-server がもう動いています。カーネル.app を閉じてから"; exit 2; }
caffeinate -i /usr/local/bin/python3 -u hakaru_yomi.py "$@" 2>&1 | tee "kekka/yomi_$(date +%m%d_%H%M).log"
