#!/bin/bash
# VM専用。手元では実行しない。hajimeru.sh から metadata とコード一式を渡す。
set -Eeuo pipefail
umask 077
WORK=/var/lib/chishiki
mkdir -p "$WORK"
exec >"$WORK/startup.log" 2>&1
cd "$WORK"
META=http://metadata.google.internal/computeMetadata/v1/instance/attributes
meta() { curl -fsS --retry 3 --max-time 30 -H 'Metadata-Flavor: Google' "$META/$1"; }
BUCKET=$(meta chishiki-bucket)
RUN_ID=$(meta chishiki-run)
BUNDLE_SHA=$(meta chishiki-bundle-sha256)
WIKI_LIMIT=$(meta chishiki-wiki-limit)
MAX_CHARS=$(meta chishiki-max-chars)
WORKERS=$(meta chishiki-workers)
PREFIX="gs://$BUCKET/runs/$RUN_ID"
STATUS=running
NOTE=起動

write_status() {
  python3 - "$STATUS" "$NOTE" >status.json <<'PY'
import json, sys, time
print(json.dumps({'state': sys.argv[1], 'note': sys.argv[2], 'time': time.time()}, ensure_ascii=False))
PY
  gcloud storage cp --quiet status.json "$PREFIX/status.json"
}
finish() {
  local code=$?
  trap - EXIT
  set +e
  if [ "$code" -ne 0 ]; then STATUS=failed; NOTE="失敗（終了番号 $code・startup.log を参照）"; fi
  if command -v gcloud >/dev/null; then
    gcloud storage cp --quiet startup.log "$PREFIX/startup.log"
    write_status
  fi
  # 成否にかかわらず自己削除。失敗時もCloud側 max-run-duration と手元の待ちが削除する。
  if [ -f code/fetch.py ]; then python3 code/fetch.py --self-delete; fi
  exit "$code"
}
trap finish EXIT
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv git curl ca-certificates google-cloud-cli
NOTE=コード取得; write_status
gcloud storage cp --quiet "gs://$BUCKET/code/$RUN_ID.tar.gz" bundle.tar.gz
printf '%s  bundle.tar.gz\n' "$BUNDLE_SHA" | sha256sum --check --status
mkdir code
tar -xzf bundle.tar.gz -C code
python3 -m venv venv
venv/bin/pip install --disable-pip-version-check --no-cache-dir -r code/requirements.txt
NOTE=公開ダンプ取得; write_status
venv/bin/python code/fetch.py --directory dumps --site jawiki --site jawikibooks --site jawikisource
git clone --depth 1 --single-branch https://github.com/aozorahack/aozorabunko_text.git aozora
git -C aozora rev-parse HEAD >aozora-commit.txt
NOTE=本文変換と索引作成; write_status
# 10/4: 中の進み具合が見えなかった。変換中は10分ごとに記録をGCSへ写す（見張りが末尾を出す）。
( while sleep 600; do gcloud storage cp --quiet startup.log "$PREFIX/startup.log" >/dev/null 2>&1; done ) &
# 分割ダンプでも1回の変換に渡す。文字列の eval はしない。
venv/bin/python - "$WIKI_LIMIT" "$MAX_CHARS" "$WORKERS" <<'PY'
import json, subprocess, sys
inputs = json.load(open('dumps/inputs.json'))
cmd = ['venv/bin/python', 'code/henkan.py', '--output', 'chishiki.sqlite3',
       '--aozora', 'aozora', '--wiki-limit', sys.argv[1], '--max-chars', sys.argv[2], '--workers', sys.argv[3]]
for site in ('jawiki', 'jawikibooks', 'jawikisource'):
    for path in inputs[site]:
        cmd += ['--wiki', site, path]
subprocess.run(cmd, check=True)
PY
NOTE=出来上がりをGCSへ保存; write_status
gcloud storage cp --quiet chishiki.sqlite3 chishiki.json chishiki.sha256 aozora-commit.txt "$PREFIX/"
gcloud storage cp --quiet dumps/*-dumpstatus.json "$PREFIX/"
# 本体・検証情報のアップロード完了後だけ complete にする。
STATUS=complete
NOTE=完成
