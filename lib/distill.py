"""層ごとの蒸留（目盛りの繰り返し調整）。

考え方:
  元の賢いAIの層出力 Y = W X を「先生の答え」とし、
  圧縮した層の出力を Y に近づける。本体のつまみ（コード番号）は動かさず、
  **目盛り（グループごとのスケール）だけ**を調整する。
  目盛りは重み256個につき1個なので調整対象が桁違いに少なく、CPUでも回る。
  層ごとに独立して解けるので、AI全体を動かす必要もない。

なぜ繰り返すのか:
  グループ同士は直交していない（互いの寄与が干渉する）。1つ直すと他がずれるので、
  順番に何度も直して収束させる。これが世界の手法(block reconstruction)の軽量版。
"""
import numpy as np


def tune_scales(W, Wh, X, G=256, rounds=8, tol=1e-4, lo=0.5, hi=2.0):
    """コードを固定したまま、グループごとの倍率だけを出力誤差最小に調整する。

    W  : 元の重み (out, in)      → 先生の答え Y = W X を作るのに使う
    Wh : 圧縮した重み (out, in)  → これを調整する
    X  : その層の本物の入力 (in, sample)
    戻り値: (調整後の重み, 各周の出力誤差の履歴)
    """
    Wh = Wh.astype(np.float64).copy()
    Y = W.astype(np.float64) @ X
    ny = np.linalg.norm(Y)
    inn = W.shape[1]
    ng = inn // G
    hist = []
    R = Y - Wh @ X                       # まだ合っていない分
    for it in range(rounds):
        for g in range(ng):
            sl = slice(g * G, (g + 1) * G)
            P = Wh[:, sl] @ X[sl]        # このグループの出力への寄与
            d = float((P * P).sum())
            if d <= 0:
                continue
            a = 1.0 + float((R * P).sum() / d)     # 誤差を最も減らす倍率
            a = min(max(a, lo), hi)                # 暴れ止め
            if a != 1.0:
                Wh[:, sl] *= a
                R -= (a - 1.0) * P                 # 残りを更新（再計算せず差分で）
        e = float(np.linalg.norm(R) / ny)
        hist.append(round(e, 5))
        if it >= 1 and hist[-2] - e < tol:
            break
    return Wh.astype(np.float32), hist


def bits_overhead(inn, G, scale_bits=16):
    """調整した目盛りを保存する分のビット。もともと持っている量なので増分はゼロ。"""
    return scale_bits / G
