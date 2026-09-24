# ubuntu-24.04_k_j_n_s_d11_xvocab99999_f0  2026-09-24T15:29:08Z
```
llama.cpp b31b71f / koukai b1fe459 / 問題 5961d8098783 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab99999.env
vocab keep /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab_keep_99999_ids.txt
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.59 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.83 ± 0.02 |

build: b31b71f3a (10872)

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.56 ± 0.02 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.51 ± 0.06 |

build: b31b71f3a (10872)
基準比 pp512: 0.998（実験 / 基準）
基準比 tg128: 1.046（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
8.04.093.403 I Final estimate: PPL = 7.8017 +/- 0.33039
探り: 読み 17.2 t/s（16字）・書き 14.2 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 84.8,
  "平均秒": 19.4
 },
 "正解率": 84.8,
 "平均秒": 19.4,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 0
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_xvocab99999_f0.json
```
所要 3481秒
