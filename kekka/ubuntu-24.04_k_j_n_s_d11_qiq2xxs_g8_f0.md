# ubuntu-24.04_k_j_n_s_d11_qiq2xxs_g8_f0  2026-09-24T10:44:58Z
```
llama.cpp b31b71f / koukai 822fdb3 / 問題 5961d8098783 / 頭脳 40e7b72332c8
メモリ上限 8 GB（swap なし、mmap ページキャッシュを含む）
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
| qwen3moe 30B.A3B IQ2_XXS - 2.0625 bpw |   9.65 GiB |    30.53 B | CPU        |       4 |           pp512 |         29.24 ± 0.07 |
| qwen3moe 30B.A3B IQ2_XXS - 2.0625 bpw |   9.65 GiB |    30.53 B | CPU        |       4 |           tg128 |          8.38 ± 0.04 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 229244928 bytes; pgmajfault: 2
探り: 読み 12.6 t/s（16字）・書き 8.1 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 84.0,
  "平均秒": 38.0
 },
 "正解率": 84.0,
 "平均秒": 38.0,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 2
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_qiq2xxs_g8_f0.json
```
llama-server cgroup memory.peak: 6122008576 bytes; pgmajfault: 2921
所要 5223秒
