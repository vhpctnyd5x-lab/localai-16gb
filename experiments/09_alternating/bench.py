"""実験09: 低ランクと残差を交互に精錬する（活性化に依存しない路線）。

いまは SVD で低ランクを決め、その残差を1回だけ量子化して終わり。
だが残差を量子化した時点で誤差が出るので、低ランク側は「最適な相棒」ではなくなる。
そこで交互に解き直す:
    A,B を固定 → 残差を量子化
    量子化残差を固定 → W - Rh に対して低ランクを取り直す
を数回まわす。ビットコストは増えない（保存するものは同じ）。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate

BLOB = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")


def inner_rotate(A, B, seed=0):
    r = A.shape[1]; d = rotate.signs(r, seed); s = 1/np.sqrt(r)
    return rotate.fwht(A)*d*s, (rotate.fwht(B.T).T)*d[:, None]*s


def fit(W, r, lr_bits, k, cb_bits, G, rounds=1, seed=0):
    out, inn = W.shape
    Rh = np.zeros_like(W)
    for it in range(rounds):
        U, S, Vt = np.linalg.svd(W - Rh, full_matrices=False)
        A, B = inner_rotate(U[:, :r]*S[:r], Vt[:r], seed)
        Aq = C.rtn(A, lr_bits, min(G, A.shape[1]))[0]
        Bq = C.rtn(B, lr_bits, min(G, B.shape[1]))[0]
        Rh, res_bpw, _ = C.pvq(W - Aq @ Bq, k=k, cb_bits=cb_bits, G=G, seed=seed)
    lr_bpw = r*(out+inn)*lr_bits/(out*inn)
    ovh = 16*(A.size/min(G, A.shape[1]) + B.size/min(G, B.shape[1]))/(out*inn)
    return (Aq @ Bq + Rh).astype(np.float32), lr_bpw+res_bpw+ovh


r_ = gguf.Reader(BLOB); rows = []
for TENSOR in ["v.blk.0.mlp.linear_fc1.weight", "blk.0.attn_qkv.weight"]:
    W0, tname = r_.load(TENSOR); W0 = np.ascontiguousarray(W0.astype(np.float32))
    inn = W0.shape[1]
    if inn & (inn-1):
        p = 1 << (inn.bit_length()-1); W0 = np.ascontiguousarray(W0[:, :p]); inn = p
    rng = np.random.default_rng(999)
    X = rng.standard_t(4, size=(inn, 128)).astype(np.float32)
    X[rng.choice(inn, max(1, inn//100), replace=False)] *= 20.
    print(f"\n=== {TENSOR} {W0.shape} 元={tname} ===")
    print(f"{'設定':<40}{'bit/重み':>9}{'出力誤差':>10}{'改善':>9}")
    print("-"*68)
    for r, lrb, k, cb in [(32,4,8,4), (64,4,8,4), (64,4,8,8), (128,4,16,8)]:
        base = None
        for rounds in (1, 2, 3):
            Wh, bpw = fit(W0, r, lrb, k, cb, 128, rounds)
            _, ry = C.evaluate(W0, Wh, X=X)
            mark = "(基準)" if base is None else f"{100*(base-ry)/base:+.1f}%"
            if base is None: base = ry
            print(f"{f'ランク{r}+PVQコード{2**cb}  {rounds}周':<40}{bpw:>9.3f}{ry:>10.4f}{mark:>9}")
            rows.append(dict(tensor=TENSOR, rank=r, cb_bits=cb, rounds=rounds,
                             bpw=round(float(bpw),4), 出力誤差=round(float(ry),5)))
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "results","alternating.json"),"w"),
          ensure_ascii=False, indent=2)
print("\n保存完了")
