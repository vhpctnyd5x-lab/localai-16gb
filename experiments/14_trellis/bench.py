"""実験14: トレリス符号化 vs 我々のk-means辞書（実重み・同じビット予算で）。

トレリスは合成ガウスでは理論限界に迫った。実際の重みでも勝てるのか。
評価は本物の活性化統計(imatrix)による重みつき出力誤差。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate, trellis

MODEL = ("/path/to/localai/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
CAL = os.path.join(ROOT, "data", "calib")


def load_imat(path):
    r = gguf.Reader(path); out = {}
    for name, dims, _ in r.list_tensors():
        if not name.endswith(".in_sum2"): continue
        v, _ = r.load(name); c, _ = r.load(name.replace(".in_sum2", ".counts"))
        out[name[:-8]] = np.asarray(v, np.float64).ravel()/float(np.asarray(c).ravel()[0])
    return out


def werr(W, Wh, imat):
    d = ((W-Wh)**2).sum(0)*imat; b = (W**2).sum(0)*imat
    return float(np.sqrt(d.sum()/b.sum()))


def inner_rotate(A, B, seed=0):
    r = A.shape[1]; d = rotate.signs(r, seed); s = 1/np.sqrt(r)
    return rotate.fwht(A)*d*s, (rotate.fwht(B.T).T)*d[:, None]*s


def lowrank(W, r, lr_bits, G, seed=0):
    out, inn = W.shape
    U, S, Vt = np.linalg.svd(W, full_matrices=False)
    A, B = inner_rotate(U[:, :r]*S[:r], Vt[:r], seed)
    Aq = C.rtn(A, lr_bits, min(G, A.shape[1]))[0]
    Bq = C.rtn(B, lr_bits, min(G, B.shape[1]))[0]
    bpw = r*(out+inn)*lr_bits/(out*inn) + 16*(A.size/min(G,A.shape[1])+B.size/min(G,B.shape[1]))/(out*inn)
    return Aq@Bq, bpw


tr = load_imat(os.path.join(CAL, "imat_train.imatrix"))
te = load_imat(os.path.join(CAL, "imat_test.imatrix"))
r_ = gguf.Reader(MODEL)
rows = []
for TENSOR in ["blk.10.attn_q.weight", "blk.0.ffn_gate.weight"]:
    W0, tname = r_.load(TENSOR); W0 = np.ascontiguousarray(W0.astype(np.float32))
    if TENSOR not in tr: continue
    imat_tr, imat_te = tr[TENSOR], te[TENSOR]
    # 重要度スケーリング(α=0.75、実験12で最適)
    s = imat_tr ** 0.375; s = s/np.exp(np.log(s).mean())
    W = W0*s[None, :]; im_te = imat_te/s**2
    print(f"\n=== {TENSOR} {W0.shape} 元={tname} ===")
    print(f"{'方式':<44}{'bit/重み':>9}{'誤差':>9}{'秒':>8}")
    print("-"*72)
    for r, lrb in [(32, 4)]:
        LR, lr_bpw = lowrank(W, r, lrb, 128)
        R = W - LR
        # (a) 既存: k-means辞書
        for k, cb, G in [(8, 8, 256), (16, 16, 256), (8, 4, 256)]:
            t0 = time.time()
            Rh, bpw, _ = C.pvq(R, k=k, cb_bits=cb, G=G)
            e = werr(W, LR+Rh, im_te)
            print(f"{f'ランク{r}+kmeans k={k},コード{2**cb}':<44}{lr_bpw+bpw:>9.3f}{e:>9.4f}{time.time()-t0:>8.1f}")
            rows.append(dict(tensor=TENSOR, 方式=f"kmeans k={k} cb={cb}",
                             bpw=round(float(lr_bpw+bpw),4), 誤差=round(e,5)))
        # (b) トレリス（1bit/重み）
        for L, G in [(10, 256), (12, 256)]:
            t0 = time.time()
            Rh, bpw = trellis.quantize_matrix(R, G=G, L=L)
            e = werr(W, LR+Rh, im_te)
            print(f"{f'ランク{r}+トレリス L={L}':<44}{lr_bpw+bpw:>9.3f}{e:>9.4f}{time.time()-t0:>8.1f}")
            rows.append(dict(tensor=TENSOR, 方式=f"trellis L={L}",
                             bpw=round(float(lr_bpw+bpw),4), 誤差=round(e,5)))
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "results","trellis.json"),"w"), ensure_ascii=False, indent=2)
print("\n保存完了")
