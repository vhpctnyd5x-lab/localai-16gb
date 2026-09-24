# ubuntu-24.04_xvocab9999_pplonly_f0  2026-09-24T15:11:46Z
```
llama.cpp b31b71f / koukai b1fe459 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab9999.env
vocab keep /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab_keep_9999_ids.txt
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.27 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.06 ± 0.03 |

build: b31b71f3a (10872)

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.25 ± 0.02 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.84 ± 0.04 |

build: b31b71f3a (10872)
基準比 pp512: 0.999（実験 / 基準）
基準比 tg128: 1.055（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
7.58.698.119 I Final estimate: PPL = 7.7997 +/- 0.33027
探り: 読み 16.4 t/s（16字）・書き 13.8 t/s（128字）
所要 1057秒
