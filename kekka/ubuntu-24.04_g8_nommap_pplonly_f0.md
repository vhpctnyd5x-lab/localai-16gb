# ubuntu-24.04_g8_nommap_pplonly_f0  2026-09-24T16:16:44Z
```
llama.cpp b31b71f / koukai bf4bd91 / 問題 edcddf2ebec8 / 頭脳 db3ce897ccc9
llama patch sha256 fc146c2e6569
メモリ上限 8 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.37 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.53 ± 0.06 |

build: b31b71f3a (10872)

## 速さ（llama-bench -t 4）
error: invalid parameter for argument: --no-mmap
usage: /home/runner/work/_temp/hakaru/build/bin/llama-bench [options]

options:
  -h, --help
  --numa <distribute|isolate|numactl>         numa mode (default: disabled)
  -r, --repetitions <n>                       number of times to repeat each test (default: 5)
  --prio <-1|0|1|2|3>                         process/thread priority (default: 0)
  --delay <0...N> (seconds)                   delay between each test (default: 0)
  -o, --output <csv|json|jsonl|md|sql>        output format printed to stdout (default: md)
  -oe, --output-err <csv|json|jsonl|md|sql>   output format printed to stderr (default: none)
  --list-devices                              list available devices and exit
  -v, --verbose                               verbose output
  --progress                                  print test progress indicators
  --no-warmup                                 skip warmup runs before benchmarking
  -fitt, --fit-target <MiB>                   fit model to device memory with this margin per device in MiB (default: off)
  -fitc, --fit-ctx <n>                        minimum ctx size for --fit-target (default: 4096)

test parameters:
  -m, --model <filename>                            (default: models/7B/ggml-model-q4_0.gguf)
  -hf, -hfr, --hf-repo <user>/<model>[:quant]       Hugging Face model repository; quant is optional, case-insensitive
                                                    default to Q4_K_M, or falls back to the first file in the repo if Q4_K_M doesn't exist.
                                                    example: ggml-org/GLM-4.7-Flash-GGUF:Q4_K_M
                                                    (default: unused)
  -hff, --hf-file <file>                            Hugging Face model file. If specified, it will override the quant in --hf-repo
                                                    (default: unused)
  -hft, --hf-token <token>                          Hugging Face access token
                                                    (default: value from HF_TOKEN environment variable)
  --offline                                         Offline mode: forces use of cache, prevents network access
                                                    (default: disabled)
  -p, --n-prompt <n>                                (default: 512)
  -n, --n-gen <n>                                   (default: 128)
  -pg <pp,tg>                                       (default: )
  -d, --n-depth <n>                                 (default: 0)
  -b, --batch-size <n>                              (default: 2048)
  -ub, --ubatch-size <n>                            (default: 512)
  -ctk, --cache-type-k <t>                          (default: f16)
  -ctv, --cache-type-v <t>                          (default: f16)
  -t, --threads <n>                                 (default: 2)
  -C, --cpu-mask <hex,hex>                          (default: 0x0)
  --cpu-strict <0|1>                                (default: 0)
  --poll <0...100>                                  (default: 50)
  -ngl, --n-gpu-layers <n>                          (default: -1)
  -ncmoe, --n-cpu-moe <n>                           (default: 0)
  -sm, --split-mode <none|layer|row|tensor>         (default: layer)
  -mg, --main-gpu <i>                               (default: 0)
  -nkvo, --no-kv-offload <0|1>                      (default: 0)
  -fa, --flash-attn <on|off|auto>                   (default: auto)
  -dev, --device <dev0/dev1/...>                    (default: auto)
  -lm, --load-mode <auto|none|mmap|mlock|mmap+mlock|dio> (default: auto)
  -lzm, --lazy-mode <on|auto|off>                   (default: auto)
  -mmp, --mmap <0|1>                                (DEPRECATED IN FAVOUR OF --load-mode)
  -dio, --direct-io <0|1>                           (DEPRECATED IN FAVOUR OF --load-mode)
  -embd, --embeddings <0|1>                         (default: 0)
  -ts, --tensor-split <ts0/ts1/..>                  (default: 0)
  -ot --override-tensor <tensor name pattern>=<buffer type>;...
                                                    (default: disabled)
  -nopo, --no-op-offload <0|1>                      (default: 0)
  --no-host <0|1>                                   (default: 0)

Multiple values can be given for each parameter by separating them with ','
or by specifying the parameter multiple times. Ranges can be given as
'first-last' or 'first-last+step' or 'first-last*mult'.
llama-bench 失敗: exit=1
8 GB で落ちた（llama-bench）
llama-bench cgroup memory.peak: 8728576 bytes; pgmajfault: 48
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
