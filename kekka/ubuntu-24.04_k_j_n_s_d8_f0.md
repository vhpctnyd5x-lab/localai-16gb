# ubuntu-24.04_k_j_n_s_d8_f0  2026-09-23T10:03:35Z
```
llama.cpp b31b71f / koukai 08799f5 / 問題 35458f5e8612 / 頭脳 db3ce897ccc9
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V45 96-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   87G  41% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         32.96 ± 1.05 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         19.74 ± 0.30 |

build: b31b71f3a (10872)

## 7段 深さ0 0問（0=全部）
```
 "段8": {
  "件": 127,
  "正解率": 89.0,
  "平均秒": 12.1
 },
 "正解率": 89.0,
 "平均秒": 12.1,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 1
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d8_f0.json
```
所要 1886秒
