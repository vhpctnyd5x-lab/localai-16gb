# ubuntu-24.04_spd06_pplonly_f0  2026-09-24T14:43:50Z
```
llama.cpp b31b71f / koukai b1fe459 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: INTEL(R) XEON(R) PLATINUM 8573C
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
草稿 23749fefcc72300e3a2ad315e1317431b06b590a / sha256 9465e63a22ad / 指定 -md /home/runner/work/_temp/hakaru/Qwen3-0.6B-Q8_0.gguf --spec-draft-n-max 8 --spec-type draft-simple,ngram-simple --spec-ngram-simple-size-m 16
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         15.02 ± 2.83 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         10.40 ± 0.51 |

build: b31b71f3a (10872)

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         15.09 ± 1.07 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         10.35 ± 0.92 |

build: b31b71f3a (10872)
基準比 pp512: 1.005（実験 / 基準）
基準比 tg128: 0.995（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
10.05.330.310 I Final estimate: PPL = 7.8222 +/- 0.33095
探り: 読み 0.6 t/s（16字）・書き 1.9 t/s（128字）
所要 1539秒
