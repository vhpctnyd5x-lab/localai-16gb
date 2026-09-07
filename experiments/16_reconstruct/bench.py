"""実験16: 出力再構成の効果。

これまで: min‖W−Ŵ‖（重み誤差）
今回:     min‖(W−Ŵ)X‖（出力誤差）  X=本物の活性化

採点は必ず「別の活性化」で行う。較正データで採点すると自己採点になる。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate, reconstruct as RC

MODEL = ("/path/to/localai/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
acts = np.load(os.path.join(ROOT, "data/calib/acts256.npz"))
r_ = gguf.Reader(MODEL)


def inner_rotate(A, B, seed=0):
    r = A.shape[1]; d = rotate.signs(r, seed); s = 1/np.sqrt(r)
    return rotate.fwht(A)*d*s, (rotate.fwht(B.T).T)*d[:, None]*s


def old_way(W, rank, k, cb, G, seed=0):
    """従来: 重み誤差を最小化（SVD＋k-means）"""
    out, inn = W.shape
    r = 1 << (min(rank, min(out, inn)//2).bit_length()-1)
    U, S, Vt = np.linalg.svd(W, full_matrices=False)
    A, B = inner_rotate(U[:, :r]*S[:r], Vt[:r], seed)
    Aq = C.rtn(A, 4, min(G, A.shape[1]))[0]
    Bq = C.rtn(B, 4, min(G, B.shape[1]))[0]
    Dp = W - Aq@Bq
    pad = (-inn) % G
    if pad: Dp = np.pad(Dp, ((0,0),(0,pad)))
    Res, _, _ = C.pvq(Dp, k=k, cb_bits=cb, G=G, seed=seed)
    Wh = Aq@Bq + Res[:, :inn]
    lr = r*(out+inn)*4/(out*inn)
    ovh = 16*(Aq.size/min(G,Aq.shape[1])+Bq.size/min(G,Bq.shape[1]))/(out*inn)
    return Wh.astype(np.float32), lr+cb/k+16.0/G+ovh


rows = []
print(f"{'層':<26}{'方式':<10}{'bit':>6}{'出力誤差(別データ)':>18}{'改善':>9}")
print("-"*72)
for name in ["blk.0.ffn_gate.weight", "blk.10.attn_q.weight",
             "blk.20.attn_output.weight", "blk.35.attn_q.weight"]:
    if name not in acts: continue
    W, _ = r_.load(name); W = np.ascontiguousarray(W.astype(np.float32))
    Xall = acts[name].T.astype(np.float32)          # (in, sample)
    n = Xall.shape[1]
    Xtr, Xte = Xall[:, :n//2], Xall[:, n//2:]        # 較正用と採点用を分ける
    def score(Wh):
        d = (W-Wh)@Xte; b = W@Xte
        return float(np.linalg.norm(d)/np.linalg.norm(b))
    base = None
    for tag, fn in [("従来", lambda: old_way(W, 32, 8, 8, 256)),
                    ("再構成", lambda: RC.fit(W, Xtr, rank=32, k=8, cb_bits=8, G=256)[:2])]:
        t0=time.time(); Wh, bpw = fn(); e = score(Wh)
        mark = "(基準)" if base is None else f"{100*(base-e)/base:+.1f}%"
        if base is None: base = e
        print(f"{name:<26}{tag:<10}{bpw:>6.3f}{e:>18.4f}{mark:>9}")
        rows.append(dict(層=name, 方式=tag, bpw=round(float(bpw),4), 誤差=round(e,5)))
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "results","recon.json"),"w"), ensure_ascii=False, indent=2)
print("\n保存完了")
