# ubuntu-24.04-arm_k_j_n_s_d11_xt9_gu_iq1m_f0  2026-09-26T10:50:04Z
```
llama.cpp b31b71f / koukai 5048ee9 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t9_gu_iq1m.env
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
Vendor ID:                               ARM
Model name:                              Neoverse-N2
               total        used        free      shared  buff/cache   available
Mem:              15           1          13           0           1          14
/dev/root       145G   37G  108G  26% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.57 ± 0.00 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.61 ± 0.06 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
作り直し: Q2_K / 7.0G / 所要 3663秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   6.96 GiB |    30.53 B | CPU        |       4 |           pp512 |         11.63 ± 0.00 |
| qwen3moe 30B.A3B Q2_K - Medium |   6.96 GiB |    30.53 B | CPU        |       4 |           tg128 |         10.92 ± 0.04 |

build: b31b71f3a (10872)
基準比 pp512: 0.798（実験 / 基準）
基準比 tg128: 0.802（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
11.59.752.669 I Final estimate: PPL = 9.0928 +/- 0.37627
探り: 読み 12.9 t/s（16字）・書き 10.4 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 71.2,
  "平均秒": 27.6
 },
 "正解率": 71.2,
 "平均秒": 27.6,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 2
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04-arm_k_j_n_s_d11_xt9_gu_iq1m_f0.json
```
所要 8825秒
