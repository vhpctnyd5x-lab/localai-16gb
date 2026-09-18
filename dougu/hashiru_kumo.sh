#!/bin/bash
export LANG=en_US.UTF-8
# 雲の先生を同じ物差しで測る（7段 128問・120問）。鍵は台本が env から読む。
cd "$(dirname "$0")"; mkdir -p kekka
for s in groq:openai/gpt-oss-120b nvidia:fast nvidia:super; do
  for m in ../monosashi/mondai_7dan.jsonl ../monosashi/mondai.jsonl; do
    /usr/local/bin/python3 hakaru_kumo.py --sensei "$s" --mondai "$m" --narabi 2 2>&1 | grep -E "=====|正答|落とした|しくじり例"
  done
done
echo "===== おわり $(date +%T) ====="
