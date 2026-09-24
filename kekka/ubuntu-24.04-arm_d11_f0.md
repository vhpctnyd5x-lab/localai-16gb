# ubuntu-24.04-arm_d11_f0  2026-09-24T06:07:32Z
```
llama.cpp b31b71f / koukai 744991e / 問題 5961d8098783 / 頭脳 db3ce897ccc9
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.55 ± 0.03 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.66 ± 0.06 |

build: b31b71f3a (10872)

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 76.0,
  "平均秒": 24.7
 },
 "正解率": 76.0,
 "平均秒": 24.7,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 4
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04-arm_d11_f0.json
```
所要 3467秒
