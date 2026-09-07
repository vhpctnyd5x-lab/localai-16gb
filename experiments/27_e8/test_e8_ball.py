"""球外入力の量子化の質: 総当たり（球内の全格子点）との差を測る"""
import os, sys, time, itertools
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib"))
import importlib, e8
R2 = 10
ints = np.array(list(itertools.product(range(-3, 4), repeat=8)), np.float32)
ints = ints[np.mod(ints.sum(1), 2) == 0]
halfs = np.array(list(itertools.product([-2.5, -1.5, -0.5, 0.5, 1.5, 2.5], repeat=8)), np.float32)
halfs = halfs[np.mod((halfs - 0.5).sum(1), 2) == 0]
P = np.concatenate([ints, halfs], 0); n2 = (P * P).sum(1)
P = P[n2 <= R2 + 1e-6]; n2 = n2[n2 <= R2 + 1e-6]
rng = np.random.default_rng(1)
for scale in (1.3, 2.0, 3.0):
    Y = rng.normal(size=(30000, 8)).astype(np.float32) * scale
    Y = Y[np.sqrt((Y * Y).sum(1)) > np.sqrt(R2)][:3000]
    t = time.time(); C = e8.quantize(Y, None, float(R2)); dt = time.time() - t
    d_ours = ((Y - C) ** 2).sum(1)
    d_bf = np.empty(len(Y))
    for i in range(0, len(Y), 200):
        y = Y[i:i+200]
        d_bf[i:i+200] = ((y * y).sum(1)[:, None] - 2 * y @ P.T + n2[None, :]).min(1)
    print(f"scale={scale}: 球外{len(Y)}点  歪み +{(d_ours.sum()/d_bf.sum()-1)*100:.2f}%  "
          f"一致率 {(np.abs(d_ours-d_bf)<1e-4).mean()*100:.1f}%  {dt*1000:.0f}ms")
# 重み付きでも球内に落ちて、かつ総当たりに近いか
w = rng.uniform(0.05, 3.0, size=8).astype(np.float32)
Y = rng.normal(size=(30000, 8)).astype(np.float32) * 2.0
Y = Y[np.sqrt((Y * Y).sum(1)) > np.sqrt(R2)][:3000]
C = e8.quantize(Y, w, float(R2))
assert (C * C).sum(1).max() <= R2 + 1e-6
d_ours = ((Y - C) ** 2 * w).sum(1)
Pw = P * w; d_bf = np.empty(len(Y))
for i in range(0, len(Y), 200):
    y = Y[i:i+200]
    d_bf[i:i+200] = ((y * y * w).sum(1)[:, None] - 2 * y @ Pw.T + (P * Pw).sum(1)[None, :]).min(1)
print(f"重み付き 球外: 歪み +{(d_ours.sum()/d_bf.sum()-1)*100:.2f}%  一致率 {(np.abs(d_ours-d_bf)<1e-4).mean()*100:.1f}%")
