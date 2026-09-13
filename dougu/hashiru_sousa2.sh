#!/bin/bash
# 操作の輪の課題（メモ・Safari・Finder）。画面を触るので、人がパソコンを使っていない時に。
# 手元のモデルは アプリが立てたもの（127.0.0.1:8080）を使い回す。2本目は立てない。
cd "$(dirname "$0")"; mkdir -p kekka
curl -sf -m 3 http://127.0.0.1:8080/health >/dev/null 2>&1 || {
  echo "手元のモデルが動いていません。カーネル.app を先に開いてください"; exit 2; }
echo "===== 操作の課題 $(date +%T) ====="
/usr/local/bin/python3 -u hakaru_sousa2.py 2>&1 | tee "kekka/sousa2_$(date +%m%d_%H%M).log"
echo "===== おわり $(date +%T) ====="
