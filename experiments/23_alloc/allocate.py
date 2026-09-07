"""実験23-B: レート歪み配分。層ごとに違うビット数を配る。

いまは252層すべてに一律の設定を配っている。だが層によって痛み（出力誤差）は
何倍も違う。同じ平均ビット数のまま、痛い層に厚く・楽な層に薄く配り直せば
全体の誤差は下がる。これが引き継ぎ書6-1。

やり方（レート歪み理論の教科書どおり）:
  各層iと候補設定cについて (ビット数 b_ic, 二乗誤差 D_ic) を用意し、
      Σ D_ic を最小化   subject to  Σ b_ic·size_i ≤ 予算
  ラグランジュ緩和すると各層独立に  argmin_c  D_ic + λ·b_ic·size_i  を選ぶだけ。
  λ を二分探索して予算にぴったり合わせる。凸包上では厳密解。

歪みのモデル:
  実測点は2つ（unified=約1.15bit と b07=約0.70bit）。高レート近似
      D(b) = D0 · 2^(−2λ(b−b0))
  の λ を層ごとに2点から推定する。2点が無い層は同じ種類(kind)の中央値を使う。

出力: results/recipe.json  … 層名 → {k, cb, G, rank} の割り当て表
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "results")
import numpy as np

# λ が負で捨てた層の数（0 のままなら 全層が使えている）
SUTETA = [0]

# --- 候補設定。bpwは recipe.fit と同じ式で閉形式に出せる（フィット不要） ---
CANDS = [(k, cb, G, rank) for k in (32, 16, 8, 4, 2)
         for cb in (8, 12) for G in (256,) for rank in (32,)]


def bpw_of(out, inn, k, cb, G, rank, lr_bits=4):
    """lib/recipe.fit の戻り値と同じ計算。"""
    r = 1 << (min(rank, min(out, inn) // 2).bit_length() - 1)
    lr = r * (out + inn) * lr_bits / (out * inn)
    Asz, Aw = r * out, min(G, r)          # A:(out,r)
    Bsz, Bw = r * inn, min(G, inn)        # B:(r,inn)
    ovh = 16 * (Asz / Aw + Bsz / Bw) / (out * inn)
    return lr + cb / k + 16.0 / G + ovh


def load(name):
    p = os.path.join(R, name + "_sens.json")
    return json.load(open(p)) if os.path.exists(p) else {}


hi = load("unified")          # 約1.154 bit
lo = load("b07")              # 約0.70 bit（37層のみ）
if not hi:
    sys.exit("先に sensitivity.py を走らせること（unified）")

HI = dict(k=8, cb=8, G=256, rank=32)
LO = dict(k=16, cb=8, G=256, rank=32)

# --- λ（1ビットあたり何倍誤差が減るか）を推定 ---
lam, bykind = {}, {}
for n, d in hi.items():
    if n not in lo:
        continue
    b1 = bpw_of(d["out"], d["inn"], **HI)
    b0 = bpw_of(d["out"], d["inn"], **LO)
    e1, e0 = d["err"], lo[n]["err"]
    if b1 <= b0 or e1 <= 0 or e0 <= 0:
        continue
    l = math.log2(e0 / e1) / (b1 - b0)      # 誤差(振幅)の指数。D=err^2 なので指数は2λ
    # ★ 2026-09-07 注記: ビットを下げても誤差が増えない層では l <= 0 になる。
    #   その層はここで黙って捨てられ、既定値へ落ちていた。捨てた数を数えて出す。
    if l <= 0:
        SUTETA[0] += 1
    if 0.01 < l < 4:
        lam[n] = l
        bykind.setdefault(d["kind"], []).append(l)

med = {k: float(np.median(v)) for k, v in bykind.items()}
gmed = float(np.median(list(lam.values()))) if lam else 0.5
print(f"λの実測: {len(lam)}層  全体中央値={gmed:.3f}")
for k in sorted(med, key=lambda x: -med[x]):
    print(f"  {k:<14} λ={med[k]:.3f}  (n={len(bykind[k])})")
if not lam:
    print("※ 2点そろった層が無いので λ=0.5 を全層に仮定する（要 b07 の感度測定）")

# --- 各層の候補表をつくる ---
rows = []
for n, d in hi.items():
    l = lam.get(n, med.get(d["kind"], gmed))
    b1 = bpw_of(d["out"], d["inn"], **HI)
    scale = (d["err"] ** 2) * d["size"]      # 絶対的な二乗誤差の大きさ（サイズ加重）
    cs = []
    for (k, cb, G, rank) in CANDS:
        b = bpw_of(d["out"], d["inn"], k, cb, G, rank)
        D = scale * (2.0 ** (-2 * l * (b - b1)))
        cs.append((b, D, (k, cb, G, rank)))
    # 凸包に載らない候補（ビットも誤差も他に負ける）は捨てる
    cs.sort()
    keep, best = [], float("inf")
    for b, D, c in cs:
        if D < best - 1e-30:
            keep.append((b, D, c)); best = D
    rows.append((n, d, keep))

TOT = sum(d["size"] for _, d, _ in rows)
BASE = sum(bpw_of(d["out"], d["inn"], **HI) * d["size"] for _, d, _ in rows) / TOT
BUDGET = float(os.environ.get("BUDGET", BASE))
print(f"\n一律配分の平均 = {BASE:.4f} bit/重み → これを予算にして配分し直す")


def solve(lmb):
    pick, bits, dist = {}, 0.0, 0.0
    for n, d, keep in rows:
        b, D, c = min(keep, key=lambda x: x[1] + lmb * x[0] * d["size"])
        pick[n] = c; bits += b * d["size"]; dist += D
    return pick, bits / TOT, dist


lo_l, hi_l = 1e-18, 1e6
for _ in range(200):
    mid = math.sqrt(lo_l * hi_l)
    _, b, _ = solve(mid)
    if b > BUDGET:
        lo_l = mid
    else:
        hi_l = mid
pick, bpw, dist = solve(hi_l)
_, _, dist0 = solve(float("inf"))          # 使わない。基準は下で別に出す

base_dist = sum((d["err"] ** 2) * d["size"] for _, d, _ in rows)
print(f"配分後: {bpw:.4f} bit/重み  推定二乗誤差 {dist:.4e}  "
      f"(一律 {base_dist:.4e} → {100*(1-dist/base_dist):.1f}% 減)")
print(f"推定の出力誤差RMS: {math.sqrt(base_dist/TOT):.4f} → {math.sqrt(dist/TOT):.4f}")

out = {n: dict(zip(("k", "cb", "G", "rank"), c)) for n, c in pick.items()}
json.dump(out, open(os.path.join(R, "recipe.json"), "w"), indent=1)
print(f"\n保存: {os.path.join(R,'recipe.json')}")

print("\n--- 配分の分布 ---")
cnt = {}
for n, c in pick.items():
    cnt[c] = cnt.get(c, 0) + 1
for c, v in sorted(cnt.items(), key=lambda x: -x[1]):
    print(f"  k={c[0]:>2} cb={c[1]:>2}  {v:>3}層")

print("\n--- 深さ方向にどう配られたか（ブロックごとの平均bit）---")
byb = {}
for n, d, _ in rows:
    b = bpw_of(d["out"], d["inn"], *pick[n])
    byb.setdefault(d["blk"], []).append((b, d["size"]))
for b in sorted(byb):
    xs = byb[b]
    v = sum(x * s for x, s in xs) / sum(s for _, s in xs)
    print(f"  blk.{b:>2} {v:.3f}bit " + "#" * int(v * 20))
