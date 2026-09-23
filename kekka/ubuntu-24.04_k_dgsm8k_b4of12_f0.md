# ubuntu-24.04_k_dgsm8k_b4of12_f0  2026-09-23T08:30:02Z
```
llama.cpp b31b71f / koukai 449b059 / 問題 52d9634a6b1b / 頭脳 db3ce897ccc9
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   87G  41% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.60 ± 0.02 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.97 ± 0.07 |

build: b31b71f3a (10872)

## 7段 深さ0 0問（0=全部）
```
 "段0": {
  "件": 110,
  "正解率": 90.9,
  "平均秒": 14.7
 },
 "正解率": 90.9,
 "平均秒": 14.7,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 0
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_dgsm8k_b4of12_f0.json
```
所要 2034秒
