# AGENTS.md — この仕事場（カーネル）の決めごと。全体は ~/.codex/AGENTS.md
合言葉は **早い・安い・賢い**。**呼び方（本人 9/23）: ローカル LLM＝頭（Qwen3-30B）、カーネル＝その手下の仕組み（直感役・道具・server.py）。**Claude は横の `CLAUDE.md`（`@AGENTS.md`）から読む。

## 場所
正は内蔵 `~/LocalAI_mirror/{kernel,koukai,llama-latest,models,uta}`。SSD は写し（`dougu/utsusu.sh`）。`kernel/`=本体（git 外）、`koukai/`=公開の写し（kernel を直したら `koukai/dougu/` に写す）。物差し `dougu/hakaru_*.py`・`monosashi/hakaru.py`、台本 `hashiru_*.sh`、結果 `dougu/kekka/`（git 外）。

## 決めごと
1. **held-out で測って、良くなければ入れない**。物差しを見ながら設定を選ばない（＝物差しに合わせるだけになる）。
2. Codex は main に push しない・kernel/ を書き換えない。同じファイルを同時に触らない。
3. 鍵は `~/.groq.env`・`~/.nvidia.env`・キーチェーン（台本が読む。値を出さない）。
4. 頭脳（llama-server）は 1本だけ・8080。**裏の処理は `dougu/ura.sh` で一覧**。置き換えたら古い方をその場で止める。報告の前に必ず見る（本人 9/23: 隠れた処理を残さない）。GCP の VM は自動消滅で作る。GUI は最後の手段。

## 頭脳の土台
Qwen3-30B-A3B Q2_K（unsloth・11.3GB）、`-t 6 -ngl 0 -dev none -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off --reasoning-format none --spec-type ngram-simple --spec-ngram-simple-size-m 16`。7段 深さ0 92/128。深さ1・2 は下がる＝深さ0 固定。

## 物差し（2026-09-23 現在。本人向けの呼び名: 7段=自作テストA、8段=B、9段=C）
7段 128問（`monosashi/mondai_7dan.jsonl`）／直感役は 手作り36問・頭脳作り88文・**独立280文**（`kernel/chokkan_monosashi2_ok.jsonl`、別の先生が作り別の先生が検品）＝ `dougu/hakaru_chokkan2.py`。**小さい物差しの数字は甘い**（88文 90% ↔ 独立280文 70%）。
**目標＝GPT-6 Luna（max・道具なし）の 7段 124/128**（2026-09-23、`dougu/kekka/7dan_gpt-6-luna_max.tsv`）。カーネルは 90/128。差は 場合分け_切手 9↔28・同文脈_在庫 20↔32 に集中（わな 32↔32・後戻り 29↔32）。
**手順書（system に足す考え方）は不採用**（9/23、練習32問 `monosashi/mondai_renshuu.jsonl`）: なし 20/20（2回）→ v1 18・v2 16。関係ない数の仕分けは +2 だが、足すと考える量が減り数え上げが 8→4→2 に落ちる。数え上げは言葉でなく計算で。
**数え上げ電卓は採用**（9/23）: ローカル LLM は「変数: x 0 27／条件: 3*x+5*y+8*z == 83」と式だけ書き、`kazoeru.py`（ast で四則・比較だけ許す閉じた電卓。シェルではない）が数える。本番の 7段 数え上げ 32問で **9→31/32**（Luna 28）。本番は `kernel/kikai.py` の「数え上げ」（「何通り」で振り分け）、物差しは `KERNEL_KAZOERU=1`。**同じ設定でも ±2問ぶれる**（同文脈 12↔14）。
128問（Actions x64/ARM）: 旧版 90 → **旧版＋電卓 113/109・平均 21秒（32→速くなった）**／2507版＋電卓 114/113・27〜30秒 → 2507 は +2〜3 で 3割遅いので**差し替えない**（9/23）。
**似た手本（`KERNEL_TEHON=1`、`kernel/tehon.jsonl` 716件＝Luna と無料の先生が作り別の先生が検品）**: 本番の同文脈 32問で 19→23（5問○に・1問×に）。128問の確かめは Actions `hakaru-zenbu-k-t`。
**★8段（新しい物差し・`monosashi/mondai_8dan.jsonl` 127問・Luna 作／Luna 検品）で 7段への合わせすぎが見えた（9/23）**: 素 99/107 → 電卓＋手本 100/98、電卓＋計算電卓 65/63。手本は 7段の後戻りを 30→13 に壊す。計算電卓は 7段の同文脈を 32/32 にするが 8段の速さ・時刻・推理で大崩れ。→ **本番は数え上げ電卓だけ・並べ方（隣・列・席）は除く**。手本と計算電卓は入れない。**1つの物差しだけ見て決めない**。8段の目標＝Luna（別呼び出し・max）**125/127**。
**公式 GSM8K（`monosashi/mondai_gsm8k.jsonl` 1319問、枝 `hyou-gsm8k` で 12台に分けて約1時間）: 93.2%（1229）・15.6秒**。公表値 91.8%（BF16・4-shot）を Q2_K・0-shot で上回る。
**道具（`kazoeru.py` の erabu/toku。物差しと本番で同じ関数）**: 数え上げ・時刻・並べ方（他N 可）・選び方。**B（練習に使った）では 99/107→113/117 だが、未見の C では 106/102→107/105（+2）**。C の Luna 126/126、差は 速さ 9↔14・時刻 6〜9↔16。**練習に使った物差しの伸びは信じない。次の未見 D を作って確かめる**。
**LoRA（`lora/tehon-lora.gguf`、教材1007件・1エポック・約$6）は不採用**: C 104→74、A 90→63（後戻り 29→3）。短い解き方（使う/使わない/式）を覚えて途中の計算を省くようになった＝手本を添えたときと同じ病気。**教材を作るなら途中の計算を全部書いた長い解き方に**。未見のテストD の基準 104/101。差は 時刻 4〜6↔15・並べ方 9〜13↔16・推理 11〜13↔14。

## 二人で回す（Claude Code ＋ Codex）
作る → 測る → Codex 審査 → 直す → 測る。`dougu/shinsa.sh <名> "<頼み>"`（gpt-6-luna・max・読み取り専用、約6分）。**Codex は repo を読めないことがある**ので、見せたいソースは頼み文に貼る。指摘は資料（測って採用）。

## 外の計算資源
| どこ | 使い方 | 実測 |
|---|---|---|
| **GitHub Actions**（公開 repo は無料・無制限、x64/ARM 4コア16GB） | `git push -f origin main:hakaru`（3問）／`hakaru-zenbu`（128問）／末尾 `-f1` `-f2`（深さ）／`hakaru-henka`（`dougu/actions_henka.txt` の起動指定）→ 枝 `kekka`。待つのは `dougu/actions_matsu.sh` | 7段 91/128（Mac 92）、128問 1.5時間 |
| **Google Cloud**（L4） | `gcloud/ryoushika.sh <HF名> 4` → imatrix Q2_K を作って手元へ（自動消滅・約 $2・1.5時間） | imatrix は効かず（30B 88/128） |
| Groq／NVIDIA（無料） | 教材と検品の先生。`~/.claude/scripts/groq.sh`、`kernel/nvidia.py`（`nv ask -m super`。承認ダイアログは廃止済み） | 頭脳の代わりにはならない |
| Modal／Oracle・Kaggle・Cloudflare・HF・TPU | Modal は GPU にカード要（保留）。他は未登録。TPU は llama.cpp が動かない | — |

**穴**: 裏で `codex exec` を呼ぶときは `< /dev/null`（無いと標準入力を待って固まる。9/23 に 48分止まった）／GCP は 既定 SA に GCS 権限が要る／`a && b` は set -e でも止まらない／CUDA は `/usr/local/cuda/bin`／合図が 12分来なければ VM を消す。llama.cpp 本家は Xing4.0（TeleChat 系）に未対応。不採用の 35B は SSD `LocalAI/models_hokan/` に移した（9/23）。教材（本）は `kernel/tehon.jsonl`（SSD にも写す）。LoRA（`gcloud/lora.sh`）は 1歩 130秒・損失 15.6 始まりで中止＝読み込みか版がおかしい。次は短い試し（--probe）で切り分けてから。
