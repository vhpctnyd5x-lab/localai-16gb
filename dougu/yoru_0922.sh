#!/bin/bash
# 9/22 の連続測定（Mac、1本ずつ）: ① m16 vs 元 16問 ② 35B imatrix 128問
cd "$(dirname "$0")"
./hashiru_imatrix.sh Qwen3-30B-A3B-Q2_K 16 _m16 --spec-type ngram-simple --spec-ngram-simple-size-m 16
./hashiru_imatrix.sh Qwen3-30B-A3B-Q2_K 16 _moto --spec-type ngram-simple
./hashiru_imatrix.sh Qwen3.5-35B-A3B-Q2_K-imatrix 0
