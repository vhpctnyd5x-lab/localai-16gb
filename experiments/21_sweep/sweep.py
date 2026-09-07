"""実験21: ビット数を振って「どこから実用になるか」の境界を探す。

1.154bitでPPL=4267（崩壊）。ではどこまで厚くすれば戻るのか。
目標を下げるのではなく、現在地と実用ラインの距離を測るのが目的。

各構成は独立にチェックポイントを持つので、何度中断しても続きから再開できる。
PPLを測ったらGGUFは消す（1本5.8GBなので溜め込まない）。
"""
import json, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results", "sweep.json")
BIN = os.path.join(ROOT, "tools/llama.cpp/build/bin")
TEST = os.path.join(ROOT, "data/calib/corpus_test.txt")
QUANT = os.path.join(ROOT, "experiments/19_full_unified/quantize2.py")

# (名前, k, コードビット, グループ, ランク)  → k を小さくすると厚くなる
CONFIGS = [
    ("b07", 16, 8, 256, 32),   # 約0.7bit
    ("b17",  8, 12, 256, 32),  # 約1.7bit
    ("b22",  4, 8, 256, 32),   # 約2.2bit
    ("b32",  4, 12, 256, 32),  # 約3.2bit
]


def load():
    return json.load(open(RES)) if os.path.exists(RES) else {}


def save(d):
    json.dump(d, open(RES, "w"), ensure_ascii=False, indent=2)


def ppl(model):
    p = subprocess.run([os.path.join(BIN, "llama-perplexity"), "-m", model,
                        "-f", TEST, "--chunks", "12", "-c", "512"],
                       capture_output=True, text=True, timeout=7200)
    for line in (p.stdout + p.stderr).replace("\r", "\n").split("\n"):
        if "Final estimate" in line:
            return float(line.split("PPL =")[1].split("+/-")[0].strip())
    return None


done = load()
for name, k, cb, G, rank in CONFIGS:
    if name in done and done[name].get("ppl"):
        print(f"[skip] {name} は測定済み PPL={done[name]['ppl']}", flush=True)
        continue
    print(f"\n===== {name}: k={k} コード{2**cb} G={G} ランク{rank} =====", flush=True)
    env = dict(os.environ, NAME=name, K=str(k), CB=str(cb), GRP=str(G),
               RANK=str(rank), NTOK="1024")
    t0 = time.time()
    r = subprocess.run([sys.executable, QUANT], env=env)
    if r.returncode != 0:
        print(f"  {name} 量子化が失敗(code={r.returncode})。次回再開できる。", flush=True)
        continue
    gguf = os.path.join(ROOT, "data/models", name + ".gguf")
    info = os.path.join(ROOT, "data/ckpt", name + ".log")
    bpw = None
    for line in open(info):
        if "平均" in line and "bit/重み" in line:
            bpw = float(line.split("平均")[1].split("bit")[0].strip())
    v = ppl(gguf)
    done[name] = dict(k=k, cb=cb, G=G, rank=rank, bpw=bpw, ppl=v,
                      分=round((time.time()-t0)/60, 1))
    save(done)
    print(f"  → {bpw} bit/重み, PPL={v}  ({done[name]['分']}分)", flush=True)
    if os.path.exists(gguf):
        os.remove(gguf)      # 1本5.8GB。測ったら消す

print("\n===== まとめ =====")
print(f"{'構成':>6}{'bit/重み':>10}{'PPL':>12}")
for n, d in sorted(done.items(), key=lambda x: x[1].get("bpw") or 0):
    print(f"{n:>6}{(d.get('bpw') or 0):>10.3f}{(d.get('ppl') or 0):>12.1f}")
print("参考: 元モデル(Q4_K, 4.8bit) = 5.58 / 統合レシピ1.154bit = 4267")
