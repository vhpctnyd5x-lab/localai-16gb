"""統合レシピ。実測で有効性を確認した手札を全部組み合わせる。

構成:
  1. 出力を意識した低ランク分解（白色化した空間でSVD＝出力誤差最小の最適解）
  2. 因子の内側にアダマール回転（積は不変・コスト0・外れ値をならす）
  3. 残差をベクトル量子化し、**誤差補償(GPTQ)で右側の列へ誤差を流す**
  4. スケールを出力誤差最小で解き直す

3が今回の主役。本物の活性化で+5.6〜39.9%が確認できた最大の武器。
GPTQの逐次ループは重いので、128列ずつまとめて更新する（BLASに載せる）。

残差の語彙は2種類から選べる:
  lattice=None : k-means で学習した語彙（k 次元・2^cb_bits 語）
  lattice="e8" : E8 格子（8次元・ノルム² ≤ R2 の格子点。語彙の保存が不要）
"""
import os
import numpy as np
import wcodec as C
import rotate
import e8 as E8


def hessian(X, damp=0.1):
    H = (X @ X.T).astype(np.float64) / X.shape[1]
    H[np.diag_indices_from(H)] += damp * np.mean(np.diag(H))
    return H


def chol_inv(H):
    Hi = np.linalg.inv(H)
    return np.linalg.cholesky((Hi + Hi.T) / 2).T          # 上三角U, Hi = U^T U


def whiten(H):
    """R Rᵀ = H を満たす R を返す。
    以前は固有値分解で対称平方根を作っていたが、lowrank が必要とするのは
    「RRᵀ=H を満たす何か」だけで、対称性は使っていない。
    コレスキーなら約3倍速く、入力次元11008の層では効きが大きい。"""
    try:
        return np.linalg.cholesky(H)
    except np.linalg.LinAlgError:
        w, V = np.linalg.eigh(H)
        return (V * np.sqrt(np.clip(w, 1e-12, None))) @ V.T


def inner_rotate(A, B, seed=0):
    r = A.shape[1]
    d = rotate.signs(r, seed); s = 1 / np.sqrt(r)
    return rotate.fwht(A) * d * s, (rotate.fwht(B.T).T) * d[:, None] * s


def lowrank(W, R, r):
    """min‖(W−AB)R‖ の閉じた解。Rは共分散の平方根。"""
    U, S, Vt = np.linalg.svd(W @ R, full_matrices=False)
    A = U[:, :r] * S[:r]
    B = np.linalg.solve(R.T, Vt[:r].T).T
    return A, B


def assign_w(sub, Cb, w):
    """出力誤差でいちばん近いコードを選ぶ（ふつうのユークリッド距離ではなく）。

    AdaRound の中核。「いちばん近い値に丸める」は最適ではない、という指摘。
    どの列がどれだけ効くかは活性化で決まるので、その重み w を入れて測る:

        距離(c) = Σ_j w_j (x_j − Cb[c,j])²

    第1項 Σ w_j x_j² は c によらないので落とせる。残りは行列積2本で済む。
    我々自身の実測（出力誤差と重み誤差の順位相関 −0.111）とも符合する:
    重み空間で近くても、出力空間で近いとは限らない。
    """
    a = -2.0 * ((sub * w) @ Cb.T)
    b = ((Cb ** 2) * w).sum(1)[None, :]
    return np.argmin(a + b, axis=1)


# 行ごとの目盛り探索の刻み。8刻み(0.6〜1.5)は 4刻みより +0.1% しか良くならず 2倍遅い。
LATTICE_SCALE_GRID = (0.75, 0.87, 1.0, 1.15)


def vq_gptq(D, U, k, cb_bits, G, blk=128, seed=0, hdiag=None,
            lattice=None, R2=10.0, scale_grid=LATTICE_SCALE_GRID,
            lat_norm="max", compand=1.0):
    """残差Dをベクトル量子化しつつ、誤差を未処理の列へ流す。
    Uは inv(H) の上三角コレスキー。128列ごとにまとめて更新してBLASに載せる。
    返り値: (量子化した残差, 語彙ぶんの bit/重み)

    格子のときの追加オプション:
      lat_norm : ブロックの目盛りの決め方。"max"=絶対値最大（k-meansと同じ） / "rms"=二乗平均平方根。
                 外れ値の多い層では max が1個の外れ値に引きずられ、残りが格子の目盛りより
                 小さくなって全部ゼロに潰れる。rms ならそれが起きにくい。
      compand  : 圧伸の指数 p。y → sign(y)|y|^p を格子で量子化し、復元後に 1/p 乗で戻す。
                 p<1 で原点付近の目盛りが細かくなり、裾の重い分布に格子を合わせられる。"""
    out, n = D.shape
    Dq = D.astype(np.float64).copy()
    Xg = D.reshape(-1, G)

    def _bscale(seg):
        if lattice is not None and lat_norm == "rms":
            s = np.sqrt((seg * seg).mean(1, keepdims=True))
        else:
            s = np.abs(seg).max(1, keepdims=True)
        s[s == 0] = 1
        return s

    s0 = _bscale(Xg)
    if lattice == "e8":
        assert k == 8, "E8 格子は k=8 のみ"
        # 語彙は学習しない。格子の目盛り α（層に1個の実数）だけを探す。
        alpha = E8.fit_scale((Xg / s0).reshape(-1, 8).astype(np.float32), R2,
                             seed=seed, compand=compand)
        vbits = E8.bits(R2)
    else:
        # コードブックは元の残差から一度だけ学習（語数は 2^cb_bits。非整数ビットも可）
        ncode = int(round(2 ** cb_bits))
        Cb = C._kmeans((Xg / s0).reshape(-1, k).astype(np.float32), ncode, seed=seed)
        vbits = float(np.log2(ncode) / k)

    # GPTQ本来の形: ブロック内は k 列ずつ逐次に丸め、誤差をその場で右隣へ流す。
    # 従来は128列を一括で丸め、ブロック外へまとめて流すだけだった。
    # つまり **128列の内側では誤差が誰にも渡っていなかった**。
    # 補償はGPTQ最大の効き所なので、ここを取りこぼすのは大きい。
    #
    # スケールはブロック単位で1個しか保存できない（16/128ビット）。
    # そこで2回通す: 1回目で最適な行スケールを求め、2回目でそれを使って
    # 逐次伝播しながら丸める。k列ごとにスケールを持つと2ビット/重みかかって破綻する。
    dU = np.diag(U)
    for bs in range(0, n, blk):
        be = min(bs + blk, n)
        width = (be - bs) // k * k
        if width == 0:
            continue
        be = bs + width
        s0 = _bscale(Dq[:, bs:be])

        def _assign_group(c0, c1, sc):
            sub = (Dq[:, c0:c1] / sc).astype(np.float32)
            w = None
            if hdiag is not None:
                w = hdiag[c0:c1].astype(np.float32)
                if w.shape[0] < k or not np.any(w > 0):
                    w = np.ones(k, dtype=np.float32)
            if lattice == "e8":
                # 11刻み＋局所改善2周で総当たりと一致（test_e8_ball.py）
                return E8.quantize_c(sub / alpha, w, R2, compand, rounds=2) * alpha
            if w is None:
                return Cb[C._assign(sub, Cb)]
            return Cb[assign_w(sub, Cb, w)]

        # 1回目: 伝播せずに割り当てて、行ごとの最適スケールを求める
        def _pass1(sc):
            if lattice == "e8":
                # 格子は語彙との行列積が要らないので、ブロック全体を一度に復号できる
                # （呼び出し回数を 1/16 にする。列ごとの重みは行ごとに並べ替えて渡す）
                seg = (Dq[:, bs:be] / sc).astype(np.float32).reshape(-1, k)
                w = None
                if hdiag is not None:
                    wb = hdiag[bs:be].astype(np.float32)
                    wb = np.where(wb > 0, wb, 0.0)
                    if not np.any(wb > 0):
                        wb = np.ones(width, np.float32)
                    w = np.broadcast_to(wb.reshape(1, width // k, k),
                                        (out, width // k, k)).reshape(-1, k)
                # 目盛り選びの段階なので球外の局所改善は1周で足りる（最終の丸めは2回目で行う）
                q = E8.quantize_c(seg / alpha, w, R2, compand, rounds=1) * alpha
                return q.reshape(out, width).astype(np.float64) * sc
            q = np.empty((out, width))
            for g in range(width // k):
                c0 = bs + g * k
                q[:, g * k:(g + 1) * k] = _assign_group(c0, c0 + k, sc) * sc
            return q
        seg0 = Dq[:, bs:be]
        if lattice is not None and scale_grid:
            # 格子は語彙が固定なので、目盛りの当たり外れがそのまま歪みになる。
            # 絶対値最大で決めた s0 は最大値1個に引きずられるので、
            # 行ごとに t·s0 を掃いて（重み付き）誤差が最小の目盛りを選ぶ。
            wb = np.ones(width) if hdiag is None else hdiag[bs:be].astype(np.float64)
            best = np.full(out, np.inf); q0 = None; sbest = s0.copy()
            for t in scale_grid:
                sc = s0 * t
                q = _pass1(sc)
                err = ((seg0 - q) ** 2 * wb).sum(1)
                imp = err < best
                if q0 is None:
                    q0, best = q, err
                else:
                    q0[imp] = q[imp]; best[imp] = err[imp]
                sbest[imp] = sc[imp]
            s0 = sbest
        else:
            q0 = _pass1(s0)
        num = (seg0 * q0).sum(1, keepdims=True)
        den = (q0 * q0).sum(1, keepdims=True); den[den == 0] = 1
        s = s0 * (num / den)

        # 2回目: そのスケールで、k列ずつ逐次に丸めて誤差を右へ流す
        Err = np.zeros((out, width))
        for g in range(width // k):
            c0 = bs + g * k; c1 = c0 + k
            q = _assign_group(c0, c1, s) * s
            e = Dq[:, c0:c1] - q
            Dq[:, c0:c1] = q
            ec = e / dU[c0:c1]
            Err[:, c0 - bs:c1 - bs] = ec
            if c1 < be:
                Dq[:, c1:be] -= ec @ U[c0:c1, c1:be]   # ブロック内の残りへ即座に
        if be < n:
            Dq[:, be:] -= Err @ U[bs:be, be:]          # ブロック外へまとめて
    return Dq.astype(np.float32), vbits


def fit(W, X, rank=32, lr_bits=4, k=8, cb_bits=8, G=256,
        damp=float(os.environ.get("DAMP", 0.1)), seed=0,
        adaround=False, lattice=None, R2=10.0, scale_grid=LATTICE_SCALE_GRID,
        lat_norm="max", compand=1.0):
    """W:(out,in), X:(in,sample)。
    lattice="e8" なら残差を E8 格子（k=8, ノルム² ≤ R2）で量子化する。
    scale_grid は格子のときの行ごとの目盛り探索（None/空で無効）。
    lat_norm / compand は vq_gptq を参照。"""
    out, inn = W.shape
    H = hessian(X, damp)
    R = whiten(H)
    U = chol_inv(H)
    r = 1 << (min(rank, min(out, inn) // 2).bit_length() - 1)

    A, B = lowrank(W, R, r)
    A, B = inner_rotate(A, B, seed)
    Aq = C.rtn(A, lr_bits, min(G, A.shape[1]))[0]
    Bq = C.rtn(B, lr_bits, min(G, B.shape[1]))[0]
    LR = Aq @ Bq

    hd = np.diag(H).astype(np.float32) if adaround else None
    Res, vbits = vq_gptq(W - LR, U, k, cb_bits, G, seed=seed, hdiag=hd,
                         lattice=lattice, R2=R2, scale_grid=scale_grid,
                         lat_norm=lat_norm, compand=compand)
    lr_bpw = r * (out + inn) * lr_bits / (out * inn)
    ovh = 16 * (Aq.size / min(G, Aq.shape[1]) + Bq.size / min(G, Bq.shape[1])) / (out * inn)
    # 実際に走るグループ幅は vq_gptq の blk と G の小さい方。
    # ここを G のままにしていたため、ビット数を 0.06 ぶん少なく申告していた。
    greal = min(128, G)
    return (LR + Res).astype(np.float32), lr_bpw + vbits + 16.0 / greal + ovh
