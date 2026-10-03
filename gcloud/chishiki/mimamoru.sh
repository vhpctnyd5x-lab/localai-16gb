#!/bin/bash
# hajimeru.sh が起動した VM を見張る。止められても何も消さない（もう一度呼べば続きから見る）。
# 完成・失敗・VM消失のどれかで、VM が消えたのを確かめてから この実行専用の SA と IAM を片付ける。
# 使い方: bash mimamoru.sh ~/.cache/chishiki-gcp/<RUN_ID>.env [最長分=110]
set -uo pipefail
STATE=${1:?状態ファイル}; LIMIT=${2:-110}
source "$STATE"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
katazuke() {
  for i in $(seq 1 20); do
    [ -z "$(gcloud compute instances list --project="$PROJECT" --filter="name=$NAME" --format='value(name)' 2>/dev/null)" ] && break
    sleep 30
  done
  if [ -n "$(gcloud compute instances list --project="$PROJECT" --filter="name=$NAME" --format='value(name)' 2>/dev/null)" ]; then
    echo "VM $NAME がまだ残っています。片付けは次回に。"; return 1
  fi
  gcloud projects remove-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" \
    --role="projects/$PROJECT/roles/$ROLE" --condition="$CONDITION" --quiet >/dev/null 2>&1
  gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" \
    --role=roles/storage.objectAdmin --quiet >/dev/null 2>&1
  gcloud iam service-accounts delete "$SA" --project="$PROJECT" --quiet >/dev/null 2>&1
  mv "$STATE" "$STATE.owari"
  echo "VM は消えた。SA と IAM も片付けた。"
}
end=$(( $(date +%s) + LIMIT * 60 )); last=''
while (( $(date +%s) < end )); do
  state=''; note=''
  if gcloud storage cat "$PREFIX/status.json" >"$TMP/s.json" 2>/dev/null; then
    state=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["state"])' "$TMP/s.json")
    note=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["note"])' "$TMP/s.json")
  fi
  [ "$state $note" != "$last" ] && { echo "[$(date +%T)] $state $note（$(( ($(date +%s)-STARTED)/60 ))分）"; last="$state $note"; }
  if [ "$state" = complete ]; then gcloud storage cat "$PREFIX/chishiki.json"; echo; echo "完成: $PREFIX"; katazuke; exit 0; fi
  if [ "$state" = failed ]; then gcloud storage cat "$PREFIX/startup.log" 2>/dev/null | tail -30; katazuke; exit 1; fi
  if [ -z "$(gcloud compute instances list --project="$PROJECT" --filter="name=$NAME" --format='value(name)' 2>/dev/null)" ]; then
    echo 'VM が消えました（Spot中断か時間切れ）。完成扱いにしません。'; katazuke; exit 1
  fi
  if [ -z "$state" ] && (( $(date +%s) - STARTED > 1200 )); then
    echo '20分たっても知らせがありません。起動記録の末尾:'
    gcloud compute instances get-serial-port-output "$NAME" --project="$PROJECT" --zone="$ZONE" 2>/dev/null | tail -20
  fi
  sleep 60
done
echo "見張りの時間切れ（VM は動いたまま）。続き: bash $0 $STATE"
