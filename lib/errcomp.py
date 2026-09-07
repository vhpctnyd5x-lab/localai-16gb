"""誤差補償つき量子化（GPTQ系）。

素朴な量子化は「重みを丸める」が、本当に守りたいのは出力 y=Wx。
ある列を丸めた誤差を、まだ丸めていない列に押しつけて打ち消せば、
同じビット数でも出力誤差だけを大きく下げられる。ここが1bit未満を
実用に近づける唯一の現実的なテコ。
"""
import numpy as np
import wcodec as C


def hessian(X, damp=0.01):
    """X: (in, nsample) の較正用活性化。H = X X^T（+ 対角ダンピング）"""
    H = (X @ X.T).astype(np.float64) / X.shape[1]
    d = np.mean(np.diag(H)) * damp
    H[np.diag_indices_from(H)] += d
    dead = np.diag(H) == 0
    H[dead, dead] = 1.0
    return H


def _hinv_chol(H):
    """GPTQ の定石: inv(H) のコレスキー上三角。"""
    Hi = np.linalg.inv(H)
    Hi = (Hi + Hi.T) / 2
    L = np.linalg.cholesky(Hi)      # 下三角 L, Hi = L L^T
    return np.linalg.cholesky(np.linalg.inv(H)).T if False else L.T


def gptq_scalar(W, X, bits=2, G=128, ternary=False):
    """列を1本ずつ丸め、誤差を右側の未処理列へ流す（本家GPTQ相当）。"""
    W = W.astype(np.float64).copy()
    n = W.shape[1]
    U = _hinv_chol(hessian(X))
    # グループごとのスケールは元の重みから先に決めておく
    W0 = W.copy()
    for start in range(0, n, G):
        end = min(start + G, n)
        blk = W0[:, start:end]
        s = np.abs(blk).max(1, keepdims=True)
        s[s == 0] = 1
        if ternary:
            s = np.abs(blk).mean(1, keepdims=True); s[s == 0] = 1
            qmax = 1
        else:
            qmax = 2 ** (bits - 1) - 1
        for j in range(start, end):
            w = W[:, j:j + 1]
            q = np.clip(np.rint(w / s * qmax), -qmax, qmax) / qmax * s
            W0[:, j:j + 1] = q          # 記録用
            err = (w - q) / U[j, j]
            if j + 1 < n:
                W[:, j + 1:] -= err @ U[j:j + 1, j + 1:]
            W[:, j:j + 1] = q
    bpw = (np.log2(3) if ternary else bits) + 16 / G
    name = "三値" if ternary else f"{bits}bit"
    return W.astype(np.float32), bpw, f"GPTQ-{name}(G={G})"


def gptq_pvq(W, X, k=8, cb_bits=4, G=128, seed=0, iters=8):
    """k列ずつまとめてベクトル量子化し、ブロック外へ誤差を流す。
    ブロック内の逐次補正は省略（近似）。
    """
    W = W.astype(np.float64).copy()
    out, n = W.shape
    assert n % k == 0 and G % k == 0
    U = _hinv_chol(hessian(X))

    # コードブックは元の重みから一度だけ学習
    Xg = C._grouped(W.astype(np.float32), G)
    s_all = C._scales(Xg)
    Cb = C._kmeans((Xg / s_all).reshape(-1, k).astype(np.float32),
                   2 ** cb_bits, iters=iters, seed=seed)

    for start in range(0, n, G):
        end = min(start + G, n)
        s = np.abs(W[:, start:end]).max(1, keepdims=True)
        s[s == 0] = 1
        for j in range(start, end, k):
            blk = W[:, j:j + k] / s                       # (out,k)
            idx = C._assign(blk.astype(np.float32), Cb)
            q = Cb[idx] * s                               # (out,k)
            E = W[:, j:j + k] - q
            W[:, j:j + k] = q
            if j + k < n:
                # ブロックの各列の誤差を、右側の未処理列へ流す
                for t in range(k):
                    col = j + t
                    err = E[:, t:t + 1] / U[col, col]
                    W[:, j + k:] -= err @ U[col:col + 1, j + k:]
    bpw = cb_bits / k + 16 / G
    return W.astype(np.float32), bpw, f"GPTQ-PVQ k={k},{cb_bits}bit(G={G})"
