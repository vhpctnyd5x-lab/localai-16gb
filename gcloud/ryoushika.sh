#!/bin/bash
# 雲（GCP L4）で「重要度つき（imatrix）の Q2_K」を作り、手元へ持ってくる。★ まだ試走前（2026-09-18 に下書き）
#   ねらい: 同じ大きさ・同じ速さのまま賢くする（imatrix は 2bit で効きが大きい）。候補は
#     ① 今の頭脳 Qwen/Qwen3-30B-A3B → Q2_K + imatrix（今の Q2_K は imatrix 無し）
#     ② 新世代 Qwen/Qwen3.5-35B-A3B → Q2_K + imatrix（9/11 は IQ2_S で測って遅かった。Q2_K なら同じ速さの土俵）
#   使い方: ./ryoushika.sh Qwen/Qwen3-30B-A3B [時間=4]     → VM を STANDARD で借り（自動消滅）、中で作らせ、GCS へ置く
#           ./ryoushika.sh --toru                            → 出来た GGUF を ~/LocalAI_mirror/models/ に落とす（写しは 1 本ずつ）
#   費用の目安: L4 STANDARD ¥110/時 × 3〜4時間 ＋ ディスク。予算アラート「GPU見張り」が知らせる。
export PATH="$HOME/google-cloud-sdk/bin:$PATH"; export LANG=en_US.UTF-8
P=project-33e6be3b-57e3-4568-b34; Z=us-central1-a; NAME=quant1; B=gs://$P-gguf
if [ "$1" = "--toru" ]; then
  gsutil ls "$B/" ; echo "落とすには: gsutil cp $B/<名前>.gguf ~/LocalAI_mirror/models/"; exit 0
fi
MODEL=${1:-Qwen/Qwen3-30B-A3B}; HOURS=${2:-4}; TAG=$(basename "$MODEL")
gsutil ls -b "$B" >/dev/null 2>&1 || gsutil mb -l us-central1 "$B"
cat > /tmp/quant_startup.sh <<EOS
#!/bin/bash
set -e; exec > /var/log/quant.log 2>&1
cd /root; apt-get install -y -q git cmake build-essential python3-pip aria2 >/dev/null
git clone --depth 1 https://github.com/ggml-org/llama.cpp && cd llama.cpp
pip install -q -r requirements/requirements-convert_hf_to_gguf.txt huggingface_hub
cmake -B build -DGGML_CUDA=ON && cmake --build build -j8 --target llama-quantize llama-imatrix
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('$MODEL', local_dir='/root/hf', allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken'])"
python3 convert_hf_to_gguf.py /root/hf --outtype bf16 --outfile /root/$TAG-BF16.gguf
# 重要度の校正文: 世間でよく使われる混合データ（bartowski の calibration_datav3・英語主体）。★ 日本語を足した自前の校正文に差し替えるのが次の宿題
curl -sL -o /root/calib.txt "https://gist.githubusercontent.com/bartowski1182/eb213dccb3571f863da82e99418f81e8/raw/calibration_datav3.txt"
./build/bin/llama-imatrix -m /root/$TAG-BF16.gguf -f /root/calib.txt -o /root/imatrix.dat -ngl 99 -c 512 --chunks 200 || true
./build/bin/llama-quantize --imatrix /root/imatrix.dat /root/$TAG-BF16.gguf /root/$TAG-Q2_K-imatrix.gguf Q2_K 8
gsutil cp /root/$TAG-Q2_K-imatrix.gguf $B/
echo DONE
EOS
echo "=== $MODEL を $HOURS 時間の VM で量子化（自動消滅・STANDARD）==="
gcloud compute instances create $NAME --project=$P --zone=$Z --machine-type=g2-standard-8 \
  --provisioning-model=STANDARD --instance-termination-action=DELETE --max-run-duration=${HOURS}h \
  --image-family=pytorch-2-9-cu129-ubuntu-2204-nvidia-580 --image-project=deeplearning-platform-release \
  --boot-disk-size=300GB --boot-disk-type=pd-balanced --boot-disk-auto-delete \
  --metadata="install-nvidia-driver=True" --metadata-from-file=startup-script=/tmp/quant_startup.sh --scopes=cloud-platform --quiet
echo "見張り: gcloud compute ssh $NAME --zone=$Z -- tail -f /var/log/quant.log ／ 出来上がり: ./ryoushika.sh --toru"
