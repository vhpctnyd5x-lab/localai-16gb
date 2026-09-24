#!/bin/bash
# 外の処理が終わるまで待って、結果を短く出す。Claude は必ず run_in_background で呼ぶ（終わると返事が戻る）。
# 使い方: dougu/matsu.sh actions   … GitHub Actions の走りが全部終わるまで。枝 kekka に増えた結果の正解率・秒を出す
#         dougu/matsu.sh gcp       … GCP の VM が 0台になるまで
#         dougu/matsu.sh pid N…    … Mac の処理が終わるまで
# 終わったら ~/.cache/claude-ura/<種類> の印を消す（印は hooks の ~/.claude/scripts/ura_guard.py が付ける）。最長 6時間。
REPO=vhpctnyd5x-lab/localai-16gb; cd "$(dirname "$0")/.."
SHU=${1:?actions / gcp / pid}; shift
HAJIME=$(date -u -r ~/.cache/claude-ura/"$SHU" +%FT%TZ 2>/dev/null || date -u +%FT%TZ)   # 印の時刻から
for i in $(seq 1 360); do
  case $SHU in
    actions) N=$(curl -s "https://api.github.com/repos/$REPO/actions/runs?per_page=20" | python3 -c "
import json,sys; print(sum(r['status']!='completed' for r in json.load(sys.stdin)['workflow_runs']))" 2>/dev/null);;
    gcp) N=$(gcloud compute instances list --format='value(name)' 2>/dev/null | wc -l | tr -d ' ');;
    pid) N=0; for p in "$@"; do kill -0 "$p" 2>/dev/null && N=$((N+1)); done;;
  esac
  [ "${N:-x}" = 0 ] && break; sleep 60
done
echo "$SHU: 残り ${N:-?}（$((i-1))分待った）"
rm -f ~/.cache/claude-ura/"$SHU"
if [ "$SHU" = actions ]; then
  git fetch -q origin kekka 2>/dev/null
  for f in $(git log origin/kekka --since="$HAJIME" --name-only --format= | grep '\.md$' | sort -u); do
    echo "$(basename "$f" .md): $(git show "origin/kekka:$f" | grep -m2 -E '"(正解率|平均秒)"' | tr -d ' \n')"
  done
fi
