"""実験19: 統合レシピをモデル全体に適用する（逐次方式）。

順伝播を1回流しながら、各層に到達した時点でその層の本物の入力を使って量子化する。
量子化済みの重みで先に進むので、誤差の伝播も現実的に扱える（実際のGPTQ実装と同じ）。
全層ぶんの活性化を同時に持たずに済むのが利点（同時保持だと100GB近く必要）。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, ggufwrite, forward, recipe as RP, wcodec as C

MODEL = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
OUT = sys.argv[1]
NTOK = int(os.environ.get("NTOK", "1024"))
RANK = int(os.environ.get("RANK", "32"))
K = int(os.environ.get("K", "8"))
CB = int(os.environ.get("CB", "8"))
GRP = int(os.environ.get("GRP", "256"))

toks = json.load(open(os.path.join(ROOT, "data/calib/tokens_big.json")))[:NTOK]
m = forward.Model(MODEL, in_memory=True)   # 外部SSDへの反復アクセスを避ける
targets = {n for n, (d, t, o) in m.r.tensors.items()
           if len(d) == 2 and n.startswith("blk.") and n.endswith(".weight")
           and ("attn" in n or "ffn" in n)}
print(f"対象{len(targets)}層 / 較正{len(toks)}トークン / ランク{RANK} k={K} コード{2**CB} G={GRP}")

CKPT = os.path.join(ROOT, "data/models", os.path.basename(OUT) + ".ckpt.npz")
done = dict(np.load(CKPT)) if os.path.exists(CKPT) else {}
if done:
    print(f"途中経過を発見: {len(done)}層は済み。続きから再開する。")
log = {"tot_w": 0, "tot_bits": 0, "n": len(done), "t0": time.time()}


def quantize(name, W, h):
    if name in done:
        return done[name]
    X = np.ascontiguousarray(h.T.astype(np.float32))      # (in, sample)
    inn = W.shape[1]
    try:
        if X.shape[1] >= inn:                              # 標本が足りるなら完全なヘッセ行列
            Wh, bpw = RP.fit(W, X, rank=RANK, k=K, cb_bits=CB, G=GRP)
        else:
            # 標本不足なら対角のみ（重要度スケーリング相当）に落とす。
            # 足りないまま完全なヘッセ行列を使うと壊れる（序盤の失敗の教訓）。
            imp = np.sqrt((X ** 2).mean(1)); imp /= np.exp(np.log(imp + 1e-30).mean())
            s = imp ** 0.75
            Wh, bpw = RP.fit(W * s[None, :],
                             np.eye(inn, dtype=np.float32) * 1.0,
                             rank=RANK, k=K, cb_bits=CB, G=GRP)
            Wh = Wh / s[None, :]
    except Exception as e:
        print(f"    !! {name} で失敗({e}) → 元の重みのまま", flush=True)
        return W.astype(np.float32)
    log["tot_w"] += W.size; log["tot_bits"] += bpw * W.size; log["n"] += 1
    done[name] = Wh.astype(np.float32)
    if log["n"] % 10 == 0:
        np.savez(CKPT, **done)          # 落ちても続きからやり直せる
    if log["n"] % 20 == 0 or log["n"] == 1:
        print(f"  [{log['n']:3d}/{len(targets)}] {name:<30} {bpw:.3f}bit "
              f"経過{time.time()-log['t0']:.0f}秒", flush=True)
    return Wh.astype(np.float32)


_, qw = forward.run(m, toks, quantizer=(targets, quantize))
np.savez(CKPT, **done)
avg = log["tot_bits"] / max(1, log["tot_w"])
print(f"\n平均 {avg:.4f} bit/重み  ({log['tot_w']/1e9:.2f}B パラメータ)")
ggufwrite.Copier(MODEL).write(OUT, qw)
print(f"書き出し: {OUT}  {os.path.getsize(OUT)/1e9:.2f}GB")
json.dump(dict(平均bpw=round(float(avg), 4), 層数=log["n"],
               設定=dict(rank=RANK, k=K, cb=CB, G=GRP, ntok=NTOK)),
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "results", os.path.basename(OUT) + ".json"), "w"),
          ensure_ascii=False, indent=2)
