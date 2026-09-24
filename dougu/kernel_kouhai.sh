#!/bin/bash
# カーネル（~/LocalAI_mirror/kernel）の コードだけ を 公開用に koukai/kernel/ へ写す（2026-09-24 本人:「カーネルも GitHub に出しておいて」）。
# 出すのは *.py と tests/*.py だけ。記録（kiroku）・状態の json・集めた文章（corpus）・ログ・辞書データ・.claude は出さない。
# 秘密の検査で 1件でも当たれば 写さずに止まる。Mac のユーザー名は伏せる。push は この後 git で。
set -euo pipefail
SRC=~/LocalAI_mirror/kernel; DST="$(cd "$(dirname "$0")/.." && pwd)/kernel"
python3 - "$SRC" <<'PY'
import glob, os, re, sys
src = sys.argv[1]
files = sorted(glob.glob(os.path.join(src, "*.py")) + glob.glob(os.path.join(src, "tests", "*.py")))
pat = re.compile(r"(gsk_[A-Za-z0-9]{10,}|nvapi-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|xox[bp]-|-----BEGIN [A-Z ]*PRIVATE|hf_[A-Za-z0-9]{20,}"
                 r"|(api_key|apikey|token|secret|password|passwd)\s*=\s*[\"'][^\"'\s]{12,}[\"']|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}|0[789]0-?\d{4}-?\d{4})")
bad = [f"{f}:{i}" for f in files for i, l in enumerate(open(f, encoding="utf-8", errors="replace"), 1) if pat.search(l)]
big = [f for f in files if os.path.getsize(f) > 400_000]
if bad or big:
    print("止めた（秘密らしき行 / 大きすぎるファイル）:", bad[:10], big); sys.exit(1)
print("検査 OK", len(files), "本")
PY
rm -rf "$DST"; mkdir -p "$DST/tests"
cp "$SRC"/*.py "$DST/"; cp "$SRC"/tests/*.py "$DST/tests/" 2>/dev/null || true
LC_ALL=C sed -i '' "s/$(id -un)/<user>/g" "$DST"/*.py "$DST"/tests/*.py
! grep -rq "$(id -un)" "$DST" || { echo "ユーザー名が残った"; exit 1; }
[ -f "$(dirname "$0")/kernel_README.md" ] && cp "$(dirname "$0")/kernel_README.md" "$DST/README.md"
echo "写した: $(ls "$DST"/*.py | wc -l | tr -d ' ') 本 → $DST"
