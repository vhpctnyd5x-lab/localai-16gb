#!/bin/bash
# GitHub Actions の走りが終わるのを待って、枝 kekka の結果を出す（公開 repo なので鍵なしで API を読める）。最長 3時間。
REPO=vhpctnyd5x-lab/localai-16gb; cd "$(dirname "$0")/.."
for i in $(seq 1 180); do
  J=$(curl -s "https://api.github.com/repos/$REPO/actions/runs?per_page=1")
  S=$(printf '%s' "$J" | python3 -c "import json,sys; r=json.load(sys.stdin)['workflow_runs'][0]; print(r['status'], r['conclusion'], r['html_url'])" 2>/dev/null)
  case "$S" in completed*) break;; esac; sleep 60
done
echo "走り: $S"
git fetch -q origin kekka 2>/dev/null && git show origin/kekka --stat --oneline | head -5 && for f in $(git ls-tree --name-only origin/kekka kekka/ | grep '\.md$'); do echo "===== $f"; git show "origin/kekka:$f"; done
