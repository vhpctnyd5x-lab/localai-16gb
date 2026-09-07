"""実験05: 低ランク分解 + 残差の超低ビット量子化。

評議会の第1推奨。ただし委員のビット計算は誤っていたので自分で数え直す。
W (out×in) をランク r で近似すると、U(out×r) と V(r×in) を持つ必要があり、
コストは r*(out+in)*bits_lr ビット。これを out*in で割ったものが1重みあたりの上乗せ。
例: out=4096, in=1024, r=64, 8bit なら 64*5120*8 / (4096*1024) = 0.625 bit/重み。
委員の見積り(0.13bit)は5倍ほど楽観的だった。低ランクは「安くない」。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate

BLOB = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")
TENSOR = "v.blk.0.mlp.linear_fc1.weight"


def lowrank_cost(out, inn, r, bits):
    return r * (out + inn) * bits / (out * inn)


def run(W, r, lr_bits, k, cb_bits, G, rot=False, seed=0):
    out, inn = W.shape
    if r > 0:
        U, S, Vt = np.linalg.svd(W, full_matrices=False)
        A = U[:, :r] * S[:r]                      # (out, r)
        B = Vt[:r]                                # (r, in)
        # 低ランク因子も量子化する（fp16のままでは高すぎる）
        A = C.rtn(A, lr_bits, min(G, r))[0] if r >= G else C.rtn(A, lr_bits, r)[0]
        B = C.rtn(B, lr_bits, min(G, inn))[0]
        R = W - A @ B
        lr_bpw = lowrank_cost(out, inn, r, lr_bits)
    else:
        A = B = None
        R = W
        lr_bpw = 0.0
    Rh, res_bpw, _ = C.pvq(R, k=k, cb_bits=cb_bits, G=G, seed=seed)
    Wh = (A @ B + Rh) if r > 0 else Rh
    return Wh.astype(np.float32), lr_bpw + res_bpw


r_ = gguf.Reader(BLOB)
W0, tname = r_.load(TENSOR); W0 = W0.astype(np.float32)
out, inn = W0.shape
rng = np.random.default_rng(999)
X0 = rng.standard_t(4, size=(inn, 128)).astype(np.float32)
X0[rng.choice(inn, inn // 100, replace=False)] *= 20.
rot_W, rot_x, _ = rotate.make(inn, seed=0)

# スペクトルを見る: 低ランクが効く相手かどうか
S = np.linalg.svd(W0, compute_uv=False)
tot = (S ** 2).sum()
print(f"対象: {TENSOR} {W0.shape} 元={tname}")
for r in (16, 32, 64, 128, 256):
    print(f"  上位{r:4d}成分でエネルギーの {100*(S[:r]**2).sum()/tot:5.1f}% を説明 "
          f"(低ランク側の費用 {lowrank_cost(out,inn,r,8):.3f} bit/重み @8bit)")
print()

print(f"{'設定':<44}{'bit/重み':>9}{'出力誤差':>10}")
print("-" * 63)
rows = []
for rot in (False, True):
    W = rot_W(W0) if rot else W0
    Xe = rot_x(X0) if rot else X0
    for r, lrb, k, cb in [(0, 0, 8, 4), (0, 0, 8, 8),
                          (16, 8, 8, 4), (32, 8, 8, 4), (64, 8, 8, 4),
                          (32, 4, 8, 4), (64, 4, 8, 4), (64, 4, 8, 8),
                          (128, 4, 16, 8)]:
        t0 = time.time()
        Wh, bpw = run(W, r, lrb, k, cb, 128)
        rw, ry = C.evaluate(W, Wh, X=Xe)
        tag = (f"ランク{r}@{lrb}bit + PVQ k={k},コード{2**cb}"
               + ("+回転" if rot else ""))
        print(f"{tag:<44}{bpw:>9.3f}{ry:>10.4f}")
        rows.append(dict(rank=r, lr_bits=lrb, k=k, cb_bits=cb, 回転=rot,
                         bpw=round(float(bpw), 4), 出力誤差=round(float(ry), 5),
                         秒=round(time.time()-t0, 1)))

json.dump(dict(tensor=TENSOR, rows=rows),
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "results", f"{TENSOR}.json"), "w"),
          ensure_ascii=False, indent=2)
print("\n保存完了")
