"""実験22: 目盛りの繰り返し調整（層ごとの蒸留）の効果。

統合レシピで量子化したあと、目盛りだけを先生の出力に合わせ込む。
採点は必ず別区間のデータで行う。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, recipe as RP, distill

MODEL = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
acts = np.load(os.path.join(ROOT, "data/calib/acts_big.npz"))
r_ = gguf.Reader(MODEL)
rows = []
for name in ["blk.10.attn_q.weight", "blk.20.attn_output.weight"]:
    W, _ = r_.load(name); W = np.ascontiguousarray(W.astype(np.float32))
    Xtr = acts[f"tr|{name}"].T.astype(np.float32)
    Xte = acts[f"te|{name}"].T.astype(np.float32)
    sc = lambda Wh: float(np.linalg.norm((W-Wh)@Xte)/np.linalg.norm(W@Xte))
    print(f"\n=== {name} {W.shape} ===")
    for k, cb, G in [(8, 8, 256), (16, 8, 256)]:
        t0 = time.time()
        Wh, bpw = RP.fit(W, Xtr, rank=32, k=k, cb_bits=cb, G=G)
        e0 = sc(Wh)
        Wt, hist = distill.tune_scales(W, Wh, Xtr, G=G, rounds=8)
        e1 = sc(Wt)
        print(f"  k={k} {bpw:.3f}bit  調整前 {e0:.4f} → 調整後 {e1:.4f}  "
              f"({100*(e0-e1)/e0:+.1f}%)  {time.time()-t0:.0f}秒")
        print(f"    較正データ上の推移: {hist}")
        rows.append(dict(層=name, k=k, bpw=round(float(bpw),4),
                         調整前=round(e0,5), 調整後=round(e1,5),
                         改善率=round(100*(e0-e1)/e0,2)))
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "results","distill.json"),"w"), ensure_ascii=False, indent=2)
print("\n保存完了")
