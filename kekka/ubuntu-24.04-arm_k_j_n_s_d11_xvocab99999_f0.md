# ubuntu-24.04-arm_k_j_n_s_d11_xvocab99999_f0  2026-09-24T15:29:35Z
```
llama.cpp b31b71f / koukai b1fe459 / 問題 5961d8098783 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab99999.env
vocab keep /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab_keep_99999_ids.txt
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.54 ± 0.04 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.62 ± 0.00 |

build: b31b71f3a (10872)

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.57 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.41 ± 0.05 |

build: b31b71f3a (10872)
基準比 pp512: 1.002（実験 / 基準）
基準比 tg128: 1.058（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
9.45.309.278 I Final estimate: PPL = 7.7986 +/- 0.32957
探り: 読み 15.6 t/s（16字）・書き 13.4 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 82.4,
  "平均秒": 21.3
 },
 "正解率": 82.4,
 "平均秒": 21.3,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 3
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04-arm_k_j_n_s_d11_xvocab99999_f0.json
```
所要 3812秒
