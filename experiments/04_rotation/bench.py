"""実験04: 回転 + 残差VQ + スケール最小二乗 を積み上げる。

査読で挙がった3つの改良を、単独と組み合わせで測る。
- 回転(アダマール): 保存コストほぼゼロ。値を均して量子化しやすくする。
- 残差VQ: 1段目の取りこぼしを2段目の辞書で拾う。ビット配分を細かく刻める。
- スケール最小二乗: absmax(外れ値1個に引きずられる)ではなく、誤差最小のスケールを解く。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate, entropy as E

BLOB = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")
TENSOR = "v.blk.0.mlp.linear_fc1.weight"


def quantize(W, k, cb_bits, G, stages=1, ls_scale=False, seed=0):
    """PVQ 本体。stages>1 で残差VQ、ls_scale で最小二乗スケール。"""
    X = C._grouped(W, G)
    s = C._scales(X)
    idxs, cbs = [], []
    Xn = (X / s).reshape(-1, k).astype(np.float32)
    recon = np.zeros_like(Xn)
    R = Xn
    for st in range(stages):
        Cb = C._kmeans(R, 2 ** cb_bits, seed=seed + st)
        idx = C._assign(R, Cb)
        recon = recon + Cb[idx]
        R = Xn - recon
        idxs.append(idx); cbs.append(Cb)
    if ls_scale:
        # コードを固定して、グループごとに誤差最小のスケールを解き直す
        Rec = recon.reshape(X.shape)
        num = (X * Rec).sum(1, keepdims=True)
        den = (Rec * Rec).sum(1, keepdims=True)
        den[den == 0] = 1
        s = num / den
    Wh = (recon.reshape(X.shape) * s).reshape(W.shape).astype(np.float32)
    bpw = stages * cb_bits / k + 16 / G
    return Wh, bpw, idxs


r = gguf.Reader(BLOB)
W0, tname = r.load(TENSOR); W0 = W0.astype(np.float32)
n = W0.shape[1]
rng = np.random.default_rng(999)
X0 = rng.standard_t(4, size=(n, 128)).astype(np.float32)
X0[rng.choice(n, n // 100, replace=False)] *= 20.
rot_W, rot_x, _ = rotate.make(n, seed=0)

print(f"対象: {TENSOR} {W0.shape} 元={tname}")
print(f"{'設定':<46}{'bit/重み':>9}{'出力誤差':>10}{'エントロピー後':>13}")
print("-" * 80)
rows = []
configs = [
    # (k, cb_bits, G, stages, ls, rot)
    (8, 8, 128, 1, False, False),
    (8, 8, 128, 1, False, True),
    (8, 8, 128, 1, True,  True),
    (8, 8, 128, 2, True,  True),
    (8, 4, 128, 1, False, False),
    (8, 4, 128, 1, False, True),
    (8, 4, 128, 1, True,  True),
    (8, 4, 128, 2, True,  True),
    (8, 10, 128, 1, True, True),
    (16, 8, 256, 1, True, True),
    (16, 8, 256, 2, True, True),
]
for k, cb, G, stages, ls, rot in configs:
    t0 = time.time()
    W = rot_W(W0) if rot else W0
    Xe = rot_x(X0) if rot else X0
    Wh, bpw, idxs = quantize(W, k, cb, G, stages, ls)
    rw, ry = C.evaluate(W, Wh, X=Xe)
    # エントロピー符号化後の実効ビット（全段の合計）
    ent = sum(E.entropy(np.bincount(i, minlength=2 ** cb)) for i in idxs) / k + 16 / G
    tag = f"k={k},コード{2**cb},{stages}段" + ("+回転" if rot else "") + ("+LS" if ls else "")
    print(f"{tag:<46}{bpw:>9.3f}{ry:>10.4f}{ent:>13.3f}")
    rows.append(dict(k=k, cb_bits=cb, G=G, 段数=stages, LS=ls, 回転=rot,
                     bpw=round(bpw, 4), 出力誤差=round(float(ry), 5),
                     重み誤差=round(float(rw), 5), エントロピー後=round(float(ent), 4),
                     秒=round(time.time() - t0, 1)))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", f"{TENSOR}.json")
json.dump(dict(tensor=TENSOR, rows=rows), open(out, "w"), ensure_ascii=False, indent=2)
print("\n保存:", out)
