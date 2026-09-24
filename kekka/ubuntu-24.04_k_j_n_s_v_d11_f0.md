# ubuntu-24.04_k_j_n_s_v_d11_f0  2026-09-24T07:18:12Z
```
llama.cpp b31b71f / koukai 4785a47 / 問題 5961d8098783 / 頭脳 db3ce897ccc9
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   87G  41% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.56 ± 0.00 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.01 ± 0.02 |

build: b31b71f3a (10872)

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 88.0,
  "平均秒": 18.7
 },
 "正解率": 88.0,
 "平均秒": 18.7,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 2
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_v_d11_f0.json
```
所要 2755秒
