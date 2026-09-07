import os
"""実験17: 誤差補償(GPTQ)の決着。本物の活性化で再評価する。

序盤に合成活性化で全敗した件。実装は厳密OBQと15桁一致することを検証済みで、
原因は「合成データへの過学習」と診断していた。本物の活性化で覆るか。

較正用と採点用は本文の別区間から採っている（自己採点にならない）。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate

MODEL = (os.environ.get("MODEL_BLOB") or "/path/to/localai/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
acts = np.load(os.path.join(ROOT, "data/calib/acts_big.npz"))
r_ = gguf.Reader(MODEL)


def hess(X, damp):
    H = (X @ X.T).astype(np.float64)/X.shape[1]
    H[np.diag_indices_from(H)] += damp*np.mean(np.diag(H))
    return H


def gptq(W, X, bits, G, damp):
    """列を1本ずつ丸め、誤差をヘッセ行列に基づいて右側へ流す。"""
    n = W.shape[1]
    # ★ 2026-09-07: 数値誤差で ほんの少し非正定値になると cholesky が落ちる。

    # 落ちたら 対角に少しずつ足して 正定値に押し戻す。

    _M = (lambda A:(A+A.T)/2)(np.linalg.inv(hess(X, damp)))

    for _t in range(6):

        try:

            U = np.linalg.cholesky(_M).T

            break

        except np.linalg.LinAlgError:

            _M = _M + np.eye(_M.shape[0]) * (10.0 ** (-10 + _t)) * np.trace(_M) / _M.shape[0]

    else:

        raise np.linalg.LinAlgError("対角を足しても正定値にできませんでした")
    Wq = W.astype(np.float64).copy(); qmax = 2**(bits-1)-1
    for st in range(0, n, G):
        en = min(st+G, n)
        s = np.abs(W[:, st:en]).max(1, keepdims=True); s[s == 0] = 1
        for j in range(st, en):
            w = Wq[:, j:j+1]
            q = np.clip(np.rint(w/s*qmax), -qmax, qmax)/qmax*s
            if j+1 < n: Wq[:, j+1:] -= ((w-q)/U[j, j]) @ U[j:j+1, j+1:]
            Wq[:, j:j+1] = q
    return Wq.astype(np.float32)


rows = []
for name in ["blk.10.attn_q.weight", "blk.20.attn_output.weight"]:
    ktr, kte = f"tr|{name}", f"te|{name}"
    if ktr not in acts: continue
    W, _ = r_.load(name); W = np.ascontiguousarray(W.astype(np.float32))
    Xtr = acts[ktr].T.astype(np.float32)     # (in, 2048)
    Xte = acts[kte].T.astype(np.float32)     # (in, 1024) 別区間
    def score(Wh):
        return float(np.linalg.norm((W-Wh)@Xte)/np.linalg.norm(W@Xte))
    print(f"\n=== {name} {W.shape}  較正{Xtr.shape[1]}本 / 採点{Xte.shape[1]}本(別区間) ===")
    print(f"{'方式':<28}{'誤差(別区間)':>14}{'変化':>9}")
    print("-"*54)
    for bits in (4, 3, 2):
        base = score(C.rtn(W, bits, G=128)[0])
        print(f"{f'RTN {bits}bit':<28}{base:>14.4f}{'(基準)':>9}")
        rows.append(dict(層=name, 方式=f"RTN{bits}", 誤差=round(base,5)))
        for damp in (0.01, 0.1):
            t0=time.time(); e = score(gptq(W, Xtr, bits, 128, damp))
            print(f"{f'  GPTQ {bits}bit damp={damp}':<28}{e:>14.4f}"
                  f"{100*(base-e)/base:>+8.1f}%")
            rows.append(dict(層=name, 方式=f"GPTQ{bits} damp{damp}", 誤差=round(e,5)))
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "results","gptq_real.json"),"w"), ensure_ascii=False, indent=2)
print("\n保存完了")
