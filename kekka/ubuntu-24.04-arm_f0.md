# ubuntu-24.04-arm_f0  2026-09-19T14:42:09Z
```
llama.cpp b31b71f / koukai 17b8d3c / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
Vendor ID:                               ARM
Model name:                              Neoverse-N2
               total        used        free      shared  buff/cache   available
Mem:              15           1          13           0           1          14
/dev/root       145G   36G  109G  25% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.60 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.81 ± 0.01 |

build: b31b71f3a (10872)

## 起動指定の比べ（7段 深さ0 16問ずつ、同じ問題）
| 名前 | 指定 | 正解率 | 平均秒 |
|---|---|---|---|
| moto | `--spec-type ngram-simple` | None | None |
| m16 | `--spec-type ngram-simple --spec-ngram-simple-size-m 16` | None | None |
| m8 | `--spec-type ngram-simple --spec-ngram-simple-size-m 8` | None | None |
| n8m16 | `--spec-type ngram-simple --spec-ngram-simple-size-n 8 --spec-ngram-simple-size-m 16` | None | None |
| mod | `--spec-type ngram-mod` | None | None |
| nashi | `--spec-type none` | None | None |
| kq8 | `--spec-type ngram-simple -ctk q8_0` | None | None |
所要 4670秒
