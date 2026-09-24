# 自作テスト実験

`bash dougu/jikken_hashiru.sh 名前...` が `hakaru-zenbu-pplonly-x名前` の Actions を起動する push を行う。物差しも測る場合は後ろに `-d11-k-j-n-s` などを追加する。push は Claude がこの台本を実行する。

`KOUKAI_QTYPE` は Q8_0 から llama-quantize で作り直す型。`QOUT` は output.weight、`QEMB` は token embeddings、`QTT` は `テンソル名の正規表現:型` のカンマ列で、`--tensor-type` に渡す。再量子化では約32GBの Q8_0 と imatrix を一時取得し、lfs.oid の SHA256 を照合する。処理後に Q8_0 と imatrix を消し、所要時間・作成後サイズ・手術後サイズを結果 Markdown に記録する。

| 名前 | 部署 | 何を変えるか | 狙い |
|---|---|---|---|
| q2k_jibun | 基準 | Q8_0 から Q2_K を再量子化 | 配布 Q2_K とサイズ・PPLを比較 |
| pn10 / pn25 / pn40 | ニューロン | Q8_0 と imatrix を 0.10 / 0.25 / 0.40 剪定して Q2_K に再量子化 | ニューロン削減と品質の関係を見る。`prune_neurons.py` が必要 |
| edp90 / edp80 / edp70 | 専門家 | `KOUKAI_EXPERT_P` を .90 / .80 / .70 | 専門家の実行割合を変える |
| reap112 / reap96 / reap88 | 専門家 | 専門家を112 / 96 / 88個に剪定 | 専門家数と品質・容量の関係を見る |
| exq_iq2xxs | 専門家 | gate/up/down experts を IQ2_XXS | 専門家テンソルだけ小さくする |
| exq_iq1m / exq_iq1s | 専門家 | gate/up/down experts を IQ1_M / IQ1_S | 小さい型の影響を見る |
| reap96_iq2xxs / reap96_iq1m | 専門家 | 3種を追加量子化後、96個に剪定 | 圧縮の組み合わせを見る |
| sa4 / sa8 / sa12 | 注意 | 後方の4 / 8 / 12層（最後の47層を残し、43-46 / 39-46 / 35-46） | 後方 attention の寄与を見る |
| kvs8 | 注意 | KV share を後ろ8層（40-47）に指定 | KV共有の効果を見る |
| swa8 / swa16 | 注意 | 後ろ寄り 24-46 層を window 512 / 16-46 層を window 1024 に指定 | SWA の品質・速さを見る。対応するカーネル実装が必要 |
| hm25 | 注意 | 後ろ12層（35-46）の各層8ヘッドを指定 | ヘッド削減の影響を見る。対応するカーネル実装が必要 |
| attq2 | 注意 | `attn_` を含む tensor 名を Q2_K に指定 | attention 重みの型を揃える |
| vocab999 / vocab9999 / vocab99999 | 語彙 | 対応する vocab_keep ファイルで語彙を制限 | 語彙削減の影響を見る。ファイルは後置 |
| out_q4k / out_q3k / out_q5k | 出力 | output.weight を Q4_K / Q3_K / Q5_K | 出力テンソルの精度差を見る |
| rf16 | 案内係 | `gguf_router_f16.py` で router を F16 化 | router のサイズ・PPL差を見る |
| rq8 | 案内係 | `ffn_gate_inp` を Q8_0 | router を Q8_0 にして比較 |
| sl2 / sl4 / sl6 | 層 | 後ろ寄りの2 / 4 / 6層（45-46 / 43-46 / 41-46）を指定 | 層スキップの影響を見る |
| sf4 / sf8 | FFN | 後ろ4 / 8層（44-47 / 40-47）を指定 | FFNスキップの影響を見る |
| bi | BI記録 | `KOUKAI_BI_DUMP=1` | BI の測定結果を保存 |

`ek4` / `ek5` / `ek6` は既存の枝指定 `-e` を使う。

枝スイッチ `-kvk8v4` は K=q8_0 / V=q4_0、`-fa1` は f16 KV のまま FA 有効、`-nommap` / `-mlock` は全3種の llama 実行ファイルに適用、`-spd06` は 0.6B 草稿を使う。枝の名札にはそれぞれのスイッチ名が付く。
