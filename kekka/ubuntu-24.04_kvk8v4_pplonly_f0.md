# ubuntu-24.04_kvk8v4_pplonly_f0  2026-09-24T12:01:47Z
```
llama.cpp b31b71f / koukai f83e090 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 747aa9c1df41
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |   q8_0 |   q4_0 |   1 |           pp512 |         20.08 ± 0.86 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |   q8_0 |   q4_0 |   1 |           tg128 |         15.27 ± 1.33 |

build: b31b71f3a (10872)
