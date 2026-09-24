# ubuntu-24.04_xexq_iq1m_pplonly_f0  2026-09-24T13:16:58Z
```
llama.cpp b31b71f / koukai 97c7133 / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
llama patch sha256 1a2b1d653f2a
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/exq_iq1m.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: INTEL(R) XEON(R) PLATINUM 8573C
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
作り直し: Q2_K / 6.7G / 所要 8434秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   6.61 GiB |    30.53 B | CPU        |       4 |           pp512 |         31.86 ± 0.12 |
| qwen3moe 30B.A3B Q2_K - Medium |   6.61 GiB |    30.53 B | CPU        |       4 |           tg128 |          8.79 ± 0.09 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
5.08.446.238 I Final estimate: PPL = 9.7265 +/- 0.40254
探り: 読み 13.9 t/s（16字）・書き 7.8 t/s（128字）
所要 9589秒
