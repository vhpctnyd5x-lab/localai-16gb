#!/bin/bash
# 例: bash dougu/jikken_hashiru.sh sa8 rf16 -d11-k-j-n-s
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ $# -ge 1 ]] || { echo "使い方: bash dougu/jikken_hashiru.sh 名前... [枝の追加指定]" >&2; exit 2; }
names=(); suffix=""
for arg in "$@"; do
  if [[ "$arg" == -* ]]; then suffix="$suffix$arg"
  else
    [[ -z "$suffix" && "$arg" =~ ^[A-Za-z0-9_]+$ ]] || { echo "不正な実験名または引数順: $arg" >&2; exit 2; }
    [[ -f "dougu/jikken/$arg.env" ]] || { echo "env がありません: $arg" >&2; exit 2; }
    names+=("$arg")
  fi
done
[[ ${#names[@]} -gt 0 ]] || { echo "実験名がありません" >&2; exit 2; }
[[ -z "$suffix" || "$suffix" =~ ^(-[A-Za-z0-9]+)+$ ]] || { echo "不正な枝指定: $suffix" >&2; exit 2; }
for name in "${names[@]}"; do
  branch="hakaru-zenbu-pplonly-x${name}${suffix}"
  echo "push: main:$branch"
  git push -f origin "main:$branch"
done
