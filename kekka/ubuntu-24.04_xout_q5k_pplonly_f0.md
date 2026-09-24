# ubuntu-24.04_xout_q5k_pplonly_f0  2026-09-24T13:18:07Z
```
llama.cpp b31b71f / koukai 97c7133 / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
llama patch sha256 1a2b1d653f2a
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/out_q5k.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
作り直し: Q2_K / 11G / 所要 1395秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.44 GiB |    30.53 B | CPU        |       4 |           pp512 |         21.53 ± 2.56 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.44 GiB |    30.53 B | CPU        |       4 |           tg128 |         16.69 ± 0.20 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
7.29.074.549 I Final estimate: PPL = 7.6647 +/- 0.31643
探り: 読み 5.4 t/s（16字）・書き 9.0 t/s（128字）
所要 2636秒
