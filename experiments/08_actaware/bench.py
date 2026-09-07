import os
"""実験08: 活性化を意識した量子化（チャンネル重要度スケーリング）。

評議会が繰り返し指摘した本質的な問題:
  いまの量子化は「重みの誤差」を最小化しているが、本当に守りたいのは「出力の誤差」。
  よく使われる入力チャンネルの重みは大事、ほとんど使われないチャンネルは雑でよい。

対策は単純で、量子化の前に列ごとの物差しを変える:
    W' = W · diag(s),   x' = diag(s)^-1 · x     (W'x' = Wx なので出力は不変)
  s を活性化の大きさから決めると、大事な列が「大きく」なり、量子化が自然にそこを丁寧に扱う。

GPTQ と違い、使うのは**チャンネルごとのスケール1024個だけ**（ヘッセ行列100万個ではない）。
推定する量が桁違いに少ないので、過学習しにくいはず——というのが検証したい仮説。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate

BLOB = (os.environ.get("MODEL_BLOB") or "/path/to/localai/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")


def inner_rotate(A, B, seed=0):
    r = A.shape[1]
    d = rotate.signs(r, seed)
    s = 1.0 / np.sqrt(r)
    return rotate.fwht(A) * d * s, (rotate.fwht(B.T).T) * d[:, None] * s


def recipe(W, r, lr_bits, k, cb_bits, G, seed=0):
    """主力レシピ（内側回転あり）。"""
    out, inn = W.shape
    U, S, Vt = np.linalg.svd(W, full_matrices=False)
    A, B = inner_rotate(U[:, :r] * S[:r], Vt[:r], seed)
    Aq = C.rtn(A, lr_bits, min(G, A.shape[1]))[0]
    Bq = C.rtn(B, lr_bits, min(G, B.shape[1]))[0]
    Rh, res_bpw, _ = C.pvq(W - Aq @ Bq, k=k, cb_bits=cb_bits, G=G, seed=seed)
    lr_bpw = r * (out + inn) * lr_bits / (out * inn)
    ovh = 16 * (A.size / min(G, A.shape[1]) + B.size / min(G, B.shape[1])) / (out * inn)
    return (Aq @ Bq + Rh).astype(np.float32), lr_bpw + res_bpw + ovh


r_ = gguf.Reader(BLOB)
allrows = []
for TENSOR in ["v.blk.0.mlp.linear_fc1.weight", "blk.0.attn_qkv.weight"]:
    W0, tname = r_.load(TENSOR)
    W0 = np.ascontiguousarray(W0.astype(np.float32))
    out, inn = W0.shape
    if inn & (inn - 1):
        p = 1 << (inn.bit_length() - 1)
        W0 = np.ascontiguousarray(W0[:, :p]); inn = p

    def acts(ns, seed):
        rng = np.random.default_rng(seed)
        X = rng.standard_t(4, size=(inn, ns)).astype(np.float32)
        X[rng.choice(inn, max(1, inn // 100), replace=False)] *= 20.
        return X
    Xcal, Xev = acts(4096, 0), acts(128, 999)          # 較正用と評価用は別データ
    chan = np.sqrt((Xcal ** 2).mean(1))                # チャンネルごとの大きさ
    chan /= chan.mean()

    print(f"\n=== {TENSOR} {W0.shape} 元={tname} ===")
    print(f"{'設定':<40}{'bit/重み':>9}{'出力誤差':>10}{'改善':>9}")
    print("-" * 68)
    for r, lrb, k, cb in [(32, 4, 8, 4), (64, 4, 8, 4), (64, 4, 8, 8)]:
        base = None
        for alpha in (0.0, 0.25, 0.5, 0.75, 1.0):
            s = chan ** alpha
            s = s / np.exp(np.log(s).mean())            # 幾何平均を1に正規化
            W = W0 * s[None, :]                         # W' = W diag(s)
            Xe = Xev / s[:, None]                       # x' = diag(s)^-1 x
            Wh, bpw = recipe(W, r, lrb, k, cb, 128)
            _, ry = C.evaluate(W, Wh, X=Xe)
            if base is None:
                base = ry; mark = "(基準)"
            else:
                mark = f"{100*(base-ry)/base:+.1f}%"
            print(f"{f'ランク{r}+PVQコード{2**cb}  重要度^{alpha}':<40}"
                  f"{bpw:>9.3f}{ry:>10.4f}{mark:>9}")
            allrows.append(dict(tensor=TENSOR, rank=r, cb_bits=cb, alpha=alpha,
                                bpw=round(float(bpw), 4), 出力誤差=round(float(ry), 5)))

json.dump(allrows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "results", "actaware.json"), "w"),
          ensure_ascii=False, indent=2)
print("\n保存完了")
