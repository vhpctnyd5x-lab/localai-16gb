# ubuntu-24.04_g8_nommap_pplonly_f0  2026-09-25T06:39:48Z
```
llama.cpp b31b71f / koukai 8f8d20b / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
メモリ上限 8 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.49 ± 0.00 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.56 ± 0.20 |

build: b31b71f3a (10872)

## 速さ（llama-bench -t 4）
8GB に載らない（Killed、exit 137）
DEPRECATED: -mmp and --mmap are deprecated in favour of --load-mode. Please use --load-mode mmap instead.
dougu/actions_hakaru.sh: line 188:  5128 Killed                  sudo --preserve-env="$keep" bash -c 'echo $$ > "$1/cgroup.procs"; shift; uid="$1"; gid="$2"; shift 2; exec setpriv --reuid="$uid" --regid="$gid" --init-groups -- "$@"' _ "$path" "$uid" "$gid" "$@"
llama-bench cgroup memory.peak: 8589934592 bytes; pgmajfault: 73
8 GB で落ちた（llama-bench、OOM kill）
基準比 pp512: 算出できず（ベンチ値不足）
基準比 tg128: 算出できず（ベンチ値不足）

## PPL（llama-perplexity -c 512 --chunks 16）
8GB に載らない（Killed、exit 137）
llama-perplexity cgroup memory.peak: 8589934592 bytes; pgmajfault: 91
8 GB で落ちた（llama-perplexity、OOM kill）
PPL: 取れなかった
8GB に載らない（Killed、exit 137）
llama-server cgroup memory.peak: 8589934592 bytes; pgmajfault: 112
8 GB で落ちた（llama-server、OOM kill）
