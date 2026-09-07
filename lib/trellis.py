"""トレリス符号化量子化（QTIP方式の中核）。

k-means辞書の限界: k個をまとめると候補が 2^(k×bit) で爆発し、k=32が壁。
トレリスは重みを1個ずつ符号化しつつ「直近Lビットの履歴」を状態として持ち、
系列全体の誤差が最小になる経路をViterbiで厳密に探す。
再生値は状態番号から計算で生成するので**コードブックを保存しない**。

高速化の鍵（ビットシフトトレリスの構造）:
  遷移は next = ((state << K) | code) & (2^L - 1)。
  K=1 のとき、ある次状態 j の前状態は必ず 2つだけ:  j>>1  と  (j>>1) + 2^(L-1)。
  この「バタフライ構造」のおかげで、全状態・全行を一度に配列演算で処理できる。
"""
import numpy as np


def gen_values(L, seed=0):
    """状態ごとの再生値。保存不要＝シードだけで再現できる。"""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(1 << L)
    return ((v - v.mean()) / v.std()).astype(np.float32)


def quantize_rows(X, L=10, seed=0):
    """X: (N, T) の各行をトレリス符号化（K=1bit/要素）。全行を同時に処理する。"""
    N, T = X.shape
    S = 1 << L
    H = S >> 1
    vals = gen_values(L, seed)                      # (S,)
    j = np.arange(S)
    p0 = (j >> 1)                                   # 前状態その1
    p1 = p0 + H                                     # 前状態その2

    cost = np.zeros((N, S), np.float32)
    back = np.empty((T, N, S), np.bool_)            # Trueなら前状態はp1側
    for t in range(T):
        c0 = cost[:, p0]
        c1 = cost[:, p1]
        take1 = c1 < c0
        back[t] = take1
        base = np.where(take1, c1, c0)
        d = vals[None, :] - X[:, t:t + 1]
        cost = base + d * d

    # 後ろ向き復元
    s = np.argmin(cost, axis=1).astype(np.int64)    # (N,)
    out = np.empty((N, T), np.float32)
    rows = np.arange(N)
    for t in range(T - 1, -1, -1):
        out[:, t] = vals[s]
        take1 = back[t, rows, s]
        s = (s >> 1) + np.where(take1, H, 0)
    return out


def quantize_matrix(W, G=256, L=10, seed=0, ls_scale=True):
    """行列全体。グループ(=行の一区間)ごとにスケール、中身を1bitトレリスで符号化。
    実効ビット = 1 + スケールのビット/G。"""
    X = W.reshape(-1, G)
    s = np.abs(X).max(1, keepdims=True)
    s[s == 0] = 1
    R = quantize_rows((X / s).astype(np.float32), L=L, seed=seed)
    if ls_scale:
        num = (X * R).sum(1, keepdims=True)
        den = (R * R).sum(1, keepdims=True)
        den[den == 0] = 1
        s = num / den
    return (R * s).reshape(W.shape).astype(np.float32), 1.0 + 8.0 / G
