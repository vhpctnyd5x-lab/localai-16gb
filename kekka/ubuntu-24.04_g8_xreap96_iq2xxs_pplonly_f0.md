# ubuntu-24.04_g8_xreap96_iq2xxs_pplonly_f0  2026-09-25T06:33:28Z
```
llama.cpp b31b71f / koukai 3e922cf / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/reap96_iq2xxs.env
メモリ上限 8 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.36 ± 0.02 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.42 ± 0.03 |

build: b31b71f3a (10872)
作り直し: Q2_K / 7.7G / 所要 5829秒
専門家を 96 個に手術: 6.0G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   5.92 GiB |    23.28 B | CPU        |       4 |           pp512 |         24.03 ± 0.02 |
| qwen3moe 30B.A3B Q2_K - Medium |   5.92 GiB |    23.28 B | CPU        |       4 |           tg128 |          8.74 ± 0.02 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 6610731008 bytes; pgmajfault: 99
基準比 pp512: 1.241（実験 / 基準）
基準比 tg128: 0.606（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 7626182656 bytes; pgmajfault: 107
6.58.358.520 I Final estimate: PPL = 8.8062 +/- 0.35271
探り: 読み 12.1 t/s（16字）・書き 8.0 t/s（128字）
llama-server cgroup memory.peak: 7316439040 bytes; pgmajfault: 184
所要 7397秒
