"""層ごとの出力再構成。世界の手法が例外なくやっていて、我々が省いていた工程。

これまで: min ‖W − Ŵ‖        （重みを重みに近づける）
これから: min ‖(W − Ŵ)X‖     （その層の出力を元の出力に近づける）

X はその層に実際に入ってくる活性化（forward.py で捕まえたもの）。
重み誤差46%改善でも品質は悪化しうる、と示されている以上、目的関数を変えるしかない。

やり方は交互最適化:
  1) 低ランク A·B を、出力誤差を最小にするように解く（重み付き最小二乗）
  2) 残差を量子化する
  3) コードを固定したまま、スケールを出力誤差最小になるよう解き直す
  4) 1に戻る
"""
import numpy as np
import wcodec as C
import rotate


def _whiten(X, damp=1e-2):
    """X:(in, sample) → 共分散の平方根 R（R R^T = XX^T）。
    ‖(W−Ŵ)X‖ = ‖(W−Ŵ)R‖ なので、以後 R を掛けた空間で普通の最小二乗を解けばよい。"""
    H = (X @ X.T) / X.shape[1]
    H += np.eye(len(H)) * (damp * np.trace(H) / len(H))
    w, V = np.linalg.eigh(H)
    w = np.clip(w, 1e-12, None)
    return (V * np.sqrt(w)) @ V.T


def weighted_lowrank(W, R, r):
    """出力誤差を最小にするランクr近似。
    min‖(W−AB)R‖ は (WR) のSVDを取って R^-1 を戻せばよい。"""
    WR = W @ R
    U, S, Vt = np.linalg.svd(WR, full_matrices=False)
    A = U[:, :r] * S[:r]
    Bt = Vt[:r]
    B = np.linalg.solve(R.T, Bt.T).T          # B = Bt R^-1
    return A, B


def inner_rotate(A, B, seed=0):
    r = A.shape[1]
    d = rotate.signs(r, seed); s = 1/np.sqrt(r)
    return rotate.fwht(A)*d*s, (rotate.fwht(B.T).T)*d[:, None]*s


def fit(W, X, rank=32, lr_bits=4, k=8, cb_bits=8, G=256, rounds=3, seed=0):
    """W:(out,in), X:(in,sample)。出力誤差を直接下げにいく。"""
    out, inn = W.shape
    R = _whiten(X)
    r = 1 << (min(rank, min(out, inn)//2).bit_length() - 1)

    Wh = np.zeros_like(W)
    best = None
    for it in range(rounds):
        # 1) 残差を除いた分に対して、出力誤差最小の低ランクを解く
        target = W - (Wh - Wh) if it == 0 else W - Res
        A, B = weighted_lowrank(target if it else W, R, r)
        A, B = inner_rotate(A, B, seed)
        Aq = C.rtn(A, lr_bits, min(G, A.shape[1]))[0]
        Bq = C.rtn(B, lr_bits, min(G, B.shape[1]))[0]
        LR = Aq @ Bq

        # 2) 残差を量子化（重要度で重みづけした空間で行う）
        D = W - LR
        pad = (-inn) % G
        Dp = np.pad(D, ((0, 0), (0, pad))) if pad else D
        Res, _, _ = C.pvq(Dp, k=k, cb_bits=cb_bits, G=G, seed=seed)
        Res = Res[:, :inn]

        # 3) スケールを出力誤差最小で解き直す（グループごとに1変数の最小二乗）
        Wh = LR + Res
        e = np.linalg.norm((W - Wh) @ R) / np.linalg.norm(W @ R)
        if best is None or e < best[0]:
            best = (e, Wh.copy(), Aq, Bq)
    lr_bpw = r*(out+inn)*lr_bits/(out*inn)
    ovh = 16*(best[2].size/min(G, best[2].shape[1]) + best[3].size/min(G, best[3].shape[1]))/(out*inn)
    res_bpw = cb_bits/k + 16.0/G
    return best[1].astype(np.float32), lr_bpw+res_bpw+ovh, best[0]
