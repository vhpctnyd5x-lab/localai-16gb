#!/bin/bash
# 雲（GCP L4）で「重要度つき（imatrix）の Q2_K」を作り、手元へ持ってくる。
#   ねらい: 同じ大きさ・同じ速さのまま賢くする（今の頭脳 unsloth Q2_K は imatrix 無し）。
#   使い方: gcloud/ryoushika.sh [Qwen/Qwen3-30B-A3B] [時間=4]   → VM（g2-standard-16: L4 24GB・64GB RAM・STANDARD・自動消滅）を借り、
#           中で作らせ、GCS に置き、出来たら手元 models/ に落として VM を消す。裏で 1本（約2時間）。
#           gcloud/ryoushika.sh --toru <TAG>   → GCS の出来上がりを手元に落とすだけ
#   費用の目安: g2-standard-16 STANDARD 約 $1.15/時 × 2〜4時間 ＋ 盤 300GB（時間割）＋ GCS 出し 11GB 約 $1。
#   9/19 Codex 審査で直した点: RAM 64GB・-ngl は試して決める・失敗を握り潰さない・完了を GCS の status で待つ・commit/HF revision/校正文を固定。
set -Eeuo pipefail
export PATH="$HOME/google-cloud-sdk/bin:$PATH"; export LANG=en_US.UTF-8
P=project-33e6be3b-57e3-4568-b34; Z=us-central1-a; NAME=quant1; B=gs://$P-gguf
FAM=pytorch-2-9-cu129-ubuntu-2204-nvidia-580; COMMIT=b31b71f; CHUNKS=${CHUNKS:-200}
MD=~/LocalAI_mirror/models
toru(){ # $1=TAG
  local f="$1-Q2_K-imatrix.gguf"
  [ "$(df -g "$MD" | awk 'NR==2{print $4}')" -gt 20 ] || { echo "手元の盤が 20GB 無い。GCS に置いたまま: $B/$f"; return 1; }
  gsutil -q cp "$B/$f" "$MD/$f.part" && gsutil -q cp "$B/$1-Q2_K-imatrix.sha256" "$MD/$f.sha256"
  (cd "$MD" && [ "$(shasum -a 256 "$f.part" | cut -c1-64)" = "$(cut -c1-64 "$f.sha256")" ]) || { echo "sha256 が違う"; return 1; }
  mv "$MD/$f.part" "$MD/$f"; ls -la "$MD/$f"; echo "落とした → $MD/$f"
}
if [ "${1:-}" = "--toru" ]; then toru "${2:?TAG}"; exit; fi
MODEL=${1:-Qwen/Qwen3-30B-A3B}; HOURS=${2:-4}; TAG=$(basename "$MODEL")
REV=$(curl -fsS "https://huggingface.co/api/models/$MODEL" | python3 -c 'import json,sys;print(json.load(sys.stdin)["sha"])')
gcloud compute images describe-from-family "$FAM" --project=deeplearning-platform-release --format='value(name)' >/dev/null
gsutil ls -b "$B" >/dev/null 2>&1 || gsutil mb -l us-central1 "$B"
# VM の既定サービスアカウントに GCS の読み書きを許す（新しいプロジェクトは既定で無い。9/19 これが無くて 3時間空回り）
SA="$(gcloud projects describe $P --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
gsutil -q iam ch "serviceAccount:$SA:objectAdmin" "$B"
TMP=${TMPDIR:-/tmp}; curl -fsSL -o "$TMP/calib.txt" "https://gist.githubusercontent.com/bartowski1182/eb213dccb3571f863da82e99418f81e8/raw/calibration_datav3.txt"
echo "校正文 sha256 $(shasum -a 256 "$TMP/calib.txt" | cut -c1-12) $(wc -c < "$TMP/calib.txt")B  HF $MODEL@${REV:0:12}  llama.cpp $COMMIT"
gsutil -q cp "$TMP/calib.txt" "$B/calib.txt"; gsutil -q rm "$B/status/$TAG.json" 2>/dev/null || true
{ echo '#!/bin/bash'; printf 'B=%s\nTAG=%s\nMODEL=%s\nREV=%s\nCOMMIT=%s\nCHUNKS=%s\n' "$B" "$TAG" "$MODEL" "$REV" "$COMMIT" "$CHUNKS"; cat <<'EOS'
exec > /var/log/quant.log 2>&1
set -Eeuo pipefail
status(){ printf '{"tag":"%s","state":"%s","at":"%s","note":"%s"}\n' "$TAG" "$1" "$(date -u +%FT%TZ)" "$2" > /root/status.json
  gsutil -q cp /root/status.json "$B/status/$TAG.json"; gsutil -q cp /var/log/quant.log "$B/status/$TAG.log" || true; }
trap 'status shippai "line $LINENO"' ERR
status hajime ""
( while true; do sleep 300; gsutil -q cp /var/log/quant.log "$B/status/$TAG.log" || true; done ) &
for i in $(seq 1 90); do nvidia-smi >/dev/null 2>&1 && break; sleep 10; done
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader; nproc; free -g | head -2; df -BG / | tail -1
cd /root; apt-get install -y -q git cmake build-essential python3-pip >/dev/null
git clone -q --filter=blob:none https://github.com/ggml-org/llama.cpp && cd llama.cpp && git checkout -q "$COMMIT"
pip install -q -r requirements/requirements-convert_hf_to_gguf.txt huggingface_hub hf_transfer
# ★ `a && b` は set -e でも a の失敗で止まらない（9/19 これで cmake 失敗を見逃した）→ 1行ずつ・出来た物を確かめる
export PATH=/usr/local/cuda/bin:$PATH
cmake -B build -DGGML_CUDA=ON -DLLAMA_CURL=OFF -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc > /root/cmake.log 2>&1 || { tail -15 /root/cmake.log; status shippai "cmake"; exit 1; }
cmake --build build -j"$(nproc)" --target llama-quantize llama-imatrix > /root/build.log 2>&1 || { tail -15 /root/build.log; status shippai "build"; exit 1; }
test -x build/bin/llama-imatrix && test -x build/bin/llama-quantize
echo "作った $(date +%T)"
HF_HUB_ENABLE_HF_TRANSFER=1 python3 -c "from huggingface_hub import snapshot_download; snapshot_download('$MODEL', revision='$REV', local_dir='/root/hf', allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken'])"
echo "落とした $(date +%T)"; df -BG / | tail -1
python3 convert_hf_to_gguf.py /root/hf --outtype bf16 --outfile "/root/$TAG-BF16.gguf" >/dev/null; rm -rf /root/hf
echo "BF16 にした $(date +%T) $(stat -c %s /root/$TAG-BF16.gguf)B"; df -BG / | tail -1
gsutil -q cp "$B/calib.txt" /root/calib.txt; sha256sum /root/calib.txt
# 試し: 4 chunks で VRAM と時間を測る。載らなければ層を減らす（48層。24GB には全部は載らない）
NGL=""; for n in 16 12 8 4; do
  if ./build/bin/llama-imatrix -m "/root/$TAG-BF16.gguf" -f /root/calib.txt -o /root/imatrix_tameshi.dat -ngl $n -c 512 --chunks 4 > /root/tameshi_$n.log 2>&1; then NGL=$n; break; fi
  echo "ngl $n だめ: $(grep -i -m1 'out of memory\|error' /root/tameshi_$n.log || tail -1 /root/tameshi_$n.log)"; done
[ -n "$NGL" ] || { status shippai "imatrix が動かない"; exit 1; }
grep -i 'compute_imatrix\|tokens\|used\|estimated' /root/tameshi_$NGL.log | tail -5
echo "ngl $NGL で本番 $CHUNKS chunks $(date +%T)"; T=$(date +%s)
./build/bin/llama-imatrix -m "/root/$TAG-BF16.gguf" -f /root/calib.txt -o /root/imatrix.dat -ngl $NGL -c 512 --chunks $CHUNKS > /root/imatrix.log 2>&1
tail -8 /root/imatrix.log; echo "imatrix $(( $(date +%s)-T ))秒"; test -s /root/imatrix.dat
T=$(date +%s); ./build/bin/llama-quantize --imatrix /root/imatrix.dat "/root/$TAG-BF16.gguf" "/root/$TAG-Q2_K-imatrix.gguf" Q2_K "$(nproc)" > /root/quant.log 2>&1
tail -3 /root/quant.log; echo "量子化 $(( $(date +%s)-T ))秒 $(stat -c %s /root/$TAG-Q2_K-imatrix.gguf)B"
sha256sum "/root/$TAG-Q2_K-imatrix.gguf" | tee /root/sha.txt
gsutil -q cp "/root/$TAG-Q2_K-imatrix.gguf" "$B/"; gsutil -q cp /root/imatrix.dat "$B/$TAG-imatrix.dat"; gsutil -q cp /root/sha.txt "$B/$TAG-Q2_K-imatrix.sha256"
gsutil -q cp /root/imatrix.log /root/tameshi_$NGL.log "$B/status/"
status dekita "$(cut -c1-12 /root/sha.txt) ngl$NGL"
EOS
} > "$TMP/quant_startup.sh"
echo "=== $MODEL を $HOURS 時間の VM で量子化（g2-standard-16・自動消滅・STANDARD）$(date +%T) ==="
gcloud compute instances create $NAME --project=$P --zone=$Z --machine-type=g2-standard-16 \
  --provisioning-model=STANDARD --instance-termination-action=DELETE --max-run-duration=${HOURS}h --maintenance-policy=TERMINATE \
  --image-family=$FAM --image-project=deeplearning-platform-release \
  --boot-disk-size=300GB --boot-disk-type=pd-balanced --boot-disk-auto-delete \
  --metadata="install-nvidia-driver=True" --metadata-from-file=startup-script="$TMP/quant_startup.sh" --scopes=cloud-platform --quiet --format='value(name,status)'
trap 'gcloud compute instances delete $NAME --project=$P --zone=$Z --quiet 2>/dev/null || true' EXIT
LAST=""; for i in $(seq 1 $((HOURS*60+10))); do sleep 60
  S=$(gsutil -q cat "$B/status/$TAG.json" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["state"], d["note"])' 2>/dev/null || echo "")
  [ "$S" != "$LAST" ] && { echo "[$(date +%T)] $S"; LAST=$S; }
  # 12分たっても「hajime」が来なければ起動台本が死んでいる → 記録を見せて止める（空回りで金を溶かさない）
  [ $i -ge 12 ] && [ -z "$S" ] && { echo "★ 起動台本が動いていない。serial の末尾:"; gcloud compute instances get-serial-port-output $NAME --project=$P --zone=$Z 2>/dev/null | grep -i 'startup-script' | tail -5; break; }
  [ $((i % 10)) -eq 0 ] && echo "[$(date +%T)] $(gsutil -q cat "$B/status/$TAG.log" 2>/dev/null | tail -1 | cut -c1-120)"
  case "$S" in dekita*|shippai*) break;; esac
  gcloud compute instances describe $NAME --project=$P --zone=$Z --format='value(status)' >/dev/null 2>&1 || { echo "VM が消えた（時間切れ？）"; break; }
done
echo "--- 記録の末尾 ---"; gsutil -q cat "$B/status/$TAG.log" 2>/dev/null | tail -25
gcloud compute instances delete $NAME --project=$P --zone=$Z --quiet 2>/dev/null && echo "VM を消した"; trap - EXIT
gcloud compute instances list --project=$P --format='value(name)' | grep -q . && echo "★ まだ VM がある" || echo "VM なし"
case "$S" in dekita*) toru "$TAG";; esac
