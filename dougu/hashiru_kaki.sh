#!/bin/bash
export LANG=en_US.UTF-8
# 手元のモデルの「書き出し」の速さを、起動の指定ごとに測る。画面は使わない。20分ほど。
cd "$(dirname "$0")"; mkdir -p kekka
pgrep -f llama-server >/dev/null && { echo "llama-server がもう動いています。カーネル.app を閉じてから"; exit 2; }
caffeinate -i /usr/local/bin/python3 -u hakaru_kaki.py "$@" 2>&1 | tee "kekka/kaki_$(date +%m%d_%H%M).log"
