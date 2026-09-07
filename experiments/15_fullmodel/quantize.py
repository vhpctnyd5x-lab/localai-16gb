"""実験15: モデル全体を我々のレシピで圧縮し、GGUFに書き戻す。

ここまでは1層の誤差しか見ていなかった。ここで初めて
「このモデルは実際どれくらい賢いのか(perplexity)」「何トークン/秒で動くのか」を測る。

方針:
- 大きな線形層(attn/ffn)だけを圧縮する。埋め込み・出力層・正規化は触らない
  （壊れやすく、かつ圧縮の旨みが薄い。世界の手法も同様）。
- 本物の活性化統計(imatrix)による重要度スケーリングを使う(α=0.75、実験12で最適)。
- 出力はF16のGGUF。**ファイルは大きくなるが中身は圧縮済みの値**。
  品質を測るための装置であって、容量削減の実証ではない。
"""
import os, sys, time, json
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, ggufwrite, wcodec as C, rotate

MODEL = (os.environ.get("MODEL_BLOB") or "/path/to/localai/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
CAL = os.path.join(ROOT, "data", "calib")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data/models/ours.gguf")
RANK = int(os.environ.get("RANK", "32"))
K = int(os.environ.get("K", "8"))
CB = int(os.environ.get("CB", "8"))
GRP = int(os.environ.get("GRP", "256"))
ALPHA = float(os.environ.get("ALPHA", "0.75"))


def load_imat(path):
    r = gguf.Reader(path); out = {}
    for name, dims, _ in r.list_tensors():
        if not name.endswith(".in_sum2"): continue
        v, _ = r.load(name); c, _ = r.load(name.replace(".in_sum2", ".counts"))
        out[name[:-8]] = np.asarray(v, np.float64).ravel()/float(np.asarray(c).ravel()[0])
    return out


def inner_rotate(A, B, seed=0):
    r = A.shape[1]; d = rotate.signs(r, seed); s = 1/np.sqrt(r)
    return rotate.fwht(A)*d*s, (rotate.fwht(B.T).T)*d[:, None]*s


def compress(W, imat, rank, k, cb, G, alpha):
    out, inn = W.shape
    if imat is not None and alpha > 0:
        s = imat ** (alpha/2); s = s/np.exp(np.log(s+1e-30).mean())
    else:
        s = np.ones(inn)
    Ws = W * s[None, :]
    r = min(rank, min(out, inn)//2)
    r = 1 << (r.bit_length()-1)                    # 内側回転のため2のべき乗に
    U, S, Vt = np.linalg.svd(Ws, full_matrices=False)
    A, B = inner_rotate(U[:, :r]*S[:r], Vt[:r])
    Aq = C.rtn(A, 4, min(G, A.shape[1]))[0]
    Bq = C.rtn(B, 4, min(G, B.shape[1]))[0]
    R = Ws - Aq@Bq
    pad = (-inn) % G
    if pad: R = np.pad(R, ((0,0),(0,pad)))
    Rh, res_bpw, _ = C.pvq(R, k=k, cb_bits=cb, G=G)
    Rh = Rh[:, :inn]
    Wh = (Aq@Bq + Rh) / s[None, :]
    lr_bpw = r*(out+inn)*4/(out*inn)
    ovh = 16*(A.size/min(G,A.shape[1])+B.size/min(G,B.shape[1]))/(out*inn)
    return Wh.astype(np.float32), lr_bpw+res_bpw+ovh


imat = load_imat(os.path.join(CAL, "qwen25coder3b.imatrix"))
r_ = gguf.Reader(MODEL)
targets = [n for n, (dims, t, off) in r_.tensors.items()
           if len(dims) == 2 and n.startswith("blk.") and n.endswith(".weight")
           and ("attn" in n or "ffn" in n)]
print(f"圧縮対象: {len(targets)}層  設定: ランク{RANK} k={K} コード{2**CB} G={GRP} α={ALPHA}")

replace = {}
tot_w = tot_bits = 0
t0 = time.time()
for i, name in enumerate(targets):
    W, tname = r_.load(name)
    W = np.ascontiguousarray(W.astype(np.float32))
    im = imat.get(name)
    if im is not None and len(im) != W.shape[1]:
        im = None
    Wh, bpw = compress(W, im, RANK, K, CB, GRP, ALPHA)
    replace[name] = Wh
    tot_w += W.size; tot_bits += bpw*W.size
    if i % 20 == 0 or i == len(targets)-1:
        print(f"  [{i+1:3d}/{len(targets)}] {name:<32} {str(W.shape):>14} "
              f"{bpw:.3f}bit  経過{time.time()-t0:.0f}秒", flush=True)

avg = tot_bits/tot_w
print(f"\n平均 {avg:.4f} bit/重み  (圧縮対象 {tot_w/1e9:.2f}B パラメータ)")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
ggufwrite.Copier(MODEL).write(OUT, replace)
print(f"書き出し: {OUT}  {os.path.getsize(OUT)/1e9:.2f}GB")
json.dump(dict(平均bpw=round(float(avg),4), 層数=len(targets),
               設定=dict(rank=RANK,k=K,cb=CB,G=GRP,alpha=ALPHA)),
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "results", os.path.basename(OUT)+".json"), "w"),
          ensure_ascii=False, indent=2)
