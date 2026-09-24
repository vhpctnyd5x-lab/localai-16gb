# ubuntu-24.04_xrf16_pplonly_f0  2026-09-24T14:43:45Z
```
llama.cpp b31b71f / koukai b1fe459 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/rf16.env
変換 gguf_router_f16.py
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         24.00 ± 0.45 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         16.59 ± 0.04 |

build: b31b71f3a (10872)

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.46 GiB |    30.53 B | CPU        |       4 |           pp512 |         23.53 ± 0.75 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.46 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.29 ± 1.21 |

build: b31b71f3a (10872)
基準比 pp512: 0.980（実験 / 基準）
基準比 tg128: 0.922（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
6.45.870.020 I Final estimate: PPL = 7.8239 +/- 0.33111
探り: 読み 2.9 t/s（16字）・書き 11.1 t/s（128字）
所要 1070秒
