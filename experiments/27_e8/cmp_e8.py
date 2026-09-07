"""E8格子 対 k-means語彙 — 同一ビットでの公平比較（単層・未使用データで採点）。

手順は実験30と同じ:
  先生の活性化 512 トークンを前半/後半に割り、前半で量子化し後半で採点する。
  採点は出力空間の相対誤差 ‖(W−Ŵ)X‖ / ‖WX‖。
"""
import os, sys, time
import numpy as np
S = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(S)), "lib"))
ROOT = "/Volumes/Mac Windows/LocalAI改良"
import forward, recipe as RP, e8

MODEL = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
m = forward.Model(MODEL, in_memory=False)


def load(name):
    W = m.T(name).astype(np.float32); m.drop(name)
    X = np.load(f"{ROOT}/data/ckpt/sensei_acts/{name}.npy").astype(np.float32).T
    h = X.shape[1] // 2
    return W, np.ascontiguousarray(X[:, :h]), np.ascontiguousarray(X[:, h:])


# E8 の語彙ビットに k-means(4次元) の語数を合わせる: 4次元あたり bits(R2)*4 ビット
def kmeans_match(R2):
    return float(np.log2(e8.count(R2)) / 2)          # 4次元ぶんのビット数

CONFIGS = [
    ("k-means k=4 2^8   (現行)",         dict(k=4, cb_bits=8.0)),
    ("k-means k=4 語数=E8(R2=10)",       dict(k=4, cb_bits=kmeans_match(10))),
    ("E8      R2=10",                    dict(k=8, lattice="e8", R2=10.0)),
    ("k-means k=4 語数=E8(R2=12)",       dict(k=4, cb_bits=kmeans_match(12))),
    ("E8      R2=12",                    dict(k=8, lattice="e8", R2=12.0)),
]
LAYERS = sys.argv[1:] or ["blk.4.attn_q.weight", "blk.4.ffn_gate.weight",
                          "blk.20.attn_output.weight", "blk.4.ffn_down.weight"]

for name in LAYERS:
    W, Xa, Xb = load(name)
    base = np.linalg.norm(W @ Xb)
    print(f"\n[{name}]  {W.shape}  標本 {Xa.shape[1]}/{Xb.shape[1]}", flush=True)
    print(f"  {'方式':<32} {'bit':>6}  {'出力誤差':>8}  {'重み誤差':>8}  {'秒':>4}", flush=True)
    ref = None
    for label, kw in CONFIGS:
        t = time.time()
        Wh, bpw = RP.fit(W, Xa, rank=32, G=256, adaround=True, **kw)
        eo = float(np.linalg.norm((Wh - W) @ Xb) / base)
        ew = float(np.linalg.norm(Wh - W) / np.linalg.norm(W))
        if ref is None:
            ref = eo
        print(f"  {label:<32} {bpw:6.3f}  {eo:8.4f}  {ew:8.4f}  {time.time()-t:4.0f}"
              f"   ({(1-eo/ref)*100:+.1f}% 対現行)", flush=True)
