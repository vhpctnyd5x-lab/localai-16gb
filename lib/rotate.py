"""アダマール回転（インコヒーレンス処理）。

重み行列は少数の巨大な値と大量の小さい値で出来ていて、これが量子化に最悪。
直交行列で回転すると値が均されて「全部そこそこの大きさ」になり、
同じビット数でも表現しやすくなる。

肝は **回転行列を保存しなくていい** こと。アダマール行列は構造で決まり、
符号反転はシード1個で再現できるので、オーバーヘッドは実質ゼロ。
推論時は入力 x 側も同じ回転をかける（O(n log n)で安い）。
"""
import numpy as np


def fwht(a):
    """高速ウォルシュ・アダマール変換（最終軸に対して、正規化なし）。"""
    a = a.copy()
    n = a.shape[-1]
    assert n & (n - 1) == 0, "長さは2のべき乗が必要"
    h = 1
    while h < n:
        a = a.reshape(*a.shape[:-1], n // (2 * h), 2, h)
        x = a[..., 0, :].copy()
        y = a[..., 1, :].copy()
        a[..., 0, :] = x + y
        a[..., 1, :] = x - y
        a = a.reshape(*a.shape[:-3], n)
        h *= 2
    return a


def signs(n, seed):
    rng = np.random.default_rng(seed)
    return rng.choice(np.array([-1.0, 1.0], np.float32), size=n)


def rotate_rows(A, d, inverse=False):
    """A の最終軸に Q = H·diag(d)/√n を掛ける。inverse=True で Qᵀ。"""
    n = A.shape[-1]
    s = 1.0 / np.sqrt(n)
    if not inverse:
        return fwht(A * d) * s          # A Q^T 相当（Hは対称）
    return fwht(A) * d * s


def make(n, seed=0):
    """(重み用の回転関数, 活性化用の回転関数) を返す。両者は必ず打ち消し合う。"""
    d = signs(n, seed)

    def rot_W(W):                      # W' = W Q
        return rotate_rows(W, d, inverse=False)

    def rot_x(X):                      # x' = Qᵀ x   (X は (n, sample))
        return rotate_rows(X.T, d, inverse=False).T

    return rot_W, rot_x, d
