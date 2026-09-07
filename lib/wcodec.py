"""1ビット未満まで含む重み圧縮コーデック群。

共通の約束:
  encode(W, ...) -> (W_hat, bpw, label)
    W_hat : 復元された重み (float32, Wと同形)
    bpw   : 1重みあたりの実効ビット数（スケール等のオーバーヘッド込み）
    label : 表示用の名前

前提: W は (out, in) の行優先。量子化グループは「同じ行の連続 G 要素」。
"""
import numpy as np

FP16_BITS = 16


# ---------- 補助 ----------
def _grouped(W, G):
    """(out,in) -> (ngroup, G) に切る。in が G で割り切れる前提。"""
    out, inn = W.shape
    assert inn % G == 0, f"in={inn} が group={G} で割り切れない"
    return W.reshape(-1, G)


def _scales(X):
    s = np.abs(X).max(axis=1, keepdims=True)
    s[s == 0] = 1.0
    return s


# ---------- 1. RTN（普通の整数量子化。比較の基準線）----------
def rtn(W, bits=4, G=128):
    X = _grouped(W, G)
    s = _scales(X)
    qmax = 2 ** (bits - 1) - 1
    q = np.clip(np.rint(X / s * qmax), -qmax, qmax)
    Xh = q / qmax * s
    bpw = bits + FP16_BITS / G
    return Xh.reshape(W.shape).astype(np.float32), bpw, f"RTN-{bits}bit(G={G})"


# ---------- 2. 三値（BitNet風。約1.58bit）----------
def ternary(W, G=128):
    X = _grouped(W, G)
    s = np.abs(X).mean(axis=1, keepdims=True)
    s[s == 0] = 1.0
    q = np.clip(np.rint(X / s), -1, 1)
    Xh = q * s
    bpw = np.log2(3) + FP16_BITS / G
    return Xh.reshape(W.shape).astype(np.float32), bpw, f"三値(G={G})"


# ---------- 3. 学習コードブックの積量子化（1bit未満の本命）----------
def _kmeans(data, ncode, iters=8, seed=0, sample=120_000):
    rng = np.random.default_rng(seed)
    if len(data) > sample:
        data = data[rng.choice(len(data), sample, replace=False)]
    C = data[rng.choice(len(data), ncode, replace=False)].copy()
    for _ in range(iters):
        idx = _assign(data, C)
        dead = []
        for c in range(ncode):
            m = idx == c
            if m.any():
                C[c] = data[m].mean(0)
            else:
                dead.append(c)
        if dead:
            # 誰にも選ばれなかったコードは初期値のまま居座り、語彙を無駄にする。
            # 最も表現できていない点（現コードから最も遠い点）へ置き直して回収する。
            d2 = ((data - C[idx]) ** 2).sum(1)
            far = np.argsort(-d2)[:len(dead)]
            C[np.array(dead)] = data[far]
    return C


def _assign(X, C, chunk=65536):
    """最近傍コード番号。||x-c||^2 = ||x||^2 -2x·c + ||c||^2 の展開で高速化。"""
    cn = (C * C).sum(1)
    out = np.empty(len(X), np.int32)
    for i in range(0, len(X), chunk):
        x = X[i:i + chunk]
        d = cn[None, :] - 2.0 * (x @ C.T)
        out[i:i + chunk] = d.argmin(1)
    return out


def pvq(W, k=8, cb_bits=8, G=128, seed=0, random_codebook=False):
    """k次元ごとに 2^cb_bits 個のコードへ割り当てる積ベクトル量子化。
    bpw = cb_bits/k + スケール分。k=8, cb_bits=4 なら 0.5bit/重み。
    random_codebook=True なら学習せず乱数で作る（コードブックの保存が不要＝seed だけ）。
    """
    assert G % k == 0
    X = _grouped(W, G)
    s = _scales(X)
    Xn = (X / s).reshape(-1, k)          # 正規化済みサブベクトル
    ncode = 2 ** cb_bits
    if random_codebook:
        rng = np.random.default_rng(seed)
        C = rng.normal(0, Xn.std(), size=(ncode, k)).astype(np.float32)
        tag = "乱数CB"
    else:
        C = _kmeans(Xn.astype(np.float32), ncode, seed=seed)
        tag = "学習CB"
    idx = _assign(Xn.astype(np.float32), C)
    Xh = (C[idx].reshape(X.shape) * s)
    bpw = cb_bits / k + FP16_BITS / G
    return Xh.reshape(W.shape).astype(np.float32), bpw, f"PVQ-{tag} k={k},{cb_bits}bit(G={G})"


# ---------- 4. 重要度ハイブリッド（少数の列だけ厚く、残りを極薄に）----------
def hybrid(W, keep_frac=0.01, keep_bits=8, sub=None, G=128, importance=None):
    """入力次元(列)の重要度上位 keep_frac だけ高精度、残りを sub コーデックで潰す。
    importance: 長さ in の配列（キャリブレーションから来る活性化スケール等）。
                None なら列ノルムで代用。
    """
    if sub is None:
        sub = lambda M: pvq(M, k=8, cb_bits=4, G=G)
    out, inn = W.shape
    imp = importance if importance is not None else np.linalg.norm(W, axis=0)
    nkeep = max(1, int(round(inn * keep_frac)))
    keep = np.argsort(-imp)[:nkeep]
    mask = np.zeros(inn, bool)
    mask[keep] = True

    Wh = np.empty_like(W, dtype=np.float32)
    # 高精度側（列数が G で割り切れないので行ごとに1グループ扱い）
    Wk = W[:, mask]
    s = _scales(Wk)
    qmax = 2 ** (keep_bits - 1) - 1
    Wh[:, mask] = np.clip(np.rint(Wk / s * qmax), -qmax, qmax) / qmax * s

    Wr = np.ascontiguousarray(W[:, ~mask])
    rest_in = Wr.shape[1]
    pad = (-rest_in) % G
    if pad:
        Wr = np.pad(Wr, ((0, 0), (0, pad)))
    Wrh, sub_bpw, sub_label = sub(Wr)
    Wh[:, ~mask] = Wrh[:, :rest_in]

    f = nkeep / inn
    bpw = f * (keep_bits + FP16_BITS / min(G, nkeep)) + (1 - f) * sub_bpw + 1.0 / out
    return Wh, bpw, f"ハイブリッド {keep_frac*100:.1f}%@{keep_bits}bit + {sub_label}"


# ---------- 評価 ----------
def evaluate(W, Wh, X=None, seed=0):
    """重み誤差と、実際に効く「出力誤差」を測る。"""
    E = W - Wh
    rel_w = np.linalg.norm(E) / np.linalg.norm(W)
    if X is None:
        rng = np.random.default_rng(seed)
        n = W.shape[1]
        # 正規分布＋外れ値チャンネル（実際の活性化は少数の次元が突出する）
        X = rng.normal(size=(n, 64)).astype(np.float32)
        big = rng.choice(n, max(1, n // 100), replace=False)
        X[big] *= 20.0
    Y, Yh = W @ X, Wh @ X
    rel_y = np.linalg.norm(Y - Yh) / np.linalg.norm(Y)
    return rel_w, rel_y
