# ubuntu-24.04_xreap96_pplonly_f0  2026-09-24T12:44:25Z
```
llama.cpp b31b71f / koukai ff0775c / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 1a2b1d653f2a
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/reap96.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: INTEL(R) XEON(R) PLATINUM 8573C
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
専門家を 96 個に手術: 8.1G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   8.02 GiB |    23.28 B | CPU        |       4 |           pp512 |         22.61 ± 0.09 |
| qwen3moe 30B.A3B Q2_K - Medium |   8.02 GiB |    23.28 B | CPU        |       4 |           tg128 |         12.54 ± 0.03 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
6.45.488.968 I Final estimate: PPL = 8.2835 +/- 0.34628
探り: 読み 19.1 t/s（16字）・書き 12.1 t/s（128字）
所要 832秒
