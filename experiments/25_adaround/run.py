"""実験25: AdaRound方式の割り当ての効果を測る。

「いちばん近い値に丸める」をやめ、**出力誤差でいちばん近いコード**を選ぶ。
5モデル中4モデルが独立に挙げた手法（AdaRound）の中核だけを取り出したもの。

採点は必ず**別区間の活性化**で行う（訓練区間で測ると過学習を見逃す）。
指標は出力空間の相対誤差。重み誤差は当てにならない（順位相関 −0.111）。
"""
import os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, recipe as RP

MODEL = (os.environ.get("MODEL_BLOB") or "/path/to/localai/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
acts = np.load(os.path.join(ROOT, "data/calib/acts_big.npz"))
r = gguf.Reader(MODEL)

NAMES = [n for n in ["blk.10.attn_q.weight", "blk.20.attn_output.weight",
                     "blk.5.attn_v.weight", "blk.30.attn_q.weight",
                     "blk.15.attn_output.weight"]
         if f"tr|{n}" in acts and f"te|{n}" in acts]
KS = [(8, 8), (16, 8), (8, 12)]


def err(W, Wh, X):
    return float(np.linalg.norm((W - Wh) @ X) / (np.linalg.norm(W @ X) + 1e-12))


print(f"{'層':<26}{'k/cb':>7}{'従来':>9}{'AdaRound':>10}{'改善':>8}{'秒':>6}", flush=True)
rows = []
for name in NAMES:
    W, _ = r.load(name)
    W = np.ascontiguousarray(W.astype(np.float32))
    Xtr = acts[f"tr|{name}"].T.astype(np.float32)
    Xte = acts[f"te|{name}"].T.astype(np.float32)
    for k, cb in KS:
        t0 = time.time()
        A, _ = RP.fit(W, Xtr, k=k, cb_bits=cb, adaround=False)
        B, _ = RP.fit(W, Xtr, k=k, cb_bits=cb, adaround=True)
        ea, eb = err(W, A, Xte), err(W, B, Xte)
        kai = 100 * (ea - eb) / ea
        rows.append(kai)
        print(f"{name:<26}{f'{k}/{cb}':>7}{ea:>9.4f}{eb:>10.4f}"
              f"{kai:>7.1f}%{time.time()-t0:>6.0f}", flush=True)

if rows:
    a = np.array(rows)
    print(f"\n改善の平均 {a.mean():+.1f}%  中央値 {np.median(a):+.1f}%  "
          f"最良 {a.max():+.1f}%  最悪 {a.min():+.1f}%")
    print(f"改善した設定: {(a>0).sum()}/{len(a)}")
else:
    print("活性化データが見つからない。acts_big.npz のキーを確認すること")
    print("あるキーの例:", list(acts.keys())[:6])
