# AGENTS.md — この場所で働く AI（Claude Code・Codex CLI）の共通の決めごと

本人（開発者）の合言葉は **早い・安い・賢い**。全体の決めごとは `~/.codex/AGENTS.md`（Claude は `~/.claude/CLAUDE.md` が取り込む）。この紙はこの仕事場の分。Claude は横の `CLAUDE.md`（`@AGENTS.md` の 1行）から読む。

## 場所
- 正は内蔵 `~/LocalAI_mirror/{kernel,koukai,llama-latest,models}`。外部 SSD は **写し**（`koukai/dougu/utsusu.sh` で片方向）。SSD は日に何度も切れる。
- `kernel/` = 本体（git 外）。`koukai/` = 公開の写し（git・GitHub main）。kernel を直したら `koukai/dougu/` に写す。
- 物差し（測る台本）は `koukai/dougu/hakaru_*.py`、走らせる台本は `hashiru_*.sh`、結果は `koukai/dougu/kekka/`（git 外）。

## この仕事場の決めごと（全体の分は ~/.codex/AGENTS.md）
1. 新しい仕組みは held-out の物差しで測り、数字が良くなければ入れない。
2. Codex は `koukai` の main に push しない・kernel/ を書き換えない。読み取り専用か別の作業場（worktree）で。同じファイルを二人で同時に触らない。
3. 鍵は `~/.groq.env`・`~/.nvidia.env`（本人が置いた）と macOS キーチェーン。台本が読む。
4. 手元の頭脳（llama-server）は 1本だけ・8080（16GB）。物差しの台本が立てて消す。
5. GCP の VM は自分から消える指定で作る。GUI の操作は道具（コマンド）で済むなら GUI を使わない。

## 二人で回す（Claude Code ＋ Codex CLI）
- 1周 = 作る → 測る → Codex 審査 → 直す → 測る。Codex は審査役（測り方の穴・不具合）と出題役（独立した held-out）。
- 呼び方: `codex exec -m gpt-5.6-terra -c model_reasoning_effort=max -s read-only -C ~/LocalAI_mirror/koukai -o <出力> "<頼み>"`（luna でも可。**ultra max・multi_agent は使わない**＝本人の指示 9/19）。
- 目安: 審査 1回 ≈ 6分・100万トークン（9割はキャッシュ）。ChatGPT Plus の週の枠は 1回で 1% ほどしか減らない（9/18 実測 24%→25%）。
- Codex は kernel/ を書き換えない。実装を任せるなら別の作業場（worktree）で。

## 雲の先生（無料 API）を呼ぶ
- Groq: `~/.claude/scripts/groq.sh -m openai/gpt-oss-120b "頼み"`（鍵は台本が ~/.groq.env から読む）。実測 150 tokens/秒。
- NVIDIA NIM: `python3 ~/LocalAI_mirror/kernel/nvidia.py`（呼び名 fast／super／code／deep、鍵は ~/.nvidia.env）。`nv ask` はキーチェーン＋承認ダイアログの道（無人では使わない）。
- 両方を同じ物差しで測る台本: `koukai/dougu/hakaru_kumo.py --sensei groq:openai/gpt-oss-120b|nvidia:fast --mondai ../monosashi/mondai_7dan.jsonl`
- Python の urllib はそのままだと Groq の Cloudflare に弾かれる（403 1010）→ User-Agent を付ける。

## 借りられる計算資源（2026-09-19 調べ。★＝今の用途に合う。数字は各社の頁の値・変わる）
| どこ | ただで | 向く用途 | 登録 |
|---|---|---|---|
| ★GitHub Actions | 公開 repo は無制限（Linux 4コア 16GB・空き 14GB・1本 6時間・ARM も可） | 物差しを Mac の外で走らせる（頭脳 11GB は HF から落とす。掃除で空きを増やす） | 済み。`gh` の鍵は切れ→本人が `gh auth refresh` |
| ★Google Cloud | 無料クレジット。L4 24GB（g2-standard-8） | imatrix・量子化（`gcloud/ryoushika.sh`） | 済み |
| ★Modal | 月 $30 分（H100 $3.95/h・A100 80GB $2.50/h・L4 $0.80/h・T4 $0.59/h、秒課金、GPU 同時 10） | imatrix・量子化・比較を H100 で 30分 | **未**（GitHub/Google で入る→本人が `modal setup`） |
| ★Oracle Always Free | ARM 4コア 24GB をずっと無料（+ 200GB 盤） | 同じ頭脳を Mac の外で常時（PC の資源を使わない） | **未**（カード要・GUI。空きが無い地域あり） |
| Kaggle | GPU T4×2 を週 30時間、TPU も。`kaggle kernels push` で無人実行 | Modal の予備 | **未**（電話認証） |
| Cloudflare Workers AI | 日 1万ニューロン（gpt-oss-120b なら入力 30万 tok／日ほど） | Groq が枠切れの時の先生 | **未**（メール） |
| Hugging Face | Spaces CPU 2コア 16GB は常時無料。ZeroGPU は要確認 | 頭脳の公開デモ（遅い） | 未（ログイン無し） |
| TPU（Kaggle・Colab・TRC） | ある | **今は無し**（llama.cpp は TPU で動かない。学習をやる時に） | — |
| Colab・Lightning・Codespaces・Azure・AWS・Railway | ある | GUI 専用か上と重なる → 後回し | — |

## Google Cloud
- `~/google-cloud-sdk/bin/gcloud`、アカウントは gcloud に設定済み（`gcloud config get account`）、プロジェクト `project-33e6be3b-57e3-4568-b34`、既定 `us-central1-a`、通貨 JPY。
- 借りられる GPU: `g2-standard-8`（L4 24GB）1台。**必ず** `--max-run-duration=Nh --instance-termination-action=DELETE --boot-disk-auto-delete`。長い仕事は SPOT でなく STANDARD。
- 予算アラートは知らせるだけで止めない。終わったら `gcloud compute instances list` と `disks list` が空なのを確かめる。

## 手元の頭脳の土台（2026-09-18）
Qwen3-30B-A3B Q2_K（11.3GB）、`-t 6 -ngl 0 -dev none -c 8192 -np 1 -cb -ub 256 --cache-reuse 16 -fa off --spec-type ngram-simple`。読み込み 41 t/s・書き出し 12 t/s。CPU の上限は 35 t/s なので「何百 t/s」は雲の先生の仕事。
