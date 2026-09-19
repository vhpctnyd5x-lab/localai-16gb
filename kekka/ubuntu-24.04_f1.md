# ubuntu-24.04_f1  2026-09-19T14:26:19Z
```
llama.cpp b31b71f / koukai ea4d684 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.59 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.46 ± 0.15 |

build: b31b71f3a (10872)

## 7段 深さ1 0問（0=全部）
```
 "段7": {
  "件": 128,
  "正解率": 67.2,
  "平均秒": 47.5
 },
 "正解率": 67.2,
 "平均秒": 47.5,
 "平均考えた字数": 855,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 5
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_f1.json
```
所要 6548秒
