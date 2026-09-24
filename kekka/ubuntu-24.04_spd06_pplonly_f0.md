# ubuntu-24.04_spd06_pplonly_f0  2026-09-24T13:00:52Z
```
llama.cpp b31b71f / koukai 97c7133 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 1a2b1d653f2a
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
草稿 23749fefcc72300e3a2ad315e1317431b06b590a / sha256 9465e63a22ad / 指定 -md /home/runner/work/_temp/hakaru/Qwen3-0.6B-Q8_0.gguf --draft-max 8 --draft-min 1 --spec-type draft-simple,ngram-simple --spec-ngram-simple-size-m 16

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.50 ± 0.05 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.72 ± 0.13 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
8.17.838.912 I Final estimate: PPL = 7.8099 +/- 0.33087
頭脳が立たない: -md /home/runner/work/_temp/hakaru/Qwen3-0.6B-Q8_0.gguf --draft-max 8 --draft-min 1 --spec-type draft-simple,ngram-simple --spec-ngram-simple-size-m 16
