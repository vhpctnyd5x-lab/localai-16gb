"""E8格子によるベクトル量子化（8次元・語彙の保存が不要）。

なぜ E8 か:
  8次元で最も密な球充填。一様雑音に対する形状利得は立方格子 Z^8 比 +0.65 dB
  （正規化二次モーメント G(E8)=0.0717 対 G(Z)=0.0833）。
  語彙（コードブック）を保存しなくてよく、最近点の探索が O(k) で済む。
  k-means の語彙は学習データ（重み自身）に過適合するが、格子は構造で勝負する。

構成:
  E8 = D8 ∪ (D8 + ½·1)        D8 = {整数点のうち座標和が偶数}
  最近点復号 (Conway & Sloane, Ch.20):
    D8: 各座標を丸め、和が奇数なら「丸め誤差が最大の座標」を逆側へ1動かす
    E8: 2つのコセットで復号し、近い方を採る

AdaRound（出力誤差で丸め先を選ぶ）を厳密に組み込める:
  距離を Σ_j w_j (y_j − c_j)² にしたとき、D8 の最近点は「座標ごとの丸め」か
  「そこから1座標だけ ±1 動かした点」のどちらかであることは変わらない。
  奇数和の直しで動かす座標を argmax|d_j| から argmin w_j(1−2|d_j|) に替えるだけ。
  w は (8,)（全行共通）でも (n,8)（行ごと）でもよい。

固定レートにするため、ノルム² ≤ R2 の格子点だけを語彙にする（球で切る）:
  R2=10 → 56881 点 (15.80 bit / 8重み = 1.975 bit/重み)
  R2=12 → 117361 点 (16.84 bit / 8重み = 2.105 bit/重み)
球の外に落ちた入力は、原点方向へ縮めて復号し直し、さらに隣接格子点（240本）を
見て局所改善する。総当たりの最近点と一致することを test_e8_ball.py で確認済み。
"""
import numpy as np

# E8 のテータ級数: ノルム² → その殻にある格子点の数（検算済み: test_e8.py）
_SHELL = {0: 1, 2: 240, 4: 2160, 6: 6720, 8: 17520, 10: 30240,
          12: 60480, 14: 82560, 16: 140400}


def count(R2):
    """ノルム² ≤ R2 の格子点の数（=語彙の大きさ）"""
    return sum(c for n, c in _SHELL.items() if n <= R2 + 1e-9)


def bits(R2):
    """1重みあたりのビット数（8次元ぶんの語彙を 8 で割る）"""
    return float(np.log2(count(R2)) / 8.0)


def _bw(w, Y):
    """w を (n,8) に揃える（None はそのまま）"""
    if w is None:
        return None
    w = np.asarray(w, np.float32)
    return np.broadcast_to(w, Y.shape) if w.ndim == 1 else w


def _wdist(Y, C, W):
    E = Y - C
    if W is None:
        return (E * E).sum(1)
    return (E * E * W).sum(1)


def _d8(Y, W=None):
    """D8 の最近点。Y:(n,8)  W:(n,8) または None（重み付き距離）"""
    F = np.rint(Y)
    D = Y - F                                    # 丸め誤差 ∈ [-0.5, 0.5]
    odd = np.mod(F.sum(1), 2.0) != 0
    if odd.any():
        idx = np.nonzero(odd)[0]
        Do = D[idx]
        # 座標 j を「丸めと逆側」へ1動かす追加コストは w_j (1 − 2|d_j|)
        cost = 1.0 - 2.0 * np.abs(Do)
        if W is not None:
            cost = cost * W[idx]
        j = cost.argmin(1)
        r = np.arange(len(idx))
        step = np.where(Do[r, j] >= 0, 1.0, -1.0)
        F[idx, j] += step
    return F


def nearest(Y, w=None):
    """E8 の最近点（重み付き距離にも対応）。Y:(n,8)"""
    W = _bw(w, Y)
    C0 = _d8(Y, W)
    C1 = _d8(Y - 0.5, W) + 0.5
    pick = _wdist(Y, C1, W) < _wdist(Y, C0, W)
    return np.where(pick[:, None], C1, C0)


def _min_vectors():
    """E8 の最短ベクトル 240 本（隣接格子点への移動）。
    112本: (±1, ±1, 0^6) の並べ替え   128本: (±½)^8 で負号が偶数個"""
    import itertools
    out = []
    for i in range(8):
        for j in range(i + 1, 8):
            for si in (1.0, -1.0):
                for sj in (1.0, -1.0):
                    v = np.zeros(8, np.float32); v[i] = si; v[j] = sj
                    out.append(v)
    for signs in itertools.product((0.5, -0.5), repeat=8):
        if sum(1 for s in signs if s < 0) % 2 == 0:
            out.append(np.array(signs, np.float32))
    return np.array(out, np.float32)


_MIN = _min_vectors()
# 縮め方の刻み。粗い5刻み＋局所改善2周では遠い入力で総当たりに 20% 負けた。
# 11刻み＋3周なら全ての検証入力で総当たりと一致（test_e8_ball.py）。
_SHRINK = (0.97, 0.94, 0.90, 0.85, 0.80, 0.72, 0.62, 0.50, 0.35, 0.20, 0.0)


def _improve_in_ball(Yo, C, W, R2, rounds=3, chunk=2048):
    """球内の候補 C を、隣接格子点（240本）を見て局所的に改善する。
    「原点方向へ縮めて復号」は光線上しか探さないので、球の殻の上で横にずれた
    最近点を取りこぼす。隣を見に行けば総当たりに並ぶ（test_e8_ball.py）。"""
    C = C.copy()
    for _ in range(rounds):
        moved = False
        for i in range(0, len(Yo), chunk):
            y = Yo[i:i + chunk]; c = C[i:i + chunk]
            cand = c[:, None, :] + _MIN[None, :, :]                  # (m,240,8)
            ok = (cand * cand).sum(2) <= R2 + 1e-9
            E = cand - y[:, None, :]
            if W is None:
                d = (E * E).sum(2)
            else:
                d = (E * E * W[i:i + chunk][:, None, :]).sum(2)
            d[~ok] = np.inf
            j = d.argmin(1)
            dj = d[np.arange(len(y)), j]
            d0 = _wdist(y, c, None if W is None else W[i:i + chunk])
            imp = dj < d0 - 1e-9
            if imp.any():
                moved = True
                c[imp] = cand[np.nonzero(imp)[0], j[imp]]
        if not moved:
            break
    return C


def quantize(Y, w=None, R2=10.0, rounds=3):
    """ノルム² ≤ R2 の E8 格子点へ量子化する。Y:(n,8)  w:(8,)/(n,8)/None"""
    Y = np.asarray(Y, np.float32)
    W = _bw(w, Y)
    C = nearest(Y, W)
    out = (C * C).sum(1) > R2 + 1e-9
    if out.any():
        idx = np.nonzero(out)[0]
        Yo = Y[idx]
        Wo = None if W is None else np.ascontiguousarray(W[idx])
        best = np.zeros_like(Yo)
        bestd = np.full(len(idx), np.inf)
        for t in _SHRINK:
            Ct = nearest(Yo * t, Wo)
            ok = (Ct * Ct).sum(1) <= R2 + 1e-9
            d = _wdist(Yo, Ct, Wo)
            d[~ok] = np.inf
            imp = d < bestd
            best[imp] = Ct[imp]
            bestd[imp] = d[imp]
        C[idx] = _improve_in_ball(Yo, best, Wo, R2, rounds=rounds)
    return C


def quantize_c(Y, w=None, R2=10.0, compand=1.0, rounds=3):
    """圧伸つきの量子化。y → sign(y)|y|^p を格子に載せ、復元後 1/p 乗で戻す。
    p<1 で原点付近が細かく、裾が粗くなる（裾の重い分布向け）。p=1 なら quantize と同じ。"""
    if compand == 1.0:
        return quantize(Y, w, R2, rounds)
    Y = np.asarray(Y, np.float32)
    Yc = np.sign(Y) * np.abs(Y) ** compand
    C = quantize(Yc, w, R2, rounds)
    return (np.sign(C) * np.abs(C) ** (1.0 / compand)).astype(np.float32)


def fit_scale(Y, R2=10.0, grid=None, sample=24000, seed=0, compand=1.0):
    """格子の目盛り α を探す: min_α Σ‖y − α·Q(y/α)‖²（標本で近似・粗→細の2段）。
    Y:(n,8) は正規化済みの部分ベクトル。圧伸があれば圧伸した空間で目盛りを当てる。"""
    rng = np.random.default_rng(seed)
    Y = np.asarray(Y, np.float32)
    if len(Y) > sample:
        Y = Y[rng.choice(len(Y), sample, replace=False)]
    Yc = Y if compand == 1.0 else np.sign(Y) * np.abs(Y) ** compand
    rms = float(np.sqrt((Yc * Yc).sum(1).mean())) + 1e-12
    base = rms / np.sqrt(R2)

    def err(a):
        C = quantize_c(Y / a, None, R2, compand, rounds=1) * a
        return float(((Y - C) ** 2).sum())

    if grid is None:
        grid = base * np.exp(np.linspace(np.log(0.25), np.log(1.6), 9))
    errs = [err(a) for a in grid]
    i = int(np.argmin(errs)); a0 = float(grid[i])
    # 細: 最良点の両隣の間を 5 点で刻む
    lo = float(grid[max(i - 1, 0)]); hi = float(grid[min(i + 1, len(grid) - 1)])
    fine = np.exp(np.linspace(np.log(lo), np.log(hi), 7))[1:-1]
    for a in fine:
        e = err(a)
        if e < errs[i]:
            errs[i], a0 = e, float(a)
    return a0
