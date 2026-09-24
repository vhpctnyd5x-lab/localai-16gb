# ubuntu-24.04_k_j_n_s_d12_xq2k_jibun_f0  2026-09-24T14:18:21Z
```
llama.cpp b31b71f / koukai 908d6f2 / 問題 b7a44aa92e05 / 頭脳 a68fe7343b0c
llama patch sha256 1a2b1d653f2a
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/q2k_jibun.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: INTEL(R) XEON(R) PLATINUM 8573C
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
作り直し: Q2_K / 11G / 所要 1550秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.81 ± 0.40 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         11.52 ± 0.11 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
7.48.702.549 I Final estimate: PPL = 7.6319 +/- 0.31475
探り: 読み 3.9 t/s（16字）・書き 9.0 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段12": {
  "件": 47,
  "正解率": 80.9,
  "平均秒": 35.3
 },
 "正解率": 80.9,
 "平均秒": 35.3,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 2
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d12_xq2k_jibun_f0.json
```
所要 4451秒
