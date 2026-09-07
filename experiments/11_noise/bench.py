"""実験11: ノイズの床を測る。

k-means は初期値によって結果が変わる。同じ設定でも実行ごとに誤差が揺れる。
その揺れ幅より小さい「改善」は、改善ではなく偶然である。
これまで報告した小さな利得（回転+3%、エントロピー+4%、交互精錬+1%）が
本物かどうかを判定するための基準線を作る。
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate

BLOB = ("/path/to/localai/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")


def inner_rotate(A, B, seed=0):
    r = A.shape[1]; d = rotate.signs(r, seed); s = 1/np.sqrt(r)
    return rotate.fwht(A)*d*s, (rotate.fwht(B.T).T)*d[:, None]*s


def recipe(W, r, lr_bits, k, cb_bits, G, rot=True, seed=0):
    out, inn = W.shape
    U, S, Vt = np.linalg.svd(W, full_matrices=False)
    A, B = U[:, :r]*S[:r], Vt[:r]
    if rot:
        A, B = inner_rotate(A, B, seed)
    Aq = C.rtn(A, lr_bits, min(G, A.shape[1]))[0]
    Bq = C.rtn(B, lr_bits, min(G, B.shape[1]))[0]
    Rh, res_bpw, _ = C.pvq(W - Aq@Bq, k=k, cb_bits=cb_bits, G=G, seed=seed)
    lr_bpw = r*(out+inn)*lr_bits/(out*inn)
    ovh = 16*(A.size/min(G, A.shape[1]) + B.size/min(G, B.shape[1]))/(out*inn)
    return (Aq@Bq+Rh).astype(np.float32), lr_bpw+res_bpw+ovh


r_ = gguf.Reader(BLOB)
W0, _ = r_.load("v.blk.0.mlp.linear_fc1.weight")
W0 = np.ascontiguousarray(W0.astype(np.float32))
inn = W0.shape[1]
rng = np.random.default_rng(999)
X = rng.standard_t(4, size=(inn, 128)).astype(np.float32)
X[rng.choice(inn, inn//100, replace=False)] *= 20.

SEEDS = range(8)
print("同一設定を8シードで実行し、ばらつきを測る\n")
print(f"{'設定':<34}{'平均':>9}{'標準偏差':>10}{'最小':>9}{'最大':>9}{'変動幅':>9}")
print("-"*80)
out = {}
for label, kw in [("ランク32+コード16 回転なし", dict(r=32, rot=False, k=8, cb_bits=4)),
                  ("ランク32+コード16 回転あり", dict(r=32, rot=True,  k=8, cb_bits=4)),
                  ("ランク64+コード256 回転なし", dict(r=64, rot=False, k=8, cb_bits=8)),
                  ("ランク64+コード256 回転あり", dict(r=64, rot=True,  k=8, cb_bits=8))]:
    vals = []
    for sd in SEEDS:
        Wh, bpw = recipe(W0, kw["r"], 4, kw["k"], kw["cb_bits"], 128,
                         rot=kw["rot"], seed=sd)
        vals.append(float(C.evaluate(W0, Wh, X=X)[1]))
    v = np.array(vals)
    print(f"{label:<34}{v.mean():>9.4f}{v.std():>10.5f}{v.min():>9.4f}{v.max():>9.4f}"
          f"{100*(v.max()-v.min())/v.mean():>8.1f}%")
    out[label] = dict(平均=round(float(v.mean()),5), 標準偏差=round(float(v.std()),6),
                      最小=round(float(v.min()),5), 最大=round(float(v.max()),5),
                      値=[round(x,5) for x in vals])

# 回転の効果が、ばらつきを超えているかを判定
for a, b in [("ランク32+コード16 回転なし", "ランク32+コード16 回転あり"),
             ("ランク64+コード256 回転なし", "ランク64+コード256 回転あり")]:
    A = np.array(out[a]["値"]); B = np.array(out[b]["値"])
    diff = A - B                     # 正なら回転が改善
    se = diff.std(ddof=1)/np.sqrt(len(diff))
    t = diff.mean()/se if se > 0 else float("inf")
    print(f"\n{a.split()[0]}: 回転の効果 = {100*diff.mean()/A.mean():+.2f}%  "
          f"(t値 {t:+.2f} / 目安|t|>2.4で有意)")

json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "results","noise.json"),"w"), ensure_ascii=False, indent=2)
print("\n保存完了")
