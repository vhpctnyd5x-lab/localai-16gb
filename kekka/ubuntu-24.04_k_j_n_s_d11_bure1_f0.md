# ubuntu-24.04_k_j_n_s_d11_bure1_f0  2026-09-24T16:16:38Z
```
llama.cpp b31b71f / koukai bf4bd91 / 問題 5961d8098783 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
生成設定 temperature=0.7 top_p=0.8 top_k=20 seed=1
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.54 ± 0.03 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.08 ± 0.01 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
8.13.920.447 I Final estimate: PPL = 7.8099 +/- 0.33087
探り: 読み 18.2 t/s（16字）・書き 14.2 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 85.6,
  "平均秒": 20.3
 },
 "正解率": 85.6,
 "平均秒": 20.3,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 2
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_bure1_f0.json
```
所要 3473秒
