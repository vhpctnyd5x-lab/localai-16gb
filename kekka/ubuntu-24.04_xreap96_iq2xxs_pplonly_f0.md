# ubuntu-24.04_xreap96_iq2xxs_pplonly_f0  2026-09-24T15:29:58Z
```
llama.cpp b31b71f / koukai 1cfd9ab / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/reap96_iq2xxs.env
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.55 ± 0.02 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.75 ± 0.24 |

build: b31b71f3a (10872)
作り直し: Q2_K / 7.7G / 所要 5279秒
専門家を 96 個に手術: 6.0G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   5.92 GiB |    23.28 B | CPU        |       4 |           pp512 |         25.76 ± 0.10 |
| qwen3moe 30B.A3B Q2_K - Medium |   5.92 GiB |    23.28 B | CPU        |       4 |           tg128 |          9.24 ± 0.00 |

build: b31b71f3a (10872)
基準比 pp512: 1.318（実験 / 基準）
基準比 tg128: 0.626（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
6.16.486.689 I Final estimate: PPL = 8.8062 +/- 0.35271
探り: 読み 12.7 t/s（16字）・書き 8.8 t/s（128字）
所要 7194秒
