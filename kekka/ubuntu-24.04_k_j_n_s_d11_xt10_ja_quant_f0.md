# ubuntu-24.04_k_j_n_s_d11_xt10_ja_quant_f0  2026-09-26T11:11:03Z
```
llama.cpp b31b71f / koukai bd2a117 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t10_ja_quant.env
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         21.30 ± 5.18 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         17.24 ± 0.16 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
12.46.671.966 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
12.46.671.967 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (85.94%)
12.46.671.968 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.94%)
12.46.671.969 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.06%)
12.46.671.970 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
12.46.671.973 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
12.46.671.973 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
12.46.671.974 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (85.94%)
12.46.671.975 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (85.94%)
12.46.671.976 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.06%)


較正 imatrix: 0517237453cee6085453ee29e88eb3c20e0841bea375262b2b2c4c00951696d5  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.7G / 所要 4746秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.67 GiB |    30.53 B | CPU        |       4 |           pp512 |         37.37 ± 0.06 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.67 GiB |    30.53 B | CPU        |       4 |           tg128 |         10.94 ± 0.01 |

build: b31b71f3a (10872)
基準比 pp512: 1.754（実験 / 基準）
基準比 tg128: 0.635（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
4.18.969.612 I Final estimate: PPL = 8.1043 +/- 0.32338
探り: 読み 15.7 t/s（16字）・書き 10.5 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 79.2,
  "平均秒": 23.9
 },
 "正解率": 79.2,
 "平均秒": 23.9,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 4
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_xt10_ja_quant_f0.json
```
所要 9569秒
