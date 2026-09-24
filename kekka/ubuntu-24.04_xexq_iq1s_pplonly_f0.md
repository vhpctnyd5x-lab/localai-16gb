# ubuntu-24.04_xexq_iq1s_pplonly_f0  2026-09-24T11:37:56Z
```
llama.cpp b31b71f / koukai bf00ed1 / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/exq_iq1s.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   87G  41% /
```
作り直し: Q2_K / 6.0G / 所要 2120秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   5.98 GiB |    30.53 B | CPU        |       4 |           pp512 |         26.05 ± 0.06 |
| qwen3moe 30B.A3B Q2_K - Medium |   5.98 GiB |    30.53 B | CPU        |       4 |           tg128 |          9.72 ± 0.04 |

build: b31b71f3a (10872)
