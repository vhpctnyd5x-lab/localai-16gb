# ubuntu-24.04_xedp70_pplonly_f0  2026-09-24T14:43:43Z
```
llama.cpp b31b71f / koukai b1fe459 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/edp70.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         21.77 ± 2.94 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.73 ± 1.16 |

build: b31b71f3a (10872)

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         23.00 ± 1.06 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         16.45 ± 0.30 |

build: b31b71f3a (10872)
基準比 pp512: 1.056（実験 / 基準）
基準比 tg128: 1.046（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
7.27.653.661 I Final estimate: PPL = 7.8396 +/- 0.33221
探り: 読み 2.6 t/s（16字）・書き 7.0 t/s（128字）
所要 1028秒
