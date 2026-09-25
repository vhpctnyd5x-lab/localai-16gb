# ubuntu-24.04-arm_k_j_n_s_d11_g8_xreap96_iq2xxs_f0  2026-09-25T06:33:30Z
```
llama.cpp b31b71f / koukai 3e922cf / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/reap96_iq2xxs.env
メモリ上限 8 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
Vendor ID:                               ARM
Model name:                              Neoverse-N2
               total        used        free      shared  buff/cache   available
Mem:              15           1          13           0           1          14
/dev/root       145G   37G  108G  26% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.62 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.79 ± 0.03 |

build: b31b71f3a (10872)
作り直し: Q2_K / 7.7G / 所要 2315秒
専門家を 96 個に手術: 6.0G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   5.92 GiB |    23.28 B | CPU        |       4 |           pp512 |         13.10 ± 0.00 |
| qwen3moe 30B.A3B Q2_K - Medium |   5.92 GiB |    23.28 B | CPU        |       4 |           tg128 |         12.40 ± 0.06 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 6861008896 bytes; pgmajfault: 127
基準比 pp512: 0.896（実験 / 基準）
基準比 tg128: 0.899（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 7877959680 bytes; pgmajfault: 128
10.54.751.114 I Final estimate: PPL = 8.8123 +/- 0.35183
探り: 読み 14.8 t/s（16字）・書き 12.6 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 43.2,
  "平均秒": 18.9
 },
 "正解率": 43.2,
 "平均秒": 18.9,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 3
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04-arm_k_j_n_s_d11_g8_xreap96_iq2xxs_f0.json
```
llama-server cgroup memory.peak: 8589934592 bytes; pgmajfault: 290784
所要 6482秒
