"""誤差補償あり/なしの比較。較正用と評価用の活性化は必ず分ける。"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, errcomp as E

BLOB = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")
TENSOR = sys.argv[1] if len(sys.argv) > 1 else "v.blk.0.mlp.linear_fc1.weight"


def make_acts(n, ns, seed):
    """実際の活性化に似せる: 正規分布＋1%の突出チャンネル＋重い裾。"""
    rng = np.random.default_rng(seed)
    X = rng.standard_t(df=4, size=(n, ns)).astype(np.float32)
    big = rng.choice(n, max(1, n // 100), replace=False)
    X[big] *= 20.0
    return X


r = gguf.Reader(BLOB)
W, tname = r.load(TENSOR); W = W.astype(np.float32)
n = W.shape[1]
Xcal = make_acts(n, 512, 0)      # 較正用
Xev = make_acts(n, 128, 999)     # 評価用（別データ）

print(f"対象: {TENSOR} {W.shape} 元={tname}")
print(f"{'方式':<40}{'bit/重み':>9}{'重み誤差':>10}{'出力誤差':>10}{'秒':>7}")
print("-" * 78)
rows = []
cases = [
    ("補償なし", lambda: C.rtn(W, 2, 128)),
    ("補償あり", lambda: E.gptq_scalar(W, Xcal, 2, 128)),
    ("補償なし", lambda: C.ternary(W, 128)),
    ("補償あり", lambda: E.gptq_scalar(W, Xcal, ternary=True, G=128)),
    ("補償なし", lambda: C.pvq(W, k=4, cb_bits=4, G=128)),
    ("補償あり", lambda: E.gptq_pvq(W, Xcal, k=4, cb_bits=4, G=128)),
    ("補償なし", lambda: C.pvq(W, k=8, cb_bits=4, G=128)),
    ("補償あり", lambda: E.gptq_pvq(W, Xcal, k=8, cb_bits=4, G=128)),
    ("補償あり", lambda: E.gptq_pvq(W, Xcal, k=8, cb_bits=6, G=128)),
]
for tag, fn in cases:
    t0 = time.time(); Wh, bpw, label = fn()
    rw, ry = C.evaluate(W, Wh, X=Xev)
    dt = time.time() - t0
    print(f"{tag+' '+label:<40}{bpw:>9.3f}{rw:>10.4f}{ry:>10.4f}{dt:>7.1f}")
    rows.append(dict(補償=tag, 方式=label, bpw=round(bpw,4),
                     重み誤差=round(float(rw),5), 出力誤差=round(float(ry),5)))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                   f"errcomp_{TENSOR}.json")
json.dump(dict(tensor=TENSOR, rows=rows), open(out,"w"), ensure_ascii=False, indent=2)
print("\n保存:", out)
