"""ブロック単位の再構成（BRECQ の中核）。

【いま何が足りていないか】
現状の quantize2/quantize3 は、各層でこう解いている:

    min ‖(W − Ŵ) X_生徒‖        … 自分の出力を、自分の入力で合わせる

X_生徒 は「前の層まで量子化済みで流れてきた活性化」なので、そこは正しい。
だが **目標が W X_生徒 になっている**。つまり
「前の層でずれた入力を、そのまま正しいものとして受け入れて」しまっている。
層を重ねるほど、ずれが素通しで積み上がる。

【BRECQ の言い分】
目標は自分の出力ではなく、**先生（元モデル）の出力**であるべき:

    min ‖Ŵ X_生徒 − W X_先生‖   … 先生の出力に、生徒の入力で追いつく

こうすると、前の層でついたずれを、次の層が**打ち消しにいく**。
これが「2段構え」の2段目で、OneComp の③、我々だけが持っていなかった工程。

【CPU で解く】
量子化の制約を一旦外すと、これはただの最小二乗:

    W* = (Y_先生 X_生徒ᵀ)(X_生徒 X_生徒ᵀ + λI)⁻¹

W* は「生徒の入力のもとで、先生の出力を出すための理想の重み」。
これを **W の代わりに量子化する**。層ごとに閉じているので GPU は要らない。
"""
import numpy as np


def target_weight(W, Xs, Xt, damp=0.1, maxd=0.30, mindrift=0.15):
    """先生の出力に追いつくための「理想の重み」を解く。

    W  : 元の重み (out, in)
    Xs : 生徒の入力 (in, sample)  … 前の層まで量子化済みで流れてきたもの
    Xt : 先生の入力 (in, sample)  … 元モデルをそのまま流したもの
    返り: W* (out, in)

    Xs と Xt が同じなら W* == W に戻る（ずれが無ければ何もしないのが正しい）。
    """
    # ずれが小さい層は、そもそも直す対象が無い。
    # ここで手を出すと最小二乗の解が元の重みから無意味に離れ、
    # そのうえに量子化誤差が乗って、かえって悪化する（実験26で実測）。
    if drift(Xs, Xt) < mindrift:
        return W.astype(np.float32)

    Xs = np.ascontiguousarray(Xs.astype(np.float64))
    Xt = np.ascontiguousarray(Xt.astype(np.float64))
    n = Xs.shape[1]
    A = (Xs @ Xs.T) / n
    A[np.diag_indices_from(A)] += damp * np.mean(np.diag(A)) + 1e-8
    B = (W.astype(np.float64) @ Xt) @ Xs.T / n        # (out,in)
    try:
        Wt = np.linalg.solve(A.T, B.T).T
    except np.linalg.LinAlgError:
        return W.astype(np.float32)                   # 解けなければ元のまま
    # 暴走の歯止め。先生の出力に合わせるためとはいえ、
    # 元の重みから離れすぎたものは、別の区間で必ず破綻する。
    # 歯止め。実験26では上限1.0が甘すぎた:
    # W* が元から0.9離れ、その上に量子化誤差0.6が乗って合計1.32、
    # 「ゼロを入れるより元から遠い」重みが浅い層に並んで崩壊した。
    # 量子化誤差ぶんの余地を残すため、上限を大きく下げる。
    d = np.linalg.norm(Wt - W) / (np.linalg.norm(W) + 1e-12)
    if not np.isfinite(d):
        return W.astype(np.float32)
    if d > maxd:
        # 全部捨てるのは惜しいので、上限まで引き戻して使う。
        Wt = W + (Wt - W) * (maxd / d)
    return Wt.astype(np.float32)


def drift(Xs, Xt):
    """生徒の入力が先生からどれだけずれているか（0なら一致）"""
    a = np.linalg.norm(Xs - Xt)
    b = np.linalg.norm(Xt) + 1e-12
    return float(a / b)
