# AGENTS.md — この仕事場（カーネル）の決めごと。全体は ~/.codex/AGENTS.md
合言葉は **早い・安い・賢い**。呼び方: **ローカル LLM＝頭（Qwen3-30B）、カーネル＝その手下の仕組み**（直感役・道具・server.py）。Claude は横の `CLAUDE.md`（`@AGENTS.md`）から読む。

## 場所
正は内蔵 `~/LocalAI_mirror/{kernel,koukai,llama-latest,models}`。SSD は写し（`dougu/utsusu.sh`）。`kernel/`=本体（git 外。直したら `koukai/dougu/` に写す）。物差し `monosashi/hakaru.py`、比べる台本 `dougu/hashiru_tejun.sh`、結果 `dougu/kekka/`（git 外）。不採用の 35B は SSD `LocalAI/models_hokan/`。

## 決めごと
1. **未見の物差しで測って、良くなければ入れない**。見た物差し（間違いを読んだもの）の伸びは信じない（9/23: テストB +14 → 未見 C +2）。1つの物差しだけで決めない。
2. Codex は main に push しない・kernel/ を書き換えない。鍵は `~/.groq.env`・`~/.nvidia.env`（値を出さない）。
3. llama-server は 1本・8080。**裏の処理は `dougu/ura.sh`**、**外の処理の待ち役は `dougu/matsu.sh actions|gcp|pid`**（run_in_background で。終わると結果が返る）。置き換えたら古い方をすぐ止める。GCP の VM は自動消滅で作る。

## 頭脳
Qwen3-30B-A3B Q2_K（unsloth 11.3GB）、`-t 6 -ngl 0 -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off --reasoning-format none --spec-type ngram-simple --spec-ngram-simple-size-m 16`、深さ0。2507 版は +2〜3 で 3割遅い＝差し替えない。

## 物差し（本人には「自作テストA〜D」と言う）
| 名 | ファイル | ローカル | Luna（max） |
|---|---|---|---|
| **GSM8K（公式）** | `mondai_gsm8k.jsonl` 1319（枝 `hyou-gsm8k`、12台で1時間） | **93.2%**（公表 91.8%） | — |
| A=7段 | `mondai_7dan.jsonl` 128 | 90 → 113（数え上げ電卓） | 124 |
| B=8段（見た） | `mondai_8dan.jsonl` 127 | 99〜107 → 113〜117（道具） | 125 |
| C=9段（未見） | `mondai_9dan.jsonl` 126 | 104 → 106（道具） | 126 |
| D=10段（未見） | `mondai_10dan.jsonl` 127 | 基準 104/101。道具は測定済み（枝 `hakaru-zenbu-d10-k-j-n-s`） | — |
同じ設定でも ±2〜8 ぶれる（x64 と ARM で違う）。直感役は 独立280文（`dougu/hakaru_chokkan2.py`）で 70%。

## 道具（`kazoeru.py` の `erabu`/`toku`。物差しと本番で同じ関数。ローカル LLM は書き出すだけ・計算は Python）
数え上げ（切手型）・時刻（「2時間」は除く）・並べ方（他N 可）・選び方。**型が合うときだけ**使う。本番 `kernel/kikai.py` は まだ「数え上げ（並べ方除く）」だけ。
**不採用（9/23）**: 手順書（考える量が減る）、計算電卓の全問適用（B 103→64）、似た手本（後戻り 30→13）、**LoRA**（`gcloud/lora.sh`・$6、C 104→74）。短い解き方を見せる／覚えさせると途中の計算を省く。**教材は途中の計算を全部書く長い形で**（`kernel/tehon.jsonl` 1007件は短い形）。

## 外の計算資源
| どこ | 使い方 |
|---|---|
| **GitHub Actions**（無料・無制限） | `git push -f origin main:hakaru-zenbu[-スイッチ]` → 枝 `kekka`。スイッチ: `-k` 数え上げ `-j` 時刻 `-n` 並べ方 `-s` 選び方 `-c` 計算 `-t` 手本 `-l` LoRA `-m2507` `-d8/-d9/-d10` |
| **Google Cloud**（L4） | `gcloud/ryoushika.sh`（imatrix、効かず）、`gcloud/lora.sh`（1歩130秒、表示 loss は 8倍）。GCS に 24GB 残り（月 $0.5 ほど） |
| Groq／NVIDIA（無料） | 教材と検品の先生。1日の上限・混雑で止まる（`tsukuru_tehon.py` は 5人を回す） |
| Codex（Luna） | 審査 `dougu/shinsa.sh`、物差しづくり `tsukuru_monosashi*.py`、教材 `tsukuru_tehon_luna.py`、調査。`< /dev/null` 必須 |

**穴**: GCP は既定 SA に GCS 権限が要る／`a && b` は set -e でも止まらない／起動の合図が 12分来なければ VM を消す／Codex は repo を読めないことがある（見せたいソースは頼み文に貼る）。
