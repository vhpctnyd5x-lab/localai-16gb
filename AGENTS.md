# 仕事場（カーネル）— 共通規則は `~/.codex/AGENTS.md`
合言葉「早い・安い・賢い」。ローカルLLM＝頭（Qwen3.6-35B-A3B）、kernel＝手下（門番・道具・server.py）。詳しい版（30B・数学の物差し A〜D・外部計算資源・道具と教材）は `dougu/jikken/AGENTS_shousai.md`、経緯と数字は `dougu/jikken/KEKKA.md`、引き継ぎは `dougu/kekka/tsugi_0928.md`。

## 場所
正本は内蔵 `~/LocalAI_mirror/{kernel,koukai,llama-koukai,models}`（SSD は写し `dougu/utsusu.sh`）。`kernel/` は git 外の本番で、koukai の写しを `dougu/honban.py ireru` で入れ `kaiten` で開き直す（開き直しは聞かずにしてよい。10/2 本人）。結果は `dougu/kekka/`（git 外）。

## 頭脳（10/2〜）
`models/Qwen3.6-35B-A3B-UD-Q2_K_XL-k160.gguf`（専門家を160人に削った 7.7GiB。元の 11.7GB も残す。`dougu/kezuru_tejun.py`）。圧縮入り `llama-koukai/llama-server`、語彙 99.99%、先読みなし、`-np 2 -kvu --no-cache-idle-slots`（輪は枠0・横の仕事は枠1、立ち上げ時に輪の前置きを温める）、`-cram 512`（既定 8GB だと自前が 4〜6GB に膨らむ）。

## 物差し
全41問 `honban.py j`（`monosashi/jiyuu.jsonl`、J27〜41 は未見）、知識25問 `dougu/chishiki_wa.py`、速さ `dougu/hayasa.py --wa`。同じ設定でも±2問ぶれる。1回の数字で決めない。既見の伸びは信用しない。

## 方針・禁止
- 重い案・調査・実装は Codex（Luna 多め、Sol は難しい設計だけ。`< /dev/null`）、Claude は検証・組込。Codex は `kernel/` 変更と push 禁止。秘密鍵 `~/.groq.env` `~/.nvidia.env` は値を出さない。
- llama-server は1本・8080。外の待ちは `dougu/matsu.sh actions|gcp|pid`。GitHub Actions で測る枝 `hakaru-zenbu-*` は、結果が `kekka` 枝に入ったら消してよい（中身は main にある）。
- 本番に入れる前に、本番のファイルが前回入れた版のままか比べる。入れたら本物の場所で頼みを1つ動かす。試験は `KERNEL_*_DIR` で一時の場所へ（本番を汚さない）。
- `run_in_background` は既定30分で切れる。timeout を明示（最大2時間）、長い流れは段に分ける（10/2 g が途中で切れ、事前学習が切のまま残った）。
- 大量実行の前に1本を完走させる。同じ名前の関数を二つ置かない（10/2 温めが上書きされて呼ばれなかった。`kernel/tests/test_no_shadowing.py`）。
- 文脈を食う物を減らす: 道具の出力は tail/grep で短く、待ちは裏で1本、詳しい話は別の紙に置いて指し示す。使わない接続（Claude Docs・visualize）は切ってある（10/2）。
