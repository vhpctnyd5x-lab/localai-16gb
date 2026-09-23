# ubuntu-24.04-arm_k_j_n_s_d10_f0  2026-09-23T15:12:41Z
```
llama.cpp b31b71f / koukai 4be7570 / 問題 0914ae921584 / 頭脳 db3ce897ccc9
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
Vendor ID:                               ARM
Model name:                              Neoverse-N2
               total        used        free      shared  buff/cache   available
Mem:              15           1          13           0           1          14
/dev/root       145G   37G  108G  26% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.57 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.25 ± 0.04 |

build: b31b71f3a (10872)

## 7段 深さ0 0問（0=全部）
```
 "段10": {
  "件": 127,
  "正解率": 79.5,
  "平均秒": 23.1
 },
 "正解率": 79.5,
 "平均秒": 23.1,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 2
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04-arm_k_j_n_s_d10_f0.json
```
所要 3863秒
