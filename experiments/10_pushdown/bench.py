"""実験10: ビット数をさらに押し下げる。

これまでの最良は 0.79bit で誤差0.45。ここから「もっと薄く」を攻める。
使える手札を全部重ねる:
  - 低ランク + 残差PVQ（主力）
  - 内側回転（コストゼロ、実証済み）
  - スケールの最小二乗（安い）
  - スケール自体の量子化（fp16スケールは0.125bit/重み食っている。ここも削る）
  - グループを大きくしてスケール個数を減らす
  - エントロピー符号化後の実効ビット（実証済み3〜5%）
狙いは 0.5bit/重み以下での最良点を見つけること。
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate, entropy as E

BLOB = ("/path/to/localai/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")


def inner_rotate(A, B, seed=0):
    r = A.shape[1]; d = rotate.signs(r, seed); s = 1/np.sqrt(r)
    return rotate.fwht(A)*d*s, (rotate.fwht(B.T).T)*d[:, None]*s


def pvq_full(W, k, cb_bits, G, scale_bits=16, ls=True, seed=0):
    """残差用PVQ。スケールも量子化して、その分のビットを正直に数える。"""
    X = C._grouped(W, G)
    s = C._scales(X)
    if scale_bits < 16:
        # スケールは対数領域で量子化（桁が広いので）
        ls_ = np.log2(s)
        lo, hi = ls_.min(), ls_.max()
        q = np.rint((ls_-lo)/max(hi-lo, 1e-9)*(2**scale_bits-1))
        s = 2**(lo + q/(2**scale_bits-1)*(hi-lo))
    Xn = (X/s).reshape(-1, k).astype(np.float32)
    Cb = C._kmeans(Xn, 2**cb_bits, seed=seed)
    idx = C._assign(Xn, Cb)
    rec = Cb[idx].reshape(X.shape)
    if ls:
        num = (X*rec).sum(1, keepdims=True); den = (rec*rec).sum(1, keepdims=True)
        den[den == 0] = 1
        s2 = num/den
        # 解き直したスケールも同じビット数で量子化しないと不公平
        if scale_bits < 16:
            l2 = np.log2(np.abs(s2)+1e-30); lo, hi = l2.min(), l2.max()
            q = np.rint((l2-lo)/max(hi-lo, 1e-9)*(2**scale_bits-1))
            s2 = np.sign(s2)*2**(lo+q/(2**scale_bits-1)*(hi-lo))
        s = s2
    Wh = (rec*s).reshape(W.shape).astype(np.float32)
    bpw = cb_bits/k + scale_bits/G
    ent = E.entropy(np.bincount(idx, minlength=2**cb_bits))/k + scale_bits/G
    return Wh, bpw, ent


def recipe(W, r, lr_bits, k, cb_bits, G, scale_bits=16, seed=0):
    out, inn = W.shape
    if r == 0:                      # 低ランクなし（残差量子化のみ）
        Rh, res_bpw, res_ent = pvq_full(W, k, cb_bits, G, scale_bits, seed=seed)
        return Rh, res_bpw, res_ent
    U, S, Vt = np.linalg.svd(W, full_matrices=False)
    A, B = inner_rotate(U[:, :r]*S[:r], Vt[:r], seed)
    Aq = C.rtn(A, lr_bits, min(G, A.shape[1]))[0]
    Bq = C.rtn(B, lr_bits, min(G, B.shape[1]))[0]
    Rh, res_bpw, res_ent = pvq_full(W - Aq@Bq, k, cb_bits, G, scale_bits, seed=seed)
    lr_bpw = r*(out+inn)*lr_bits/(out*inn)
    ovh = 16*(A.size/min(G, A.shape[1]) + B.size/min(G, B.shape[1]))/(out*inn)
    return (Aq@Bq+Rh).astype(np.float32), lr_bpw+res_bpw+ovh, lr_bpw+res_ent+ovh


r_ = gguf.Reader(BLOB)
W0, tname = r_.load("v.blk.0.mlp.linear_fc1.weight")
W0 = np.ascontiguousarray(W0.astype(np.float32))
inn = W0.shape[1]
rng = np.random.default_rng(999)
X = rng.standard_t(4, size=(inn, 128)).astype(np.float32)
X[rng.choice(inn, inn//100, replace=False)] *= 20.

print(f"対象: v.blk.0.mlp.linear_fc1.weight {W0.shape} 元={tname}")
print(f"{'設定':<52}{'bit/重み':>9}{'符号化後':>10}{'出力誤差':>10}")
print("-"*82)
rows = []
configs = []
for r in (0, 8, 16, 32):
    for k, cb in [(8, 2), (8, 3), (8, 4), (16, 4), (16, 6), (32, 8)]:
        for G, sb in [(128, 16), (256, 8), (512, 8)]:
            configs.append((r, 4, k, cb, G, sb))
for r, lrb, k, cb, G, sb in configs:
    if G % k: continue
    Wh, bpw, ent = recipe(W0, r, lrb, k, cb, G, sb)
    if bpw > 0.72: continue          # 0.72bit以下だけ見る
    _, ry = C.evaluate(W0, Wh, X=X)
    tag = f"ランク{r}+PVQ k={k},コード{2**cb},G={G},スケール{sb}bit"
    print(f"{tag:<52}{bpw:>9.3f}{ent:>10.3f}{ry:>10.4f}")
    rows.append(dict(rank=r, k=k, cb_bits=cb, G=G, scale_bits=sb,
                     bpw=round(float(bpw),4), 符号化後=round(float(ent),4),
                     出力誤差=round(float(ry),5)))
rows.sort(key=lambda d: d["出力誤差"])
print("\n--- 誤差の良い順 上位8 ---")
for d in rows[:8]:
    print(f"  {d['符号化後']:.3f}bit  誤差{d['出力誤差']:.4f}  "
          f"ランク{d['rank']} k={d['k']} コード{2**d['cb_bits']} G={d['G']} スケール{d['scale_bits']}bit")
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "results","pushdown.json"),"w"), ensure_ascii=False, indent=2)
print("\n保存完了")
