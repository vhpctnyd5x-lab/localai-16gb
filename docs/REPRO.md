# 再現に要るもの

現行の160人版を作り、同じ種類の測定を行うための記録です。実測値の履歴は [`dougu/jikken/KEKKA.md`](../dougu/jikken/KEKKA.md) を参照してください。

## 入力と道具

- Python: `python3 --version` で確認。この資料を作成した環境は **Python 3.14.5**。
- 元モデル: `Qwen3.6-35B-A3B-MTP-UD-Q2_K_XL.gguf`（約 11.7 GiB）。配布元は [Hugging Face の unsloth/Qwen3.6-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF) の `UD-Q2_K_XL`。
- llama.cpp: commit **`b31b71f`**。この作業場の [`llama_patch/koukai.patch`](../llama_patch/koukai.patch) を当てて構築し、`llama-server` と `llama-imatrix` を使う。パッチ内にも語彙選択などの実装がある。
- 派生モデル: `models/Qwen3.6-35B-A3B-UD-Q2_K_XL-k160.gguf`（約 7.7 GiB）。
- SHA256（Claude が記入）:
  - 160人版: `a5166e02dc0fbf5b86b01dbc546f3f17c9316dba334fc762220bb4d725c5691b`
  - 元モデル: `ed7cda7e38985b4fcff76475865135039641d2bfbac3c169df15ca770f37fb0c`

## 作成

1. 元モデルを `~/LocalAI_mirror/models/Qwen3.6-35B-A3B-MTP-UD-Q2_K_XL.gguf` に置き、b31b71f にパッチを適用して作った道具が `~/LocalAI_mirror/llama-koukai/` にある状態にする。
2. 校正文から imatrix を作り、192人版と160人版を作る。既定で一問・知識・全41問の確認も行う:

   ```bash
   python3 dougu/kezuru_tejun.py --dan kezuru
   ```

   この手順は [`dougu/kezuru_tejun.py`](../dougu/kezuru_tejun.py) が呼ぶ [`dougu/senmonka_kezuru.py`](../dougu/senmonka_kezuru.py) に従う。層ごとの imatrix 使用数を基準に選び、MTP を外す。再量子化はしない。

3. 語彙を絞るパッチ設定を含め、サーバーを起動する。`削った.gguf` は160人版のパスに置き換える:

   ```bash
   llama-server -m 削った.gguf -t 6 -ngl 0 -c 32768 -np 2 -kvu \
     --no-cache-idle-slots -cram 512 -fa off --reasoning-format none
   ```

   語彙選択は `KOUKAI_VOCAB_KEEP=vocab_keep_9999_q36_ids.txt`、先読みは `--spec-type none`。本番構成の詳細は [`AGENTS.md`](../AGENTS.md) を参照。

## 測定

- 全41問の公開回帰テスト: `python3 dougu/honban.py j`。
- 知識25問: `python3 dougu/chishiki_wa.py --toi <知識問題JSONL> --model <モデル.gguf> --llama <llama-server>`。
- 書く速さ: `python3 dougu/hayasa.py --model <モデル.gguf> --llama <llama-server> --conf 現行:<サーバーに足す引数> --wa`。

問題・採点・実行条件の変更履歴も含め、1回の数字だけで一般化しないでください。モデルの SHA256 は空欄のままにしてあり、別途確認して記入します。
