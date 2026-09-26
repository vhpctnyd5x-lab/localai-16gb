# ubuntu-24.04_k_j_n_s_d11_xt8_imat_en96_f0  2026-09-26T07:59:45Z
```
llama.cpp b31b71f / koukai 6efeda1 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t8_imat_en96.env
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: Intel(R) Xeon(R) 6973P-C
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         13.60 ± 5.25 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |          8.84 ± 0.36 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: en / 配布Q2_K由来 / c512 chunks32 / dceea0634cfd6ff38569a66d01c5044a5ec38b0c7414394453803d07e1ec08a5  /home/runner/work/_temp/hakaru/calib_en.txt
14.02.432.712 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (92.97%)
14.02.432.713 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (89.84%)
14.02.432.713 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (86.72%)
14.02.432.714 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.06%)
14.02.432.714 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (86.72%)
14.02.432.716 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (88.28%)
14.02.432.716 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (90.62%)
14.02.432.717 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (89.84%)
14.02.432.717 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (89.84%)
14.02.432.718 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.06%)


較正 imatrix: 80c8914b8cd6f8030de732f00417ee8f8546713e70bb680fb2914999f92e75e2  /home/runner/work/_temp/hakaru/imatrix_en.gguf
作り直し: Q2_K / 7.7G / 所要 3917秒
専門家を 96 個に手術: 6.0G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   5.92 GiB |    23.28 B | CPU        |       4 |           pp512 |         40.64 ± 0.44 |
| qwen3moe 30B.A3B Q2_K - Medium |   5.92 GiB |    23.28 B | CPU        |       4 |           tg128 |          7.41 ± 0.03 |

build: b31b71f3a (10872)
基準比 pp512: 2.988（実験 / 基準）
基準比 tg128: 0.838（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
3.53.618.334 I Final estimate: PPL = 9.1026 +/- 0.36879
探り: 読み 15.5 t/s（16字）・書き 12.0 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 44.0,
  "平均秒": 25.1
 },
 "正解率": 44.0,
 "平均秒": 25.1,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 9
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_xt8_imat_en96_f0.json
```
所要 9318秒
