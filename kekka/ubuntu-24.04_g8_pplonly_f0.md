# ubuntu-24.04_g8_pplonly_f0  2026-09-24T13:00:50Z
```
llama.cpp b31b71f / koukai 97c7133 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 1a2b1d653f2a
メモリ上限 8 GB（swap なし、mmap ページキャッシュを含む）
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   87G  41% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         16.58 ± 0.16 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |          4.39 ± 0.66 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 8589934592 bytes; pgmajfault: 227166

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 8589934592 bytes; pgmajfault: 77089
10.27.990.047 I Final estimate: PPL = 7.8300 +/- 0.33154
探り: 読み 2.3 t/s（16字）・書き 2.3 t/s（128字）
llama-server cgroup memory.peak: 8589934592 bytes; pgmajfault: 148121
所要 1258秒
