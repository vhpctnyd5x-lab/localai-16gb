"""実験12: 本物の活性化で、全敗した手法を再評価する。

これまでの実験は「重みは qwen3.5、活性化は合成」というちぐはぐな条件だった。
今回は **重みも活性化も同じ qwen2.5-coder:3b** から取る。

較正テキストを前半・後半に分けて独立に活性化統計を採ったので、
「前半で決めて後半で採点する」ができる。自己採点にならない。

評価指標（imatrix が対角成分しか持たないことを踏まえた正確な形）:
    出力誤差² = Σ_j  imat_j · ‖ΔW[:,j]‖²   /   Σ_j  imat_j · ‖W[:,j]‖²
これは活性化のチャンネル間相関を無視した近似だが、サンプリング誤差が無く、
imat_test を使うかぎり完全にホールドアウトになっている。
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate

MODEL = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
CAL = os.path.join(ROOT, "data", "calib")


def load_imat(path):
    r = gguf.Reader(path)
    out = {}
    for name, dims, _ in r.list_tensors():
        if not name.endswith(".in_sum2"):
            continue
        v, _ = r.load(name)
        c, _ = r.load(name.replace(".in_sum2", ".counts"))
        out[name[:-8]] = np.asarray(v, np.float64).ravel() / float(np.asarray(c).ravel()[0])
    return out


def werr(W, Wh, imat):
    """重要度で重みづけした出力誤差。"""
    d = ((W - Wh) ** 2).sum(0) * imat
    b = (W ** 2).sum(0) * imat
    return float(np.sqrt(d.sum() / b.sum()))


def inner_rotate(A, B, seed=0):
    r = A.shape[1]; d = rotate.signs(r, seed); s = 1/np.sqrt(r)
    return rotate.fwht(A)*d*s, (rotate.fwht(B.T).T)*d[:, None]*s


def recipe(W, r, lr_bits, k, cb_bits, G, seed=0):
    out, inn = W.shape
    U, S, Vt = np.linalg.svd(W, full_matrices=False)
    A, B = inner_rotate(U[:, :r]*S[:r], Vt[:r], seed)
    Aq = C.rtn(A, lr_bits, min(G, A.shape[1]))[0]
    Bq = C.rtn(B, lr_bits, min(G, B.shape[1]))[0]
    Rh, res_bpw, _ = C.pvq(W - Aq@Bq, k=k, cb_bits=cb_bits, G=G, seed=seed)
    lr_bpw = r*(out+inn)*lr_bits/(out*inn)
    ovh = 16*(A.size/min(G, A.shape[1]) + B.size/min(G, B.shape[1]))/(out*inn)
    return (Aq@Bq+Rh).astype(np.float32), lr_bpw+res_bpw+ovh


tr = load_imat(os.path.join(CAL, "imat_train.imatrix"))
te = load_imat(os.path.join(CAL, "imat_test.imatrix"))
r_ = gguf.Reader(MODEL)

# 前半と後半で重要度がどれだけ一致するか（そもそも安定した量なのか）
ks = [k for k in tr if k in te][:200]
cors = []
for k in ks:
    a, b = np.log(tr[k]+1e-30), np.log(te[k]+1e-30)
    cors.append(np.corrcoef(a, b)[0, 1])
print(f"前半と後半の重要度の相関: 中央値 {np.median(cors):.3f} "
      f"(最小 {min(cors):.3f} / 最大 {max(cors):.3f})")
print("→ 1.0に近いほど『重要度は文章によらない安定した性質』を意味する\n")

rows = []
for TENSOR in ["blk.0.ffn_gate.weight", "blk.10.attn_q.weight", "blk.20.ffn_up.weight"]:
    if TENSOR not in tr:
        continue
    W0, tname = r_.load(TENSOR)
    W0 = np.ascontiguousarray(W0.astype(np.float32))
    imat_tr, imat_te = tr[TENSOR], te[TENSOR]
    if W0.shape[1] != len(imat_tr):
        print(f"{TENSOR}: 次元不一致 {W0.shape} vs {len(imat_tr)} → 飛ばす")
        continue
    print(f"=== {TENSOR} {W0.shape} 元={tname} ===")
    print(f"{'設定':<38}{'bit/重み':>9}{'誤差(本物)':>11}{'変化':>9}")
    print("-"*68)
    for r, k, cb in [(32, 8, 4), (32, 32, 8), (64, 8, 8)]:
        base = None
        for alpha in (0.0, 0.25, 0.5, 0.75, 1.0):
            s = imat_tr ** (alpha/2)              # 重要度の平方根を α 乗
            s = s/np.exp(np.log(s).mean())
            W = W0 * s[None, :]
            Wh, bpw = recipe(W, r, 4, k, cb, 128)
            e = werr(W, Wh, imat_te / s**2)       # 元の空間での誤差に戻して採点
            mark = "(基準)" if base is None else f"{100*(base-e)/base:+.1f}%"
            if base is None: base = e
            print(f"{f'ランク{r}+k={k},コード{2**cb} 重要度^{alpha}':<38}{bpw:>9.3f}{e:>11.4f}{mark:>9}")
            rows.append(dict(tensor=TENSOR, rank=r, k=k, cb_bits=cb, alpha=alpha,
                             bpw=round(float(bpw),4), 誤差=round(e,5)))
    print()

json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "results","realact.json"),"w"), ensure_ascii=False, indent=2)
print("保存完了")
