# ubuntu-24.04_xout_q5k_pplonly_f0  2026-09-24T11:30:26Z
```
llama.cpp b31b71f / koukai bf00ed1 / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/out_q5k.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: Intel(R) Xeon(R) Platinum 8370C CPU @ 2.80GHz
               total        used        free      shared  buff/cache   available
Mem:              15           1          11           0           2          14
/dev/root       145G   59G   86G  41% /
```
作り直し: Q2_K / 11G / 所要 1695秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.44 GiB |    30.53 B | CPU        |       4 |           pp512 |         18.53 ± 0.12 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.44 GiB |    30.53 B | CPU        |       4 |           tg128 |         10.72 ± 0.09 |

build: b31b71f3a (10872)
