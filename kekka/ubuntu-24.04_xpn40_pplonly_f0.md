# ubuntu-24.04_xpn40_pplonly_f0  2026-09-24T15:11:55Z
```
llama.cpp b31b71f / koukai b1fe459 / 問題 edcddf2ebec8 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/pn40.env
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.53 ± 0.03 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.72 ± 0.09 |

build: b31b71f3a (10872)
失敗: exit=1 行=324 命令=PYTHONPATH="$W/llama.cpp/gguf-py${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" "$K/dougu/asshuku/prune_neurons.py" --imatrix "$IMATRIX" --imatrix-out "$PRUNED_IMATRIX" --frac "$KOUKAI_PRUNE_NEURONS" "$M" "$PRUNED_M"
