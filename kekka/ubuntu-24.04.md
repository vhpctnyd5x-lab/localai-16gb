# ubuntu-24.04  2026-09-19T08:12:03Z  commit b31b71f
```
cores 4
model name	: INTEL(R) XEON(R) PLATINUM 8573C
               total        used        free      shared  buff/cache   available
Mem:              15           1          11           0           2          14
/dev/root       145G   59G   87G  41% /
```

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         22.52 ± 0.70 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         12.77 ± 0.14 |

build: b31b71f3a (10872)

## 7段 深さ0 3問
```
 "段7": {
  "件": 3,
  "正解率": 66.7,
  "平均秒": 52.3
 },
 "正解率": 66.7,
 "平均秒": 52.3,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 1
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04.json
```
所要 642秒
