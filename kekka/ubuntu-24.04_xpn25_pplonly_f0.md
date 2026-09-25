# ubuntu-24.04_xpn25_pplonly_f0  2026-09-25T06:39:53Z
```
llama.cpp b31b71f / koukai 8f8d20b / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/pn25.env
生成設定 temperature=0
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         20.31 ± 4.57 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         16.48 ± 1.34 |

build: b31b71f3a (10872)
剪定の最大メモリ: 13.36 GiB（14007612 KiB）
ニューロン剪定 0.25: 24G
作り直し: Q2_K / 9.0G / 所要 1003秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   8.93 GiB |    23.28 B | CPU        |       4 |           pp512 |         25.85 ± 3.20 |
| qwen3moe 30B.A3B Q2_K - Medium |   8.93 GiB |    23.28 B | CPU        |       4 |           tg128 |         18.56 ± 2.81 |

build: b31b71f3a (10872)
基準比 pp512: 1.273（実験 / 基準）
基準比 tg128: 1.126（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
5.24.209.188 I Final estimate: PPL = 10.0326 +/- 0.44012
探り: 読み 3.5 t/s（16字）・書き 11.1 t/s（128字）
所要 2695秒
