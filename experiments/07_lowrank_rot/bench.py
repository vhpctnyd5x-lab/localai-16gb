"""実験07: 主力レシピの低ランク因子に回転を効かせる。

実験06の知見:
  回転は「外れ値をならす」道具。尖りが大きい行列 × スカラー量子化 で破格に効く
  （RTN 4bit で 0.157 → 0.116）。ベクトル量子化には効かない。

主力レシピは W ≈ A·B + PVQ(残差) で、**A と B はスカラー4bitで量子化している**。
つまり回転が効くはずの条件にちょうど当てはまる。しかも A·B の間に直交行列 Q を
挟んでも A Q · Qᵀ B = A B で値は変わらないので、**タダで挟める**。

ここでは
  (1) A,B の間に r×r のアダマール回転を挟む
  (2) 残差側の回転（効かないはずだが念のため）
を単独と組み合わせで測る。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate

BLOB = ("/path/to/localai/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")


def kurt(M):
    z = (M - M.mean()) / M.std()
    return float((z ** 4).mean())


def inner_rotate(A, B, seed=0):
    """A(out,r) と B(r,in) の間に Q を挟む。A·B は厳密に不変。"""
    r = A.shape[1]
    d = rotate.signs(r, seed)
    s = 1.0 / np.sqrt(r)
    A2 = rotate.fwht(A) * d * s              # A Q,  Q = H·diag(d)/√r
    B2 = (rotate.fwht(B.T).T) * d[:, None] * s   # Qᵀ B
    return A2, B2


def recipe(W, r, lr_bits, k, cb_bits, G, inner_rot=False, res_rot=False, seed=0):
    out, inn = W.shape
    U, S, Vt = np.linalg.svd(W, full_matrices=False)
    A = U[:, :r] * S[:r]
    B = Vt[:r]
    if inner_rot:
        A, B = inner_rotate(A, B, seed)
    Aq = C.rtn(A, lr_bits, min(G, A.shape[1]))[0]
    Bq = C.rtn(B, lr_bits, min(G, B.shape[1]))[0]
    R = W - Aq @ Bq
    if res_rot:
        rw, rx, _ = rotate.make(inn, seed=seed + 1)
        Rh = rx(rw(R).T).T if False else None   # 残差の回転は下で別扱い
    Rh, res_bpw, _ = C.pvq(R, k=k, cb_bits=cb_bits, G=G, seed=seed)
    lr_bpw = r * (out + inn) * lr_bits / (out * inn)
    scale_ovh = 16 * (A.shape[0] * A.shape[1] / min(G, A.shape[1])
                      + B.shape[0] * B.shape[1] / min(G, B.shape[1])) / (out * inn)
    return (Aq @ Bq + Rh).astype(np.float32), lr_bpw + res_bpw + scale_ovh


r_ = gguf.Reader(BLOB)
rows = []
for TENSOR in ["v.blk.0.mlp.linear_fc1.weight", "blk.0.attn_qkv.weight"]:
    W0, tname = r_.load(TENSOR)
    W0 = np.ascontiguousarray(W0.astype(np.float32))
    out, inn = W0.shape
    if inn & (inn - 1):
        p = 1 << (inn.bit_length() - 1)
        W0 = np.ascontiguousarray(W0[:, :p]); inn = p
    rng = np.random.default_rng(999)
    X = rng.standard_t(4, size=(inn, 128)).astype(np.float32)
    X[rng.choice(inn, max(1, inn // 100), replace=False)] *= 20.

    # 低ランク因子の尖りを見る（回転が効く相手か）
    U, S, Vt = np.linalg.svd(W0, full_matrices=False)
    A = U[:, :64] * S[:64]; B = Vt[:64]
    A2, B2 = inner_rotate(A, B)
    print(f"\n=== {TENSOR} {W0.shape} 元={tname} ===")
    print(f"  A·B の不変性(誤差): {np.abs(A2@B2 - A@B).max():.2e}")
    print(f"  因子の尖り  A: {kurt(A):.2f} → {kurt(A2):.2f}   B: {kurt(B):.2f} → {kurt(B2):.2f}")
    print(f"{'設定':<42}{'bit/重み':>9}{'出力誤差':>10}")
    print("-" * 61)
    for r, lrb, k, cb in [(32, 4, 8, 4), (64, 4, 8, 4), (64, 4, 8, 8), (128, 4, 16, 8)]:
        base = None
        for irot in (False, True):
            t0 = time.time()
            Wh, bpw = recipe(W0, r, lrb, k, cb, 128, inner_rot=irot)
            _, ry = C.evaluate(W0, Wh, X=X)
            if base is None:
                base = ry; mark = ""
            else:
                mark = f"  {100*(base-ry)/base:+.1f}%"
            tag = f"ランク{r}@{lrb}bit + PVQコード{2**cb}" + ("+内側回転" if irot else "")
            print(f"{tag:<42}{bpw:>9.3f}{ry:>10.4f}{mark}")
            rows.append(dict(tensor=TENSOR, rank=r, lr_bits=lrb, k=k, cb_bits=cb,
                             内側回転=irot, bpw=round(float(bpw), 4),
                             出力誤差=round(float(ry), 5)))

json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "results", "lowrank_rot.json"), "w"),
          ensure_ascii=False, indent=2)
print("\n保存完了")
