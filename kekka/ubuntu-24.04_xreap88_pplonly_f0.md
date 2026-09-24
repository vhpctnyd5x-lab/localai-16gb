# ubuntu-24.04_xreap88_pplonly_f0  2026-09-24T13:01:13Z
```
llama.cpp b31b71f / koukai 97c7133 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 1a2b1d653f2a
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/reap88.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
専門家を 88 個に手術: 7.5G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.41 GiB |    21.47 B | CPU        |       4 |           pp512 |         19.66 ± 0.03 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.41 GiB |    21.47 B | CPU        |       4 |           tg128 |         15.02 ± 0.13 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
8.14.955.048 I Final estimate: PPL = 8.6546 +/- 0.36380
探り: 読み 17.0 t/s（16字）・書き 15.4 t/s（128字）
所要 956秒
