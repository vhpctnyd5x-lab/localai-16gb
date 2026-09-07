"""実験23-A: 層ごとの「痛み」を測る。再量子化なし・順伝播なし。

引き継ぎ書6-1「層ごとのビット配分」の第一歩。
252層すべてに一律1.15bitを配っているが、層によって誤差は2倍以上違うはず。
まずそれを実測する。

材料は既にある:
  - data/ckpt/unified/*.npy  ... 1.154bitで量子化済みの252層
  - data/calib/real_imatrix.npz ... 本物の活性化の2乗平均（対角）
  - 元のGGUF ................... 元の重み

測るもの（出力空間の相対誤差。重み空間の誤差ではない）:
    err = ‖(W−Ŵ)·diag(√imat)‖_F / ‖W·diag(√imat)‖_F

RESULTS.mdの最大の教訓「重み誤差はモデル品質を保証しない」を踏まえ、
活性化で重みづけした**出力側**の誤差で見る。これが層の痛みの指標。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import forward

MODEL = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
CKPT = os.path.join(ROOT, "data", "ckpt", os.environ.get("NAME", "unified"))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "results", os.environ.get("NAME", "unified") + "_sens.json")


def say(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


imat = np.load(os.path.join(ROOT, "data/calib/real_imatrix.npz"))
m = forward.Model(MODEL)
done = json.load(open(OUT)) if os.path.exists(OUT) else {}

names = sorted(f[:-4] for f in os.listdir(CKPT) if f.endswith(".npy"))
say(f"{len(names)}層を評価する（済み{len(done)}層）")

for i, n in enumerate(names):
    if n in done:
        continue
    if n not in imat:
        say(f"  skip {n}: imatrixに無い")
        continue
    W = m.T(n).astype(np.float32)
    Wh = np.load(os.path.join(CKPT, n + ".npy")).astype(np.float32)
    if W.shape != Wh.shape:
        say(f"  skip {n}: 形が違う {W.shape} vs {Wh.shape}")
        continue
    s = np.sqrt(np.maximum(imat[n].astype(np.float32), 0.0))
    if s.shape[0] != W.shape[1]:
        say(f"  skip {n}: imatrixの長さが違う {s.shape[0]} vs {W.shape[1]}")
        continue
    D = (W - Wh) * s[None, :]
    B = W * s[None, :]
    num = float(np.sqrt((D.astype(np.float64) ** 2).sum()))
    den = float(np.sqrt((B.astype(np.float64) ** 2).sum())) or 1.0
    # 重み空間の誤差も並べて記録する（比較用。これが当てにならないことの証拠になる）
    wnum = float(np.sqrt(((W - Wh).astype(np.float64) ** 2).sum()))
    wden = float(np.sqrt((W.astype(np.float64) ** 2).sum())) or 1.0
    blk = int(n.split(".")[1])
    kind = n.split(".")[2]
    done[n] = dict(blk=blk, kind=kind, size=int(W.size),
                   out=int(W.shape[0]), inn=int(W.shape[1]),
                   err=num / den, werr=wnum / wden)
    m.drop(n)
    del W, Wh, D, B
    if (i + 1) % 20 == 0:
        json.dump(done, open(OUT, "w"), ensure_ascii=False, indent=1)
        say(f"  {i+1}/{len(names)}")

json.dump(done, open(OUT, "w"), ensure_ascii=False, indent=1)
say(f"保存: {OUT}")

# --- 要約 ---
v = sorted(done.values(), key=lambda d: -d["err"])
tot = sum(d["size"] for d in v)
glob = float(np.sqrt(sum((d["err"] ** 2) * d["size"] for d in v) / tot))
print(f"\n全体の出力誤差（サイズ加重RMS） = {glob:.4f}")
print(f"最悪 {v[0]['err']:.4f} / 最良 {v[-1]['err']:.4f} = {v[0]['err']/max(v[-1]['err'],1e-12):.1f}倍の開き\n")

print("--- 種類ごとの平均 ---")
kinds = {}
for d in v:
    kinds.setdefault(d["kind"], []).append(d["err"])
for k, xs in sorted(kinds.items(), key=lambda x: -np.mean(x[1])):
    print(f"  {k:<14} 出力誤差 平均{np.mean(xs):.4f}  最悪{max(xs):.4f}  最良{min(xs):.4f}")

print("\n--- 痛い層 上位15 ---")
for d in v[:15]:
    print(f"  blk.{d['blk']:>2}.{d['kind']:<14} 出力{d['err']:.4f}  重み{d['werr']:.4f}")

print("\n--- 深さ方向（ブロックごとの平均出力誤差）---")
byb = {}
for d in v:
    byb.setdefault(d["blk"], []).append(d["err"])
for b in sorted(byb):
    e = float(np.mean(byb[b]))
    print(f"  blk.{b:>2} {e:.4f} " + "#" * int(e * 120))

# 出力誤差と重み誤差の順位が一致するか（一致しないなら重み誤差で判断してはいけない）
a = np.array([d["err"] for d in v]); b = np.array([d["werr"] for d in v])
ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
print(f"\n出力誤差 vs 重み誤差 の順位相関 = {np.corrcoef(ra, rb)[0,1]:.3f}")
