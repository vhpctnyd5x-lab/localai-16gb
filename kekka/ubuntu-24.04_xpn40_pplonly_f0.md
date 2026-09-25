# ubuntu-24.04_xpn40_pplonly_f0  2026-09-25T06:39:55Z
```
llama.cpp b31b71f / koukai 8f8d20b / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/pn40.env
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.29 ± 0.09 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.95 ± 0.14 |

build: b31b71f3a (10872)
剪定の最大メモリ: 13.59 GiB（14248772 KiB）
ニューロン剪定 0.40: 19G
作り直し: Q2_K / 7.2G / 所要 857秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.10 GiB |    18.45 B | CPU        |       4 |           pp512 |         27.64 ± 0.08 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.10 GiB |    18.45 B | CPU        |       4 |           tg128 |         18.42 ± 0.11 |

build: b31b71f3a (10872)
基準比 pp512: 1.433（実験 / 基準）
基準比 tg128: 1.320（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
5.51.219.855 I Final estimate: PPL = 14.3614 +/- 0.66702
探り: 読み 25.7 t/s（16字）・書き 12.5 t/s（128字）
所要 2424秒
