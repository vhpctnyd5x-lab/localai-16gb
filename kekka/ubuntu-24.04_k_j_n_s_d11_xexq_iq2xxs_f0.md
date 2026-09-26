# ubuntu-24.04_k_j_n_s_d11_xexq_iq2xxs_f0  2026-09-26T07:46:21Z
```
llama.cpp b31b71f / koukai 8f8d20b / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/exq_iq2xxs.env
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.58 ± 0.03 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.03 ± 0.00 |

build: b31b71f3a (10872)
作り直し: Q2_K / 7.7G / 所要 5279秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.67 GiB |    30.53 B | CPU        |       4 |           pp512 |         25.15 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.67 GiB |    30.53 B | CPU        |       4 |           tg128 |          9.17 ± 0.01 |

build: b31b71f3a (10872)
基準比 pp512: 1.284（実験 / 基準）
基準比 tg128: 0.610（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
6.23.101.562 I Final estimate: PPL = 8.3922 +/- 0.33847
探り: 読み 12.5 t/s（16字）・書き 8.8 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 80.8,
  "平均秒": 32.6
 },
 "正解率": 80.8,
 "平均秒": 32.6,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 4
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_xexq_iq2xxs_f0.json
```
所要 10891秒
