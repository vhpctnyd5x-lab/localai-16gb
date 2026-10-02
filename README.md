# LocalAI 16GB Mac

16GB・GPU なしの Intel Mac で、ローカルの AI に Mac の仕事（ファイルの整理・読み書き・状態の確認・調べもの）をさせる実験と道具です。
合言葉は **「早い・安い・賢い」**。モデルを大きくせず、仕組みと道具で賢くできるかを測りながら進めています。

- **頭脳**（ローカル LLM）: Qwen3.6-35B-A3B。専門家を 256人 → 160人 に削った 7.7GiB 版（元は 11.7GiB）。
- **カーネル**（手下）: 頭脳が呼ぶ道具と、危ない操作を止める門番。命令は `sandbox-exec` で隔離し、消す・送るなどは本人の承認が要ります。
- **事前学習**: 空いた時間に Wikipedia の記事を読み、知識の箱に貯めて答えに使います。

## いまの姿（2026-10-02）

| 測ったもの | 結果 | メモ |
|---|---|---|
| PC 操作の自作テスト（全41問、J27〜41 は未見） | 39/41（160人版）。元の 11.7GiB 版は 37/41 | 1回ごとに±2問ぶれる |
| 知識の問い（25問） | 23/25（元 24/25） | 事前学習の知識だけで答える |
| 書く速さ | 8.1〜9.1 字/秒（元 8.3〜8.6） | 変わらない |
| 頭脳のメモリ | 8.0〜8.2GB（元 9.6〜10.0GB） | 頼みの控えを 512MB に絞り、自前の分は最大 2.0GB |
| 最初の頼みで読み直す量 | 268トークン・9秒（前は 1,755トークン・83秒） | 立ち上げ時に前置きを先に読む |

数字はすべてこの Mac・この条件での1回の測定です。経緯と細かい数字は [dougu/jikken/KEKKA.md](dougu/jikken/KEKKA.md)。

## 最近わかったこと

- **専門家を削っても賢さはほぼ落ちない**: 層ごとに、使われる回数（imatrix）の少ない専門家から外した。192人・160人とも知識・全41問はぶれの範囲。道具は [dougu/kezuru_tejun.py](dougu/kezuru_tejun.py)、[dougu/senmonka_kezuru.py](dougu/senmonka_kezuru.py)。
- **llama-server の既定は RAM を食う**: 頼みの控え（`--cache-ram`）が既定 8GB で、使い続けると自前の分が 4〜6GB に膨らんだ。`-cram 512` で最大 2.0GB。
- **計算や写し間違いは門番が直す**: 書いた CSV を読んだファイルと照らし、合計も計算し直して、違えば直した中身を頭脳に渡す（J14・J17・J25 が通るようになった）。
- **数学の物差しでの昔の結論**（30B 時代）: 数え上げをプログラムに任せると大きく伸びた（32問で 4 → 31）。量子化の違いは飽和した問題集では差が見えなかった。詳しくは [LOG.md](LOG.md)・[RESULTS.md](RESULTS.md)。

## フォルダの地図

| 場所 | 中身 |
|---|---|
| [kernel/](kernel/) | カーネルの写し（アプリの server.py・画面 ui.html・事前学習・試験）。本番は git の外にあり、ここから入れる |
| [dougu/](dougu/) | 測る・入れる・調べる道具。輪（頭脳が道具を呼ぶ仕組み）は [dougu/jiyuu.py](dougu/jiyuu.py) |
| [monosashi/](monosashi/) | 物差し（問題集と採点）。全41問は [monosashi/jiyuu.jsonl](monosashi/jiyuu.jsonl) |
| [llama_patch/](llama_patch/) | 圧縮入りの llama.cpp に当てる差分（語彙を 99.99% に絞るなど） |
| [experiments/](experiments/)・[lib/](lib/) | 8月の量子化・圧縮の研究（古い。状態は [EXPERIMENTS.md](EXPERIMENTS.md)） |
| [gcloud/](gcloud/)・[modal/](modal/)・[lora/](lora/) | クラウドで試した量子化・LoRA（不採用） |

## 説明の紙

| 紙 | 何が書いてあるか |
|---|---|
| [dougu/jikken/KEKKA.md](dougu/jikken/KEKKA.md) | **いちばん新しい実験の記録**（日付順） |
| [MODEL.md](MODEL.md) | 使っているモデルが何であって、何ではないか |
| [ANZEN.md](ANZEN.md) | 断る力（安全性）の測定 |
| [YOUGO.md](YOUGO.md) | 独自の呼び方と一般の用語の対応表 |
| [LOG.md](LOG.md) | 9月までの実験の経緯と訂正（README 旧版の本文） |
| [RESULTS.md](RESULTS.md) | 8月の量子化の測定結果 |
| [EXPERIMENTS.md](EXPERIMENTS.md) | `experiments/`・`lib/` の状態（正直な点検） |
| [NOTES.md](NOTES.md) | 古い研究ノート |
| [AGENTS.md](AGENTS.md) | AI（Claude Code・Codex）向けの仕事の決めごと |

## 動かしかた（いまの頭脳）

1. Hugging Face の `unsloth/Qwen3.6-35B-A3B-GGUF` から `UD-Q2_K_XL` を落とす（約 12.6GB）。
2. llama.cpp（b31b71f）に [llama_patch/](llama_patch/) を当てて建てる。`llama-imatrix` も一緒に建てる。
3. 削る: `python3 dougu/kezuru_tejun.py --dan kezuru`（校正文で imatrix を作り、192人・160人版を作って一問と知識25問で確かめる）。
4. 立てる: `llama-server -m 削った.gguf -t 6 -ngl 0 -c 32768 -np 2 -kvu --no-cache-idle-slots -cram 512 -fa off --reasoning-format none`

<details>
<summary>30B 時代の始め方（考える深さを試す・特別なモデル不要）</summary>

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp && git checkout fa67698 && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cd ..
curl -L -o Qwen3-30B-A3B-Q2_K.gguf \
  https://huggingface.co/unsloth/Qwen3-30B-A3B-GGUF/resolve/main/Qwen3-30B-A3B-Q2_K.gguf
./llama.cpp/build/bin/llama-server -m Qwen3-30B-A3B-Q2_K.gguf -ngl 0 -c 8192 -np 1 -cb \
  --spec-type ngram-simple -ctk q8_0 -ctv q8_0 --host 127.0.0.1 --port 8080
python3 kangaeru_fukasa.py "12個のりんごを3人で分けて、余りは箱に戻します。余りは何個？"
```

Python 側は標準ライブラリだけ。深さ 0〜3 を順に試して秒数と一緒に出します。問題集で測るなら `monosashi/tsukuru.py --kazu 120` → `monosashi/hakaru.py --fukasa 2`。
</details>

## 測り方

- 自作の問題集で測り、見た問題で伸びたものは未見の問題でも確かめる。1回の数字は1回の数字として読む。
- 速さ・正解率は、同じ機械・同じ条件の基準との比で読む。
- 重い調査・実装は Codex、検証と組み込みは Claude Code。ローカルの頭脳には、カーネルや AI の仕組みは触らせない。

## ことわり

- 測定は Intel Mac・CPU 推論・16GB という特殊な条件です。Apple Silicon や GPU では、とくに速さの結論が変わります。
- モデルの重みは含みません。ライセンスは元モデル（Qwen）に従ってください。

## ライセンス

MIT（[LICENSE](LICENSE)）。実験コードと記録が対象で、モデルの重みは含みません。
