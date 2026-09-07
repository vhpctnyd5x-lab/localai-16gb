"""e8.py の検算: テータ級数・最近点復号・重み付き復号を総当たりと突き合わせる。"""
import os, sys, time, itertools
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib"))
import e8

t0 = time.time()
# ---- 総当たりで E8 の点を列挙（ノルム² ≤ 12）----
R2 = 12
ints = np.array(list(itertools.product(range(-3, 4), repeat=8)), np.float32)   # 7^8
ints = ints[np.mod(ints.sum(1), 2) == 0]
halfs = np.array(list(itertools.product([-2.5, -1.5, -0.5, 0.5, 1.5, 2.5], repeat=8)), np.float32)
halfs = halfs[np.mod((halfs - 0.5).sum(1), 2) == 0]          # D8 + ½ の条件
P = np.concatenate([ints, halfs], 0)
n2 = (P * P).sum(1)
P = P[n2 <= R2 + 1e-6]; n2 = n2[n2 <= R2 + 1e-6]
print(f"列挙 {len(P)} 点 ({time.time()-t0:.1f}秒)")

# ---- テータ級数の検算 ----
ok = True
for s in (0, 2, 4, 6, 8, 10, 12):
    c = int((np.abs(n2 - s) < 1e-6).sum())
    exp = e8._SHELL[s]
    flag = "OK" if c == exp else "NG"
    ok &= c == exp
    print(f"  殻 norm²={s:2d}: 総当たり {c:6d}  表 {exp:6d}  {flag}")
assert ok, "テータ級数が合わない"
print(f"  count(10)={e8.count(10)}  bits(10)={e8.bits(10):.4f}   count(12)={e8.count(12)}  bits(12)={e8.bits(12):.4f}")

# ---- 最近点復号（ユークリッド）を総当たりと突き合わせ ----
rng = np.random.default_rng(0)
Y = rng.normal(size=(4000, 8)).astype(np.float32) * 0.6      # ‖y‖ はだいたい 1.7 以下
Y = Y[np.sqrt((Y * Y).sum(1)) < 1.5]                          # 最近点は必ず norm² ≤ 12 の中
C = e8.nearest(Y)
d_ours = ((Y - C) ** 2).sum(1)
# 総当たり: 各 y に対し全 P との距離の最小
d_bf = np.empty(len(Y))
for i in range(0, len(Y), 200):
    y = Y[i:i+200]
    d = (y * y).sum(1)[:, None] - 2 * y @ P.T + n2[None, :]
    d_bf[i:i+200] = d.min(1)
gap = np.abs(d_ours - d_bf).max()
print(f"最近点復号: {len(Y)}点  最大の距離差 {gap:.2e}  {'OK' if gap < 1e-4 else 'NG'}")
assert gap < 1e-4

# ---- 重み付き復号を総当たりと突き合わせ ----
w = rng.uniform(0.05, 3.0, size=8).astype(np.float32)
Cw = e8.nearest(Y, w)
dw_ours = ((Y - Cw) ** 2 * w).sum(1)
dw_bf = np.empty(len(Y))
Pw = P * w
for i in range(0, len(Y), 200):
    y = Y[i:i+200]
    d = (y * y * w).sum(1)[:, None] - 2 * y @ Pw.T + (P * Pw).sum(1)[None, :]
    dw_bf[i:i+200] = d.min(1)
gapw = np.abs(dw_ours - dw_bf).max()
print(f"重み付き復号: 最大の距離差 {gapw:.2e}  {'OK' if gapw < 1e-4 else 'NG'}   (w={np.round(w,2)})")
assert gapw < 1e-4

# ---- 球で切る量子化: 球外の入力も必ず球内に落ちること ----
Yb = rng.normal(size=(20000, 8)).astype(np.float32) * 2.0     # 半分以上が球外
Cb = e8.quantize(Yb, None, 10.0)
n = (Cb * Cb).sum(1)
print(f"球切り: 入力の球外率 {(np.sqrt((Yb*Yb).sum(1)) > np.sqrt(10)).mean()*100:.1f}%  "
      f"出力の最大 norm² {n.max():.1f}  (≤10 なら OK)  格子点か: {np.allclose(e8.nearest(Cb), Cb)}")
assert n.max() <= 10 + 1e-6

# ---- 球外候補の質: 「縮めて復号」が、球内の総当たり最近点にどれだけ近いか ----
Pb = P[n2 <= 10 + 1e-6]; n2b = n2[n2 <= 10 + 1e-6]
Yo = Yb[np.sqrt((Yb * Yb).sum(1)) > np.sqrt(10)][:2000]
Co = e8.quantize(Yo, None, 10.0)
d_ours = ((Yo - Co) ** 2).sum(1)
d_bf = np.empty(len(Yo))
for i in range(0, len(Yo), 200):
    y = Yo[i:i+200]
    d = (y * y).sum(1)[:, None] - 2 * y @ Pb.T + n2b[None, :]
    d_bf[i:i+200] = d.min(1)
print(f"球外入力の量子化: 総当たり最適比で歪みが +{(d_ours.sum()/d_bf.sum()-1)*100:.2f}%  "
      f"（一致率 {(np.abs(d_ours-d_bf)<1e-4).mean()*100:.1f}%）")

# ---- 一様雑音に対する形状利得の確認（Z^8 比 +0.65 dB になるはず）----
U = rng.uniform(-8, 8, size=(200000, 8)).astype(np.float32)
Ce = e8.nearest(U); Cz = np.rint(U)
G_e8 = ((U - Ce) ** 2).sum(1).mean() / 8      # E8 の基本領域の体積は 1 → そのまま比較可
G_z = ((U - Cz) ** 2).sum(1).mean() / 8
print(f"形状利得: MSE(E8)={G_e8:.4f}  MSE(Z^8)={G_z:.4f}  利得 {10*np.log10(G_z/G_e8):.2f} dB (理論 0.65)")
print(f"全部OK ({time.time()-t0:.1f}秒)")
