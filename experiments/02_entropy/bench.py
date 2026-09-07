import os
"""実験02: コード番号列をさらに圧縮する。

積量子化の「名目ビット数」は log2(コード数)/k。だがコード番号の使われ方は
偏っているので、エントロピー符号化を上乗せすると実効ビット数はさらに下がる。
狙いは「コード数を増やして精度を上げつつ、平均ビットは増やさない」こと。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, entropy as E

BLOB = (os.environ.get("MODEL_BLOB") or "/path/to/localai/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")
TENSOR = sys.argv[1] if len(sys.argv) > 1 else "v.blk.0.mlp.linear_fc1.weight"


def pvq_with_idx(W, k, cb_bits, G, seed=0):
    """PVQ を回し、復元結果とコード番号列の両方を返す。"""
    X = C._grouped(W, G)
    s = C._scales(X)
    Xn = (X / s).reshape(-1, k).astype(np.float32)
    Cb = C._kmeans(Xn, 2 ** cb_bits, seed=seed)
    idx = C._assign(Xn, Cb)
    Wh = (Cb[idx].reshape(X.shape) * s).reshape(W.shape).astype(np.float32)
    return Wh, idx


r = gguf.Reader(BLOB)
W, tname = r.load(TENSOR); W = W.astype(np.float32)
rng = np.random.default_rng(999)
Xev = rng.standard_t(4, size=(W.shape[1], 128)).astype(np.float32)
Xev[rng.choice(W.shape[1], W.shape[1] // 100, replace=False)] *= 20.

print(f"対象: {TENSOR} {W.shape} 元={tname}\n")
configs = [(8, 4, 128), (8, 6, 128), (8, 8, 128), (8, 10, 128),
           (4, 4, 128), (4, 6, 128), (16, 8, 256), (16, 12, 256)]
rows = []
for k, cb, G in configs:
    t0 = time.time()
    Wh, idx = pvq_with_idx(W, k, cb, G)
    rw, ry = C.evaluate(W, Wh, X=Xev)
    bits, counts = E.analyze(idx, 2 ** cb, k, G)
    used = int((counts > 0).sum())
    print(f"k={k:2d} コード数={2**cb:5d}(実使用{used:5d})  出力誤差={ry:.4f}  {time.time()-t0:.0f}秒")
    for name, v in bits.items():
        print(f"      {name:<14} {v:.4f} bit/重み")
    print()
    rows.append(dict(k=k, cb_bits=cb, G=G, 実使用コード数=used,
                     出力誤差=round(float(ry), 5), 重み誤差=round(float(rw), 5),
                     **{n: round(v, 4) for n, v in bits.items()}))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                   f"{TENSOR}.json")
json.dump(dict(tensor=TENSOR, rows=rows), open(out, "w"), ensure_ascii=False, indent=2)
print("保存:", out)
