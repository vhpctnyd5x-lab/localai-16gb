# ubuntu-24.04-arm_k_j_n_s_v_d12_f0  2026-09-24T07:18:12Z
```
llama.cpp b31b71f / koukai 4785a47 / 問題 b7a44aa92e05 / 頭脳 db3ce897ccc9
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
Vendor ID:                               ARM
Model name:                              Neoverse-N2
               total        used        free      shared  buff/cache   available
Mem:              15           1          13           0           1          14
/dev/root       145G   37G  109G  25% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.54 ± 0.04 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.46 ± 0.02 |

build: b31b71f3a (10872)

## 7段 深さ0 0問（0=全部）
```
 "段12": {
  "件": 47,
  "正解率": 55.3,
  "平均秒": 31.9
 },
 "正解率": 55.3,
 "平均秒": 31.9,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 0
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04-arm_k_j_n_s_v_d12_f0.json
```
所要 1886秒
