# ubuntu-24.04_k_j_n_s_d11_xt8_imat_ja96_f0  2026-09-26T07:59:47Z
```
llama.cpp b31b71f / koukai 6efeda1 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t8_imat_ja96.env
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.50 ± 0.05 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.89 ± 0.01 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
16.06.736.053 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
16.06.736.054 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (86.72%)
16.06.736.055 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.16%)
16.06.736.056 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.06%)
16.06.736.057 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
16.06.736.060 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
16.06.736.061 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
16.06.736.063 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (88.28%)
16.06.736.064 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (88.28%)
16.06.736.065 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.06%)


較正 imatrix: 2eb5aa7c1922effc2068f555dcf83bb398b3b8a6afa74297f9a97092da3344e5  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.7G / 所要 5241秒
専門家を 96 個に手術: 6.0G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   5.92 GiB |    23.28 B | CPU        |       4 |           pp512 |         25.89 ± 0.04 |
| qwen3moe 30B.A3B Q2_K - Medium |   5.92 GiB |    23.28 B | CPU        |       4 |           tg128 |          9.24 ± 0.01 |

build: b31b71f3a (10872)
基準比 pp512: 1.328（実験 / 基準）
基準比 tg128: 0.621（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
6.16.327.291 I Final estimate: PPL = 8.4477 +/- 0.33441
探り: 読み 12.7 t/s（16字）・書き 8.4 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 56.0,
  "平均秒": 25.7
 },
 "正解率": 56.0,
 "平均秒": 25.7,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 13
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_xt8_imat_ja96_f0.json
```
所要 10632秒
