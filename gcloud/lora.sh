#!/bin/bash
# 雲（GCP L4）で 教材（kernel/tehon.jsonl）を ローカル LLM に覚えさせる LoRA を焼き、手元へ持ってくる（2026-09-23）。
#   ねらい: 解くたびに手本を見せる（遅くなる）代わりに、頭そのものに「使う数・使わない数を仕分けて解く」を覚えさせる。
#   作り方は 9/7 の LoRA（型C 12.5→75%）と同じ: 元の Qwen3-30B-A3B で attention(q/k/v/o) だけを QLoRA → 手元の Q2_K にそのまま乗る。
#   使い方: gcloud/lora.sh [エポック=2] [時間=6]   → VM（g2-standard-16・自動消滅）を借り、焼いて GCS に置き、手元 models/ に落として VM を消す。
#           gcloud/lora.sh --toru   → GCS の出来上がりを落とすだけ
#   費用の目安: 約 $1.15/時 × 2〜4時間。落とし穴は 記憶 moe-qlora-jirai（transformers 4.57.1 固定 等）。
set -Eeuo pipefail
export PATH="$HOME/google-cloud-sdk/bin:$PATH"; export LANG=en_US.UTF-8
P=project-33e6be3b-57e3-4568-b34; Z=us-central1-a; NAME=lora1; B=gs://$P-gguf; TAG=tehon-lora
FAM=pytorch-2-9-cu129-ubuntu-2204-nvidia-580; COMMIT=b31b71f
MD=~/LocalAI_mirror/models; K=$(cd "$(dirname "$0")/.." && pwd)
toru(){
  gsutil -q cp "$B/$TAG.gguf" "$MD/$TAG.gguf.part" && gsutil -q cp "$B/$TAG.sha256" "$MD/$TAG.gguf.sha256"
  (cd "$MD" && [ "$(shasum -a 256 "$TAG.gguf.part" | cut -c1-64)" = "$(cut -c1-64 "$TAG.gguf.sha256")" ]) || { echo "sha256 が違う"; return 1; }
  mv "$MD/$TAG.gguf.part" "$MD/$TAG.gguf"; ls -la "$MD/$TAG.gguf"
}
if [ "${1:-}" = "--toru" ]; then toru; exit; fi
EP=${1:-2}; HOURS=${2:-6}
# 教材 → 本番（物差し）と同じ形の会話。system は monosashi/hakaru.py の SYSTEM と 1字も違えない
python3 - "$K" > "${TMPDIR:-/tmp}/lora_data.jsonl" <<'PY'
import json, os, re, sys
K = sys.argv[1]
src = open(os.path.join(K, "monosashi", "hakaru.py"), encoding="utf-8").read()
SYSTEM = eval(re.search(r"^SYSTEM = (\(.*?\))\n", src, re.S | re.M).group(1))
for l in open(os.path.expanduser("~/LocalAI_mirror/kernel/tehon.jsonl"), encoding="utf-8"):
    d = json.loads(l)
    print(json.dumps({"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": d["問"]},
                                   {"role": "assistant", "content": d["解き方"]}]}, ensure_ascii=False))
PY
N=$(wc -l < "${TMPDIR:-/tmp}/lora_data.jsonl"); echo "教材 $N 件"
gcloud compute images describe-from-family "$FAM" --project=deeplearning-platform-release --format='value(name)' >/dev/null
gsutil ls -b "$B" >/dev/null 2>&1 || gsutil mb -l us-central1 "$B"
SA="$(gcloud projects describe $P --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
gsutil -q iam ch "serviceAccount:$SA:objectAdmin" "$B"
gsutil -q cp "${TMPDIR:-/tmp}/lora_data.jsonl" "$K/gcloud/lora/manabu.py" "$K/gcloud/lora/hayaku.py" "$B/lora/"
gsutil -q rm "$B/status/$TAG.json" 2>/dev/null || true
{ echo '#!/bin/bash'; printf 'B=%s\nTAG=%s\nCOMMIT=%s\nEP=%s\n' "$B" "$TAG" "$COMMIT" "$EP"; cat <<'EOS'
exec > /var/log/lora.log 2>&1
set -Eeuo pipefail
status(){ printf '{"tag":"%s","state":"%s","at":"%s","note":"%s"}\n' "$TAG" "$1" "$(date -u +%FT%TZ)" "$2" > /root/status.json
  gsutil -q cp /root/status.json "$B/status/$TAG.json"; gsutil -q cp /var/log/lora.log "$B/status/$TAG.log" || true; }
trap 'status shippai "line $LINENO"' ERR
status hajime ""
( while true; do sleep 300; gsutil -q cp /var/log/lora.log "$B/status/$TAG.log" || true; done ) &
for i in $(seq 1 90); do nvidia-smi >/dev/null 2>&1 && break; sleep 10; done
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader; free -g | head -2; df -BG / | tail -1
cd /root; mkdir -p lora; gsutil -q cp "$B/lora/*" lora/
# ★ 版は固定（v5 は MoE の専門家を 3D に融合して 4bit が効かず OOM。記憶 moe-qlora-jirai）
pip install -q "transformers==4.57.1" "peft==0.17.1" accelerate bitsandbytes datasets huggingface_hub hf_transfer "jinja2>=3.1.0" sentencepiece gguf
python3 -c "import torchaudio" 2>/dev/null || pip uninstall -y torchaudio >/dev/null 2>&1 || true
git clone -q --filter=blob:none https://github.com/ggml-org/llama.cpp && git -C llama.cpp checkout -q "$COMMIT"
HF_HUB_ENABLE_HF_TRANSFER=1 python3 -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-30B-A3B', local_dir='/root/base', allow_patterns=['*.json','*.safetensors','*.txt','*.jinja'], max_workers=8)"
echo "落とした $(date +%T)"; du -sh /root/base; status manabu "教材 $(wc -l < lora/lora_data.jsonl)件 ${EP}エポック"
cd /root/lora
python3 -u manabu.py --base /root/base --data lora_data.jsonl --out /root/lora_out --epochs "$EP" --gcs "$B/lora_out" > /root/manabu.log 2>&1 || { tail -30 /root/manabu.log; status shippai "manabu"; exit 1; }
tail -8 /root/manabu.log; test -s /root/lora_out/adapter_model.safetensors
python3 /root/llama.cpp/convert_lora_to_gguf.py /root/lora_out --base /root/base --outfile "/root/$TAG.gguf" --outtype f16 > /root/conv.log 2>&1 || { tail -15 /root/conv.log; status shippai "convert"; exit 1; }
sha256sum "/root/$TAG.gguf" | tee /root/sha.txt
gsutil -q cp "/root/$TAG.gguf" "$B/"; gsutil -q cp /root/sha.txt "$B/$TAG.sha256"; gsutil -q cp /root/manabu.log "$B/status/"
status dekita "$(cut -c1-12 /root/sha.txt) $(stat -c %s /root/$TAG.gguf)B"
EOS
} > "${TMPDIR:-/tmp}/lora_startup.sh"
echo "=== LoRA を $HOURS 時間の VM で焼く（g2-standard-16・自動消滅・STANDARD・${EP}エポック）$(date +%T) ==="
gcloud compute instances create $NAME --project=$P --zone=$Z --machine-type=g2-standard-16 \
  --provisioning-model=STANDARD --instance-termination-action=DELETE --max-run-duration=${HOURS}h --maintenance-policy=TERMINATE \
  --image-family=$FAM --image-project=deeplearning-platform-release \
  --boot-disk-size=200GB --boot-disk-type=pd-balanced --boot-disk-auto-delete \
  --metadata="install-nvidia-driver=True" --metadata-from-file=startup-script="${TMPDIR:-/tmp}/lora_startup.sh" --scopes=cloud-platform --quiet --format='value(name,status)'
trap 'gcloud compute instances delete $NAME --project=$P --zone=$Z --quiet 2>/dev/null || true' EXIT
LAST=""; S=""; for i in $(seq 1 $((HOURS*60+10))); do sleep 60
  S=$(gsutil -q cat "$B/status/$TAG.json" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["state"], d["note"])' 2>/dev/null || echo "")
  [ "$S" != "$LAST" ] && { echo "[$(date +%T)] $S"; LAST=$S; }
  [ $i -ge 12 ] && [ -z "$S" ] && { echo "★ 起動台本が動いていない。serial の末尾:"; gcloud compute instances get-serial-port-output $NAME --project=$P --zone=$Z 2>/dev/null | grep -i 'startup-script' | tail -5; break; }
  [ $((i % 10)) -eq 0 ] && echo "[$(date +%T)] $(gsutil -q cat "$B/status/$TAG.log" 2>/dev/null | grep -v '^\s*$' | tail -1 | cut -c1-140)"
  case "$S" in dekita*|shippai*) break;; esac
  gcloud compute instances describe $NAME --project=$P --zone=$Z --format='value(status)' >/dev/null 2>&1 || { echo "VM が消えた（時間切れ？）"; break; }
done
echo "--- 記録の末尾 ---"; gsutil -q cat "$B/status/$TAG.log" 2>/dev/null | tail -25
gcloud compute instances delete $NAME --project=$P --zone=$Z --quiet 2>/dev/null && echo "VM を消した"; trap - EXIT
gcloud compute instances list --project=$P --format='value(name)' | grep -q . && echo "★ まだ VM がある" || echo "VM なし"
case "$S" in dekita*) toru;; esac
