#!/bin/bash
# Bonsai 2 27B（PrismML・3値 Qwen3.8-27B）を測る準備: フォークの llama.cpp を CPU 専用で build し、GGUF を落とす。
#   置き場: ~/LocalAI_mirror/llama-bonsai（源＋build）、~/LocalAI_mirror/models/Ternary-Bonsai-2-27B-PQ2_0.gguf（6.9GB）
#   素の llama.cpp では動かない（PQ2_0 / PTQ1_0 は独自型）。CPU は「動くが遅い」と README にある → まず測る。
export LANG=en_US.UTF-8
cd "$(dirname "$0")"; mkdir -p kekka
SRC="$HOME/LocalAI_mirror/llama-bonsai"; MD="$HOME/LocalAI_mirror/models"
GG="Ternary-Bonsai-2-27B-${1:-PQ2_0}.gguf"
echo "===== はじめ $(date +%T) ====="
# 1) 落とす（裏で）。途中で切れても -C - で続きから
( cd "$MD" && curl -L -C - --retry 5 -o "$GG" "https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf/resolve/main/$GG" \
    > "$OLDPWD/kekka/bonsai_dl.log" 2>&1; echo "落とし終わり $(date +%T) $(ls -la "$MD/$GG" | awk '{print $5}') bytes" ) &
DL=$!
# 2) フォークを build（CPU だけ。Metal は Intel Mac では使わない決まり -dev none）
if [ ! -d "$SRC/.git" ]; then git clone --depth 1 -b prism https://github.com/PrismML-Eng/llama.cpp "$SRC"; fi
cd "$SRC" && git log -1 --format='fork: %h %cd' 
cmake -B build -DGGML_METAL=OFF -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_TOOLS=ON -DLLAMA_BUILD_SERVER=ON -DCMAKE_BUILD_TYPE=Release > "$OLDPWD/kekka/bonsai_build.log" 2>&1 \
 && cmake --build build --target llama-server llama-bench llama-cli -j 4 >> "$OLDPWD/kekka/bonsai_build.log" 2>&1 \
 && echo "build 終わり $(date +%T): $(ls build/bin | tr '\n' ' ')" || echo "build 失敗 $(date +%T)（kekka/bonsai_build.log）"
wait $DL
echo "===== おわり $(date +%T) ====="
