# 仕事場の決めごと・詳しい版（10/2 に AGENTS.md から移した。毎回は読まない。必要な時に読む）

## 頭脳
アプリの local:main は Qwen3.6-35B-A3B（unsloth UD-Q2_K_XL を専門家160人に削った 7.7GiB、10/2〜。元の 11.7GB も models に残す）。頼みの控えは -cram 512。圧縮入りの llama-server（`~/LocalAI_mirror/llama-koukai`、語彙 99.99%）で、先読みなし（10/1: n-gram は 11% 遅く、外れると1回の返事が止まる）。最新 llama.cpp・専門家7人・MTP・専門家 top-p は この Mac では得なし（`dougu/jikken/KEKKA.md` 9/30）。
30B（local:30b）: Qwen3-30B-A3B Q2_K（Unsloth 11.3GB）、`-t 6 -ngl 0 -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off --reasoning-format none --spec-type ngram-simple --spec-ngram-simple-size-m 16`、深さ0。2507版は+2〜3点だが30%遅いため差替えない。

## 物差し（本人には「自作テストA〜D」）
|名/問題|ローカル|Luna max|
|---|---:|---:|
|GSM8K公式 `mondai_gsm8k.jsonl` 1319（`hyou-gsm8k`、12台/1時間）|93.2%（公表91.8%）|—|
|A=7段 `mondai_7dan.jsonl` 128|90→113（数え上げ電卓）|124|
|B=8段・既見 `mondai_8dan.jsonl` 127|99〜107→113〜117（道具）|125|
|C=9段・未見 `mondai_9dan.jsonl` 126|104→106（道具）|126|
|D=10段・未見 `mondai_10dan.jsonl` 127|基準104/101、道具測定済（`hakaru-zenbu-d10-k-j-n-s`）|—|
同設定でも±2〜8ぶれる（x64/ARM差）。直感役は独立280文（`dougu/hakaru_chokkan2.py`）で70%。

## 道具・教材
`kazoeru.py` の `erabu`/`toku` を物差しと本番で共用。LLMは式を書くのみ、計算はPython。型一致時だけ：数え上げ（切手型）、時刻（「2時間」除く）、並べ方（他N可）、選び方。本番 `kernel/kikai.py` は数え上げ（並べ方除く）のみ。
不採用（9/23）: 手順書（思考量減）、電卓の全問適用（B 103→64）、似た手本（後戻り30→13）、LoRA（`gcloud/lora.sh` $6、C 104→74）。短い解法を見せる/覚えさせると途中計算を省く。教材は途中計算を全て書く長文（`kernel/tehon.jsonl` 1007件は短文）。

## 外部計算資源
- GitHub Actions（無料・無制限）: `git push -f origin main:hakaru-zenbu[-switches]` → `kekka` 枝。switch: `-k`数え上げ `-j`時刻 `-n`並べ方 `-s`選び方 `-c`計算 `-t`手本 `-l`LoRA `-m2507` `-d8/-d9/-d10`。
- Google Cloud L4: `gcloud/ryoushika.sh`（imatrix効果なし）、`gcloud/lora.sh`（1 step 130秒、表示lossは8倍）。GCS残24GB（月約$0.5）。
- Groq/NVIDIA無料: 教材・検品。日次上限/混雑で停止（`tsukuru_tehon.py` は5人を回す）。Codex（9/28〜 Sol・Luna の high、max はまれ）: 審査 `dougu/shinsa.sh`（既定 Sol）、物差し `tsukuru_monosashi*.py`、教材 `tsukuru_tehon_luna.py`、調査。`< /dev/null` 必須。

## 失敗防止
大量実行前に1本を完走（9/24未試験で45本全停止。export漏れで道具なし測定も発生）。結果集約係に concurrency を付けない（待ちが取消）。カーネルの用件は `machine.py` と `kikai.py` の両OPSを確認（片方だけ見て9/24に10個重複）。GCP既定SAにGCS権限が必要。`a && b` は `set -e` でも失敗を止めない。起動合図が12分来なければVM削除。Codexがrepoを読めない場合、必要ソースを依頼文に貼る。
