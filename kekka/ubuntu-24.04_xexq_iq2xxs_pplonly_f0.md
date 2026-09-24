# ubuntu-24.04_xexq_iq2xxs_pplonly_f0  2026-09-24T13:01:30Z
```
llama.cpp b31b71f / koukai 97c7133 / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
llama patch sha256 1a2b1d653f2a
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/exq_iq2xxs.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
作り直し: Q2_K / 7.7G / 所要 5277秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.67 GiB |    30.53 B | CPU        |       4 |           pp512 |         25.09 ± 0.07 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.67 GiB |    30.53 B | CPU        |       4 |           tg128 |          9.07 ± 0.04 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
6.25.013.089 I Final estimate: PPL = 8.3922 +/- 0.33847
探り: 読み 12.2 t/s（16字）・書き 8.8 t/s（128字）
所要 6393秒
