# ubuntu-24.04-arm_k_j_n_s_d12_xq2k_jibun_f0  2026-09-24T14:18:22Z
```
llama.cpp b31b71f / koukai 908d6f2 / 問題 b7a44aa92e05 / 頭脳 a68fe7343b0c
llama patch sha256 1a2b1d653f2a
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/q2k_jibun.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
Vendor ID:                               ARM
Model name:                              Neoverse-N2
               total        used        free      shared  buff/cache   available
Mem:              15           1          13           0           1          14
/dev/root       145G   37G  108G  26% /
```
作り直し: Q2_K / 11G / 所要 776秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.60 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.67 ± 0.15 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
9.34.353.483 I Final estimate: PPL = 7.6080 +/- 0.31411
探り: 読み 16.5 t/s（16字）・書き 12.9 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段12": {
  "件": 47,
  "正解率": 85.1,
  "平均秒": 33.8
 },
 "正解率": 85.1,
 "平均秒": 33.8,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 3
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04-arm_k_j_n_s_d12_xq2k_jibun_f0.json
```
所要 4223秒
