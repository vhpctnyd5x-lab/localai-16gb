# ubuntu-24.04_kvk8v4_pplonly_f0  2026-09-24T13:00:59Z
```
llama.cpp b31b71f / koukai 97c7133 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 1a2b1d653f2a
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |   q8_0 |   q4_0 |   1 |           pp512 |         17.13 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |   q8_0 |   q4_0 |   1 |           tg128 |         14.42 ± 0.02 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
8.08.311.971 I Final estimate: PPL = 7.8099 +/- 0.33087
探り: 読み 18.9 t/s（16字）・書き 14.2 t/s（128字）
所要 1151秒
