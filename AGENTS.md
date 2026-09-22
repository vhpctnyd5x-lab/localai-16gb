# AGENTS.md — この仕事場（カーネル）の決めごと。全体は ~/.codex/AGENTS.md
合言葉は **早い・安い・賢い**。Claude は横の `CLAUDE.md`（`@AGENTS.md`）から読む。

## 場所
正は内蔵 `~/LocalAI_mirror/{kernel,koukai,llama-latest,models,uta}`。SSD は写し（`dougu/utsusu.sh`）。`kernel/`=本体（git 外）、`koukai/`=公開の写し（kernel を直したら `koukai/dougu/` に写す）。物差し `dougu/hakaru_*.py`・`monosashi/hakaru.py`、台本 `hashiru_*.sh`、結果 `dougu/kekka/`（git 外）。

## 決めごと
1. **held-out で測って、良くなければ入れない**。物差しを見ながら設定を選ばない（＝物差しに合わせるだけになる）。
2. Codex は main に push しない・kernel/ を書き換えない。同じファイルを同時に触らない。
3. 鍵は `~/.groq.env`・`~/.nvidia.env`・キーチェーン（台本が読む。値を出さない）。
4. 頭脳（llama-server）は 1本だけ・8080。GCP の VM は自動消滅で作る。GUI は最後の手段。

## 頭脳の土台
Qwen3-30B-A3B Q2_K（unsloth・11.3GB）、`-t 6 -ngl 0 -dev none -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off --reasoning-format none --spec-type ngram-simple --spec-ngram-simple-size-m 16`。7段 深さ0 92/128。深さ1・2 は下がる＝深さ0 固定。

## 物差し（2026-09-22 現在）
7段 128問（`monosashi/mondai_7dan.jsonl`）／直感役は 手作り36問・頭脳作り88文・**独立280文**（`kernel/chokkan_monosashi2_ok.jsonl`、別の先生が作り別の先生が検品）＝ `dougu/hakaru_chokkan2.py`。**小さい物差しの数字は甘い**（88文 90% ↔ 独立280文 70%）。

## 二人で回す（Claude Code ＋ Codex）
作る → 測る → Codex 審査 → 直す → 測る。`dougu/shinsa.sh <名> "<頼み>"`（terra・max・読み取り専用、約6分）。**Codex は repo を読めないことがある**ので、見せたいソースは頼み文に貼る。指摘は資料（測って採用）。

## 外の計算資源
| どこ | 使い方 | 実測 |
|---|---|---|
| **GitHub Actions**（公開 repo は無料・無制限、x64/ARM 4コア16GB） | `git push -f origin main:hakaru`（3問）／`hakaru-zenbu`（128問）／末尾 `-f1` `-f2`（深さ）／`hakaru-henka`（`dougu/actions_henka.txt` の起動指定）→ 枝 `kekka`。待つのは `dougu/actions_matsu.sh` | 7段 91/128（Mac 92）、128問 1.5時間 |
| **Google Cloud**（L4） | `gcloud/ryoushika.sh <HF名> 4` → imatrix Q2_K を作って手元へ（自動消滅・約 $2・1.5時間） | imatrix は効かず（30B 88/128） |
| Groq／NVIDIA（無料） | 教材と検品の先生。`~/.claude/scripts/groq.sh`、`kernel/nvidia.py`（`nv ask -m super`。承認ダイアログは廃止済み） | 頭脳の代わりにはならない |
| Modal／Oracle・Kaggle・Cloudflare・HF・TPU | Modal は GPU にカード要（保留）。他は未登録。TPU は llama.cpp が動かない | — |

**穴**: GCP は 既定 SA に GCS 権限が要る／`a && b` は set -e でも止まらない／CUDA は `/usr/local/cuda/bin`／合図が 12分来なければ VM を消す。llama.cpp 本家は Xing4.0（TeleChat 系）に未対応。
