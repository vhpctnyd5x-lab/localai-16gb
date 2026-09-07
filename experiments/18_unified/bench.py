import os
"""実験18: 統合レシピ。手札を1つずつ足して効果を積み上げる。"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate, recipe as RP, reconstruct as RC

MODEL = (os.environ.get("MODEL_BLOB") or "/path/to/localai/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
acts = np.load(os.path.join(ROOT, "data/calib/acts_big.npz"))
r_ = gguf.Reader(MODEL)


def old_way(W, rank, k, cb, G, seed=0):
    out, inn = W.shape
    r = 1 << (min(rank, min(out, inn)//2).bit_length()-1)
    U, S, Vt = np.linalg.svd(W, full_matrices=False)
    A, B = RP.inner_rotate(U[:, :r]*S[:r], Vt[:r], seed)
    Aq = C.rtn(A, 4, min(G, A.shape[1]))[0]; Bq = C.rtn(B, 4, min(G, B.shape[1]))[0]
    Res, _, _ = C.pvq(W-Aq@Bq, k=k, cb_bits=cb, G=G, seed=seed)
    lr = r*(out+inn)*4/(out*inn)
    ovh = 16*(Aq.size/min(G,Aq.shape[1])+Bq.size/min(G,Bq.shape[1]))/(out*inn)
    return (Aq@Bq+Res).astype(np.float32), lr+cb/k+16.0/G+ovh


rows = []
for name in ["blk.10.attn_q.weight", "blk.20.attn_output.weight"]:
    W, _ = r_.load(name); W = np.ascontiguousarray(W.astype(np.float32))
    Xtr = acts[f"tr|{name}"].T.astype(np.float32)
    Xte = acts[f"te|{name}"].T.astype(np.float32)
    sc = lambda Wh: float(np.linalg.norm((W-Wh)@Xte)/np.linalg.norm(W@Xte))
    print(f"\n=== {name} {W.shape} ===")
    print(f"{'構成':<44}{'bit':>7}{'誤差(別区間)':>14}{'改善':>9}")
    print("-"*76)
    for k, cb, G in [(8, 8, 256), (16, 8, 256)]:
        base = None
        for tag, fn in [
            ("従来(重み誤差の最小化)", lambda: old_way(W, 32, k, cb, G)),
            ("+出力再構成", lambda: RC.fit(W, Xtr, rank=32, k=k, cb_bits=cb, G=G)[:2]),
            ("+出力再構成+誤差補償(統合)", lambda: RP.fit(W, Xtr, rank=32, k=k, cb_bits=cb, G=G)),
        ]:
            t0=time.time(); Wh, bpw = fn(); e = sc(Wh); dt=time.time()-t0
            mark = "(基準)" if base is None else f"{100*(base-e)/base:+.1f}%"
            if base is None: base = e
            print(f"{f'{tag} k={k},コード{2**cb}':<44}{bpw:>7.3f}{e:>14.4f}{mark:>9}  {dt:.0f}秒")
            rows.append(dict(層=name, 構成=tag, k=k, bpw=round(float(bpw),4), 誤差=round(e,5)))
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "results","unified.json"),"w"), ensure_ascii=False, indent=2)
print("\n保存完了")
