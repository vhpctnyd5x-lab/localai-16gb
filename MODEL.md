# モデルについて ── 何であって、何ではないか

> 「そのレイヤー、そのまま持ってきてないよね？」への答えは、今回も正直に書きます。これは公式配布のままのモデルではありません。

## いま使っているもの

`Qwen3.6-35B-A3B` の `UD-Q2_K_XL` を元に、専門家と補助的な予測層を選んで外し、語彙の読み込みを絞った派生モデルです。公式の Qwen3.6 そのものではありません。

| | 元モデル | いまのモデル |
|---|---|---|
| 配布名 | Qwen3.6-35B-A3B-MTP-UD-Q2_K_XL | `Qwen3.6-35B-A3B-UD-Q2_K_XL-k160.gguf` |
| 容量 | 約 11.7 GiB | 約 7.7 GiB |
| MoE 専門家 | 256人 | 160人 |
| 標準の層・注意機構 | — | 触っていない |
| MTP | 付属 | 補助的な MTP 層を外した |
| 量子化 | UD-Q2_K_XL | 元の量子化のまま（再量子化していない） |

専門家は校正文から作った imatrix の使用回数を層ごとに見て、よく使われるものを残しました。同数なら入力側の二乗和、さらに同じなら元の番号で選びます。256人から160人を残す手順は [`dougu/kezuru_tejun.py`](dougu/kezuru_tejun.py) と [`dougu/senmonka_kezuru.py`](dougu/senmonka_kezuru.py) にあります。

標準の層や注意機構を組み替えたわけではありません。一方で、MTP の補助層は削除しています。語彙もすべて残したままではなく、圧縮版 llama.cpp の [`llama_patch/koukai.patch`](llama_patch/koukai.patch) で必要な語彙を選び、99.99% に絞って読み込みます。これらの変更を含め、公式モデルと同一だとは主張しません。

削減後の測定値は1回ごとの結果です。10月3日の全41問は 36/41 と 38/41。条件と経緯は [`dougu/jikken/KEKKA.md`](dougu/jikken/KEKKA.md)、手順は [`docs/REPRO.md`](docs/REPRO.md) を参照してください。以前の30B版の説明は [`docs/archive/MODEL_qwen3-30b-reap96.md`](docs/archive/MODEL_qwen3-30b-reap96.md) に残しています。
