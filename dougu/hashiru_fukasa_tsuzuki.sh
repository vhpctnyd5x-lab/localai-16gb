#!/bin/bash
# 深さの測定の続き（9/17）: 深さ1 の残り → 難しい6段を 深さ1・2。おまかせ(-1) は f0/f1/f2 の1問ごとの結果から机上で出す（決め方が決定的なので同じ）。
cd "$(dirname "$0")"
./hashiru_fukasa120.sh 1
./hashiru_fukasa120.sh 1 2 --mondai ../monosashi/mondai_6dan.jsonl
