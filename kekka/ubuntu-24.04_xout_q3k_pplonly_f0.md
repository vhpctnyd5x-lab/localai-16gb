# ubuntu-24.04_xout_q3k_pplonly_f0  2026-09-24T11:23:04Z
```
llama.cpp b31b71f / koukai bf00ed1 / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/out_q3k.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
作り直し: Q2_K / 11G / 所要 1491秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.37 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.60 ± 0.02 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.37 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.21 ± 0.07 |

build: b31b71f3a (10872)
