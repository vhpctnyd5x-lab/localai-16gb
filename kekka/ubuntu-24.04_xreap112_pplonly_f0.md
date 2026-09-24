# ubuntu-24.04_xreap112_pplonly_f0  2026-09-24T12:45:55Z
```
llama.cpp b31b71f / koukai ff0775c / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 1a2b1d653f2a
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/reap112.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
専門家を 112 個に手術: 9.3G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   9.25 GiB |    26.91 B | CPU        |       4 |           pp512 |         19.46 ± 0.02 |
| qwen3moe 30B.A3B Q2_K - Medium |   9.25 GiB |    26.91 B | CPU        |       4 |           tg128 |         14.60 ± 0.16 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
