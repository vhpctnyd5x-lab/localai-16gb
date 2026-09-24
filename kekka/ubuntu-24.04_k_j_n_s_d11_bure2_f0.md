# ubuntu-24.04_k_j_n_s_d11_bure2_f0  2026-09-24T16:31:45Z
```
llama.cpp b31b71f / koukai 3e922cf / 問題 5961d8098783 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
生成設定 temperature=0.7 top_p=0.8 top_k=20 seed=2
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         24.15 ± 0.49 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         17.39 ± 0.21 |

build: b31b71f3a (10872)

## PPL（llama-perplexity -c 512 --chunks 16）
7.06.828.833 I Final estimate: PPL = 7.8300 +/- 0.33154
探り: 読み 2.3 t/s（16字）・書き 7.1 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 82.4,
  "平均秒": 16.5
 },
 "正解率": 82.4,
 "平均秒": 16.5,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 1
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_bure2_f0.json
```
所要 3211秒
