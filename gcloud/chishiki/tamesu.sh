#!/bin/bash
# 前で1本だけ実行。一時フォルダと一時の本番DBコピー以外は変更しない。
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PYTHON=${PYTHON:-python3}
bash -n "$HERE/hajimeru.sh" "$HERE/vm_startup.sh"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$HERE/tamesu.py"
