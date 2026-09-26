# ubuntu-24.04_k_j_n_s_d11_g8_xexq_iq2xxs_f0  2026-09-26T10:49:59Z
```
llama.cpp b31b71f / koukai 5048ee9 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/exq_iq2xxs.env
メモリ上限 8 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: INTEL(R) XEON(R) PLATINUM 8573C
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         20.18 ± 5.29 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         12.81 ± 0.24 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
作り直し: Q2_K / 7.7G / 所要 4435秒

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.67 GiB |    30.53 B | CPU        |       4 |           pp512 |         36.21 ± 0.29 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.67 GiB |    30.53 B | CPU        |       4 |           tg128 |          9.43 ± 0.03 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 8589934592 bytes; pgmajfault: 1109
基準比 pp512: 1.794（実験 / 基準）
基準比 tg128: 0.736（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 8589934592 bytes; pgmajfault: 17054
4.50.703.550 I Final estimate: PPL = 8.3847 +/- 0.33809
探り: 読み 7.7 t/s（16字）・書き 8.4 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 79.2,
  "平均秒": 40.8
 },
 "正解率": 79.2,
 "平均秒": 40.8,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 3
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_g8_xexq_iq2xxs_f0.json
```
llama-server cgroup memory.peak: 8589938688 bytes; pgmajfault: 6222348
所要 10788秒
