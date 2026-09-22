#!/bin/bash
# GitHub Actions の走りが全部終わるのを待って、枝 kekka の結果（.md）を出す（公開 repo なので鍵なしで API を読める）。最長 6時間。
REPO=vhpctnyd5x-lab/localai-16gb; cd "$(dirname "$0")/.."
for i in $(seq 1 360); do
  S=$(curl -s "https://api.github.com/repos/$REPO/actions/runs?per_page=10" | python3 -c "
import json,sys; rs=json.load(sys.stdin)['workflow_runs']
ima=[r for r in rs if r['status']!='completed']
print(len(ima), ' '.join(r['head_branch'] for r in ima))" 2>/dev/null)
  case "$S" in 0*|"") break;; esac; sleep 60
done
echo "走り: 残り $S"
git fetch -q origin kekka 2>/dev/null && git log origin/kekka --oneline | head -5 && for f in $(git ls-tree --name-only origin/kekka kekka/ | grep '\.md$'); do echo "===== $f"; git show "origin/kekka:$f" | grep -v '^Writing\|^```$'; done
