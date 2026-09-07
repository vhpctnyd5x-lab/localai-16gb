"""実験26-C（事前確認）: BRECQ が本当にずれを減らすか、6時間を投じる前に確かめる。

【なぜ要るか】
BRECQ の +52〜82% は **単層・人工的なガウス雑音** で測った値。
実際のずれは構造を持つので、同じ効果が出る保証はない。
全層で6時間回してから「効きませんでした」では遅い。

【やり方】
最初の6ブロックだけ量子化して流し、**ブロック5の出口のずれ**を測る。
BRECQ を切った場合と入れた場合で、同じことを2回やって比べるだけ。
他の条件は完全に同じにする（乱数の種も同じ）。

【判定】
ずれが下がれば第1段へ。下がらなければ中止して SpQR 方式へ切り替える。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import forward, recipe as RP, brecq

MODEL = ("/path/to/localai/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
NTOK = int(os.environ.get("NTOK", "128"))
NBLK = int(os.environ.get("NBLK", "6"))          # 最初の何ブロックを量子化するか
HERE = os.path.dirname(os.path.abspath(__file__))


def say(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


toks = json.load(open(os.path.join(ROOT, "data/calib/tokens_big.json")))[:NTOK]
m = forward.Model(MODEL, in_memory=True)

# 量子化する層（最初の NBLK ブロック）
targets = {n for n in m.r.tensors
           if n.startswith(tuple(f"blk.{b}." for b in range(NBLK)))
           and n.endswith(".weight") and ("attn" in n or "ffn" in n)
           and len(m.r.tensors[n][0]) == 2}
# ずれを見る場所 = ブロック NBLK の入口（＝ブロック NBLK-1 の出口）
PROBE = f"blk.{NBLK}.attn_q.weight"
say(f"量子化する層 {len(targets)}（blk.0〜{NBLK-1}） / 見る場所 {PROBE} / {NTOK}トークン")

# ---- 先生 ----
t0 = time.time()
_, sensei = forward.run(m, toks, capture=targets | {PROBE})
say(f"先生の活性化を採取 ({time.time()-t0:.0f}秒)")
Xt_probe = sensei[PROBE]


def hashiru(use_brecq):
    """最初のNBLKブロックを量子化して流し、PROBE でのずれを返す。

    注意: forward.run は quantizer を渡すと **capture を返さない**（quantized を返す）。
    なので PROBE も量子化器の対象に入れておき、
    そこへ来た活性化を横取りして記録し、重みは素通しで返す。
    """
    tsukatta = {}
    mita = {}

    def q(name, W, h):
        if name == PROBE:
            mita["x"] = np.ascontiguousarray(h.astype(np.float32)).copy()
            return W.astype(np.float32)          # 素通し。ここは量子化しない
        Xs = np.ascontiguousarray(h.T.astype(np.float32))
        Wsrc, zure = W, None
        if use_brecq and name in sensei:
            Xt = np.ascontiguousarray(sensei[name].T.astype(np.float32))
            n = min(Xs.shape[1], Xt.shape[1])
            if n >= 32:
                zure = brecq.drift(Xs[:, :n], Xt[:, :n])
                Wsrc = brecq.target_weight(W, Xs[:, :n], Xt[:, :n])
        inn = W.shape[1]
        try:
            if Xs.shape[1] >= inn:
                Wh, _ = RP.fit(Wsrc, Xs, k=8, cb_bits=8, adaround=True, seed=0)
            else:
                imp = np.sqrt((Xs ** 2).mean(1))
                imp /= np.exp(np.log(imp + 1e-30).mean())
                s = imp ** 0.75
                Wh, _ = RP.fit(Wsrc * s[None, :], np.eye(inn, dtype=np.float32),
                               k=8, cb_bits=8, adaround=True, seed=0)
                Wh = Wh / s[None, :]
        except Exception as e:
            say(f"  !! {name} 失敗({type(e).__name__}) → 元のまま")
            Wh = W.astype(np.float32)
        tsukatta[name] = zure
        return Wh.astype(np.float32)

    t = time.time()
    forward.run(m, toks, quantizer=(targets | {PROBE}, q))
    if "x" not in mita:
        raise SystemExit(f"{PROBE} に活性化が来なかった。層名を確認すること")
    d = brecq.drift(mita["x"].T, Xt_probe.T)
    say(f"  {'BRECQ入' if use_brecq else 'BRECQ切'}: "
        f"{PROBE} でのずれ = {d:.4f}  ({time.time()-t:.0f}秒)")
    return d, tsukatta


say("--- ① BRECQ を切って走らせる（いまの実装と同じ）---")
d_off, _ = hashiru(False)
say("--- ② BRECQ を入れて走らせる ---")
d_on, z = hashiru(True)

print("\n" + "=" * 52)
print(f"  BRECQ 切 : ずれ {d_off:.4f}")
print(f"  BRECQ 入 : ずれ {d_on:.4f}")
kai = 100 * (d_off - d_on) / d_off if d_off else 0
print(f"  改善     : {kai:+.1f}%")
print("=" * 52)
zz = [v for v in z.values() if v is not None]
if zz:
    print(f"  途中の各層で見えたずれ: 平均{np.mean(zz):.3f} 最大{max(zz):.3f} "
          f"（{len(zz)}層でBRECQ適用）")
print()
if d_on < 1.0 and kai > 10:
    print("  → 判定: **合格**。第1段（全層で5〜6時間）へ進んでよい")
elif kai > 10:
    print(f"  → 判定: 改善はしたが、ずれは1.0未満に届かず（{d_on:.3f}）。")
    print("     全層で回す価値はあるが、これ単独で崩壊は止まらない見込み")
else:
    print("  → 判定: **不合格**。BRECQは実際のずれには効かない。")
    print("     6時間を投じる前に SpQR 方式へ切り替えるべき")
json.dump({"off": d_off, "on": d_on, "改善率": kai, "NBLK": NBLK, "NTOK": NTOK},
          open(os.path.join(HERE, "preflight.json"), "w"), ensure_ascii=False, indent=1)
