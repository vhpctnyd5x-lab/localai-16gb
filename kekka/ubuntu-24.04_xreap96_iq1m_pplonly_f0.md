# ubuntu-24.04_xreap96_iq1m_pplonly_f0  2026-09-24T15:30:11Z
```
llama.cpp b31b71f / koukai 1cfd9ab / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/reap96_iq1m.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: Intel(R) Xeon(R) Platinum 8370C CPU @ 2.80GHz
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         17.02 ± 2.16 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         10.42 ± 0.05 |

build: b31b71f3a (10872)
作り直し: Q2_K / 6.7G / 所要 8312秒
専門家を 96 個に手術: 5.2G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   5.12 GiB |    23.28 B | CPU        |       4 |           pp512 |         28.14 ± 0.08 |
| qwen3moe 30B.A3B Q2_K - Medium |   5.12 GiB |    23.28 B | CPU        |       4 |           tg128 |          7.19 ± 0.01 |

build: b31b71f3a (10872)
基準比 pp512: 1.653（実験 / 基準）
基準比 tg128: 0.690（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
5.25.773.022 I Final estimate: PPL = 10.3944 +/- 0.42853
探り: 読み 11.2 t/s（16字）・書き 6.6 t/s（128字）
所要 9819秒
