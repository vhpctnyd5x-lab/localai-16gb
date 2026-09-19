# AGENTS.md — この仕事場（カーネル・手元の AI）の決めごと。全体の分は ~/.codex/AGENTS.md
合言葉は **早い・安い・賢い**。Claude は横の `CLAUDE.md`（`@AGENTS.md`）から読む。

## 場所
- 正は内蔵 `~/LocalAI_mirror/{kernel,koukai,llama-latest,models}`。SSD は写し（`dougu/utsusu.sh`）。`kernel/`=本体（git 外）、`koukai/`=公開の写し。kernel を直したら `koukai/dougu/` に写す。
- 物差し `dougu/hakaru_*.py`・`monosashi/hakaru.py`、走らせる台本 `hashiru_*.sh`、結果 `dougu/kekka/`（git 外）。

## 決めごと
1. 新しい仕組みは held-out の物差しで測り、良くなければ入れない。
2. Codex は main に push しない・kernel/ を書き換えない（読み取り専用か worktree）。同じファイルを同時に触らない。
3. 鍵は `~/.groq.env`・`~/.nvidia.env`・キーチェーン。台本が読む。
4. 手元の頭脳（llama-server）は 1本だけ・8080。GCP の VM は自動消滅で作る。GUI は最後の手段。

## 頭脳の土台
Qwen3-30B-A3B Q2_K（unsloth・11.3GB）、`-t 6 -ngl 0 -dev none -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off --reasoning-format none --spec-type ngram-simple`。7段 深さ0 92/128。

## 二人で回す（Claude Code ＋ Codex）
作る → 測る → Codex 審査 → 直す → 測る。`dougu/shinsa.sh <名> "<頼み>"`（terra・max・読み取り専用、約6分・100万トークンだが 9割キャッシュ）。指摘は資料（測って採用）。

## 外の計算資源（2026-09-20 時点）
| どこ | 使い方 | 実測 |
|---|---|---|
| **GitHub Actions**（公開 repo は無料・無制限、x64/ARM 4コア16GB） | `git push -f origin main:hakaru`（3問）／`hakaru-zenbu`（128問）／末尾 `-f1` `-f2`（深さ）／`hakaru-henka`（`dougu/actions_henka.txt` の起動指定を比べる）→ 結果は枝 `kekka`。待つ台本 `dougu/actions_matsu.sh` | 7段 91/128（Mac 92）、書き 13〜15 t/s、128問 1.5時間 |
| **Google Cloud**（L4、クレジット） | `gcloud/ryoushika.sh <HF名> 4` → imatrix Q2_K を作って手元へ（g2-standard-16・自動消滅・約 $2・1.5時間） | 30B: 88/128（効かず）、35B: 出来た・未測 |
| Groq／NVIDIA（無料 API） | 先生。`~/.claude/scripts/groq.sh -m openai/gpt-oss-120b`、`kernel/nvidia.py`。教材作り `dougu/tsukuru_iikata_kumo.py` | 頭脳の代わりにはならない（9/18） |
| Modal | 入ったが GPU はカード要 → 保留 | — |
| Oracle・Kaggle・Cloudflare・HF・TPU 他 | 未登録。TPU は llama.cpp が動かない | — |

GCP の穴: VM の既定 SA に GCS 権限を付ける（台本が付ける）／起動台本は `a && b` で失敗を握り潰さない／CUDA は `/usr/local/cuda/bin`／合図が 12分来なければ消す。アカウント・project は `gcloud config` に設定済み。
