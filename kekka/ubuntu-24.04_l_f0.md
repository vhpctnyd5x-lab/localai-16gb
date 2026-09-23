# ubuntu-24.04_l_f0  2026-09-23T13:08:20Z
```
llama.cpp b31b71f / koukai 5d0cb5f / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: INTEL(R) XEON(R) PLATINUM 8573C
               total        used        free      shared  buff/cache   available
Mem:              15           1          11           0           2          14
/dev/root       145G   59G   86G  41% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         21.85 ± 0.58 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         12.68 ± 0.03 |

build: b31b71f3a (10872)

## 7段 深さ0 0問（0=全部）
```
 "段7": {
  "件": 128,
  "正解率": 50.0,
  "平均秒": 23.3
 },
 "正解率": 50.0,
 "平均秒": 23.3,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 23
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_l_f0.json
```
所要 3422秒
