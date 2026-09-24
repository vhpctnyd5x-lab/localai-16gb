# ubuntu-24.04_xsl2_pplonly_f0  2026-09-24T12:30:40Z
```
llama.cpp b31b71f / koukai ff0775c / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 1a2b1d653f2a
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/sl2.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          11           0           2          14
/dev/root       145G   59G   86G  41% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         20.29 ± 0.04 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.29 ± 0.05 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
7.48.474.262 I Final estimate: PPL = 12.7026 +/- 0.55844
探り: 取れなかった
所要 898秒
