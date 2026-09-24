# ubuntu-24.04_xkumi1_kvk8v4_pplonly_f0  2026-09-24T16:31:54Z
```
llama.cpp b31b71f / koukai 3e922cf / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/kumi1.env
vocab keep /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab_keep_9999_ids.txt
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.61 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.12 ± 0.05 |

build: b31b71f3a (10872)

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |   q8_0 |   q4_0 |   1 |           pp512 |         17.36 ± 0.00 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |   q8_0 |   q4_0 |   1 |           tg128 |         15.85 ± 0.02 |

build: b31b71f3a (10872)
基準比 pp512: 0.885（実験 / 基準）
基準比 tg128: 1.048（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
9.26.851.399 I Final estimate: PPL = 7.7904 +/- 0.32827
探り: 読み 17.8 t/s（16字）・書き 15.3 t/s（128字）
所要 1150秒
