"""実験26-A: 生徒の入力が、先生からどれだけずれているかを測る。

BRECQ が効くのは「ずれが積み上がっている」ときだけ。
ずれが無ければ、目標を先生の出力に変えても何も変わらない。
**まず、直すべきものが存在するかを確かめる。** ここを飛ばすと無駄骨になる。

やり方: 同じトークン列を2回流す。
  ① 元の重みのまま        → 先生の活性化
  ② unified の量子化済み  → 生徒の活性化
各層で相対的なずれを測る。深くなるほど大きくなるはず。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import forward, brecq

MODEL = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
CKPT = os.path.join(ROOT, "data/ckpt/unified")
NTOK = int(os.environ.get("NTOK", "192"))

toks = json.load(open(os.path.join(ROOT, "data/calib/tokens_big.json")))[:NTOK]
m = forward.Model(MODEL)

# 見る層（各ブロックの入口と出口の代表）
names = []
for b in range(0, 36, 3):
    names += [f"blk.{b}.attn_q.weight", f"blk.{b}.ffn_down.weight"]
names = [n for n in names if n in m.r.tensors]

print(f"{len(names)}層で、{NTOK}トークン流してずれを測る", flush=True)

t0 = time.time()
sensei = forward.run(m, toks, capture=set(names))
print(f"  先生の活性化を採取 ({time.time()-t0:.0f}秒)", flush=True)

# 生徒: unified の量子化済み重みに差し替えて流す
rep = {}
for n in names:
    p = os.path.join(CKPT, n + ".npy")
    if os.path.exists(p):
        rep[n] = np.load(p).astype(np.float32)
# 差し替えは見る層だけでなく**全層**にしないと、ずれの積み上がりが再現できない
for f in os.listdir(CKPT):
    if f.endswith(".npy"):
        n = f[:-4]
        if n not in rep:
            rep[n] = np.load(os.path.join(CKPT, f)).astype(np.float32)
print(f"  量子化済み {len(rep)}層を差し替え", flush=True)

t0 = time.time()
seito = forward.run(m, toks, capture=set(names), replace=rep)
print(f"  生徒の活性化を採取 ({time.time()-t0:.0f}秒)\n", flush=True)


def cat(d, n):
    """forward.run は capture 指定時 (logits, 採取した辞書) を返す。
    採取ぶんは d[1]。d[0] は logits なので、文字列で引くと落ちる（一度やった）。"""
    v = d[1][n] if isinstance(d, tuple) else d[n]
    return np.concatenate(v, 0) if isinstance(v, list) else v


print(f"{'層':<28}{'入力のずれ':>12}")
out = {}
for n in names:
    try:
        Xs = cat(seito, n); Xt = cat(sensei, n)
    except Exception as e:
        print(f"  {n}: 取れない({e})"); continue
    d = brecq.drift(Xs.T, Xt.T)
    out[n] = d
    print(f"{n:<28}{d:>12.4f} " + "#" * int(min(d, 2.0) * 30))

json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "drift.json"), "w"), ensure_ascii=False, indent=1)
if out:
    v = list(out.values())
    print(f"\n最初の層 {v[0]:.4f} → 最後の層 {v[-1]:.4f}")
    print("→ 深くなるほど大きければ、ずれは積み上がっている＝BRECQが効く余地あり")
