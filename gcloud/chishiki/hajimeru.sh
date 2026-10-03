#!/bin/bash
# 作るだけの段階では実行しない。Claude が本人の承認を得たあと、前で待つ。
# 費用の計画値（USD、us-central1、e2-standard-8 Spot、2026-10-03確認）:
#   8 vCPU + 32 GiB: 約 $0.107/時（変動）。4〜12時間なら $0.43〜1.29。
#   pd-standard 100GB: $4/月 ≒ $0.0055/時、4〜12時間 $0.02〜0.07。
#   外部IPv4: 約 $0.005/時、4〜12時間 $0.02〜0.06。
#   GCS STANDARD: 約 $0.020/GiB月。2〜4GiB を1日なら $0.001〜0.003。
#   日本の手元への転送: 約 $0.12/GiB、2〜4GiB $0.24〜0.48。API操作は数セントを計上。
#   合計目安: 2〜4GiBなら $0.8〜2、6〜15GiBなら $1.3〜3.5（税・Spotやり直し別）。
#   30万件・8000字上限はFTS二重格納で2〜4GiBを超え得る。6〜15GiBも計画する。
#   既定12時間でVM・100GBディスクを削除。保存物は残す（GCS継続料金あり）。
#   時間・サイズは大規模未測定の仮見積もり。Spot中断の自動再実行はしない。
# 料金出典:
#   https://cloud.google.com/spot-vms/pricing
#   https://cloud.google.com/compute/disks-image-pricing
#   https://cloud.google.com/vpc/network-pricing
#   https://cloud.google.com/storage/pricing
# 使い方: bash gcloud/chishiki/hajimeru.sh
# 任意: BUCKET=既存バケット ZONE=us-central1-a MAX_HOURS=12 WIKI_LIMIT=300000 MAX_CHARS=8000 WORKERS=6
# 初回はAPI有効化・バケット・実行専用SA・自己削除用custom roleも作る。IAM権限が必要。
set -Eeuo pipefail
umask 077
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
command -v gcloud >/dev/null || { echo 'gcloud がありません'; exit 1; }
PROJECT=$(gcloud config get-value project 2>/dev/null)
[ -n "$PROJECT" ] && [ "$PROJECT" != '(unset)' ] || { echo 'gcloud の既定プロジェクトが未設定です'; exit 1; }
ZONE=${ZONE:-us-central1-a}
REGION=${ZONE%-*}
BUCKET=${BUCKET:-${PROJECT}-chishiki}
MAX_HOURS=${MAX_HOURS:-12}
WIKI_LIMIT=${WIKI_LIMIT:-300000}
MAX_CHARS=${MAX_CHARS:-8000}
WORKERS=${WORKERS:-6}
for value in "$MAX_HOURS" "$WIKI_LIMIT" "$MAX_CHARS" "$WORKERS"; do
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || { echo '設定値は正の整数にしてください'; exit 1; }
done
(( MAX_HOURS <= 24 && MAX_CHARS <= 8000 && WORKERS <= 8 )) || { echo '時間は24以下・字数8000以下・並列8以下です'; exit 1; }
[[ "$BUCKET" =~ ^[a-z0-9][a-z0-9._-]+[a-z0-9]$ ]] || { echo 'バケット名が不正です'; exit 1; }
RUN_ID="$(date -u +%Y%m%d-%H%M%S)-$(python3 -c 'import secrets; print(secrets.token_hex(2))')"
NAME="chishiki-$RUN_ID"
SA_ID="ck-$RUN_ID"
SA="$SA_ID@$PROJECT.iam.gserviceaccount.com"
ROLE=chishikiVmSelfDelete
CONDITION="expression=resource.type=='compute.googleapis.com/Instance' && resource.name.endsWith('/instances/$NAME'),title=$NAME"
PREFIX="gs://$BUCKET/runs/$RUN_ID"
TMP_WORK=$(mktemp -d)
CREATING=0
SA_CREATED=0
BOUND=0
BUCKET_BOUND=0

cleanup() {
  local code=$?
  trap - EXIT
  set +e
  local safe=1 names
  if [ "$CREATING" = 1 ]; then
    gcloud compute instances delete "$NAME" --project="$PROJECT" --zone="$ZONE" --quiet >/dev/null 2>&1
    names=$(gcloud compute instances list --project="$PROJECT" --filter="name=$NAME" --format='value(name)' 2>/dev/null)
    if [ "$?" -ne 0 ] || [ -n "$names" ]; then
      safe=0
      echo "VMの削除を確認できません。確認対象: $PROJECT / $ZONE / $NAME（Cloud側の時間上限も設定済み）" >&2
    fi
  fi
  if [ "$safe" = 1 ]; then
    if [ "$BOUND" = 1 ]; then
      gcloud projects remove-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" \
        --role="projects/$PROJECT/roles/$ROLE" --condition="$CONDITION" --quiet >/dev/null 2>&1
    fi
    if [ "$BUCKET_BOUND" = 1 ]; then
      gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" \
        --role=roles/storage.objectAdmin --quiet >/dev/null 2>&1
    fi
    if [ "$SA_CREATED" = 1 ]; then
      gcloud iam service-accounts delete "$SA" --project="$PROJECT" --quiet >/dev/null 2>&1
    fi
  fi
  rm -rf -- "$TMP_WORK"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "プロジェクト $PROJECT / $ZONE / $NAME / 最大${MAX_HOURS}時間（Spot・概算は台本先頭）"
echo "保存先: $PREFIX"
gcloud services enable compute.googleapis.com storage.googleapis.com iam.googleapis.com --project="$PROJECT" --quiet
if ! gcloud storage buckets describe "gs://$BUCKET" --format=json >"$TMP_WORK/bucket.json" 2>/dev/null; then
  gcloud storage buckets create "gs://$BUCKET" --project="$PROJECT" --location="$REGION" \
    --default-storage-class=STANDARD --uniform-bucket-level-access --public-access-prevention --quiet
  gcloud storage buckets describe "gs://$BUCKET" --format=json >"$TMP_WORK/bucket.json"
fi
python3 - "$TMP_WORK/bucket.json" "$REGION" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
if d.get('location', '').lower() != sys.argv[2].lower():
    raise SystemExit('バケットとVMのリージョンが違います。不要な転送費を避けるため停止します')
if d.get('default_storage_class', d.get('storageClass')) != 'STANDARD':
    raise SystemExit('バケットは STANDARD を指定してください')
PY
# SAはこの実行だけ。自己削除以外のCompute操作は許さない。
gcloud iam service-accounts create "$SA_ID" --project="$PROJECT" --display-name="知識ダンプ $RUN_ID" --quiet
SA_CREATED=1
if ! gcloud iam roles describe "$ROLE" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam roles create "$ROLE" --project="$PROJECT" --title='知識VM自己削除' \
    --permissions=compute.instances.delete --stage=GA --quiet
fi
gcloud iam roles describe "$ROLE" --project="$PROJECT" --format=json >"$TMP_WORK/role.json"
python3 - "$TMP_WORK/role.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
if d.get('deleted') or d.get('stage') == 'DISABLED' or set(d.get('includedPermissions', [])) != {'compute.instances.delete'}:
    raise SystemExit('既存の自己削除用roleの権限が違います。変更せず停止します')
PY
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" \
  --role="projects/$PROJECT/roles/$ROLE" --condition="$CONDITION" --quiet >/dev/null
BOUND=1
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" \
  --role=roles/storage.objectAdmin --quiet >/dev/null
BUCKET_BOUND=1
tar -czf "$TMP_WORK/bundle.tar.gz" -C "$HERE" henkan.py db_common.py fetch.py requirements.txt
BUNDLE_SHA=$(python3 - "$TMP_WORK/bundle.tar.gz" <<'PY'
import hashlib, sys
with open(sys.argv[1], 'rb') as f: print(hashlib.file_digest(f, 'sha256').hexdigest())
PY
)
gcloud storage cp --quiet "$TMP_WORK/bundle.tar.gz" "gs://$BUCKET/code/$RUN_ID.tar.gz"
CREATING=1
gcloud compute instances create "$NAME" --project="$PROJECT" --zone="$ZONE" \
  --machine-type=e2-standard-8 --provisioning-model=SPOT --maintenance-policy=TERMINATE \
  --instance-termination-action=DELETE --max-run-duration="${MAX_HOURS}h" --no-restart-on-failure \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=100GB --boot-disk-type=pd-standard --boot-disk-auto-delete \
  --service-account="$SA" --scopes=cloud-platform \
  --metadata="chishiki-bucket=$BUCKET,chishiki-run=$RUN_ID,chishiki-bundle-sha256=$BUNDLE_SHA,chishiki-wiki-limit=$WIKI_LIMIT,chishiki-max-chars=$MAX_CHARS,chishiki-workers=$WORKERS" \
  --metadata-from-file="startup-script=$HERE/vm_startup.sh" --quiet
started=$(date +%s)
deadline=$(( started + MAX_HOURS * 3600 + 600 ))
last=''
while (( $(date +%s) < deadline )); do
  state=''; note=''
  if gcloud storage cat "$PREFIX/status.json" >"$TMP_WORK/status.json" 2>/dev/null; then
    state=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["state"])' "$TMP_WORK/status.json")
    note=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["note"])' "$TMP_WORK/status.json")
  fi
  if [ "$state $note" != "$last" ]; then echo "[$(date +%T)] $state $note"; last="$state $note"; fi
  if [ "$state" = complete ]; then
    gcloud storage cat "$PREFIX/chishiki.json"
    echo "完成。本人の承認後に: gcloud storage cp '$PREFIX/chishiki.sqlite3' '$PREFIX/chishiki.sha256' '$PREFIX/chishiki.json' 保存先/"
    echo '取り込み前に SHA256 を照合し、torikomu.py --dry-run で件数を確認してください。'
    exit 0
  fi
  [ "$state" != failed ] || { echo "失敗記録: $PREFIX/startup.log" >&2; exit 1; }
  if [ -z "$state" ] && (( $(date +%s) - started > 1200 )); then
    echo '20分経っても起動通知がありません。VMを片付けます。起動記録の末尾:' >&2
    gcloud compute instances get-serial-port-output "$NAME" --project="$PROJECT" --zone="$ZONE" 2>/dev/null | tail -20 >&2 || true
    exit 1
  fi
  names=$(gcloud compute instances list --project="$PROJECT" --filter="name=$NAME" --format='value(name)')
  [ -n "$names" ] || { echo 'VMが消えました（Spot中断または時間切れ）。完成扱いにしません。' >&2; exit 1; }
  sleep 30
done
echo "時間切れ。記録: $PREFIX/startup.log" >&2
exit 1
