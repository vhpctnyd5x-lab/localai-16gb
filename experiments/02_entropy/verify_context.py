"""文脈モデルの利得が本物か、ホールドアウトで検証する。

条件つきエントロピーは、状態数に対してサンプルが足りないと必ず過小評価される
（見たことのない組み合わせを確率0と誤認するため）。コード数4096なら遷移表は
1670万マスあるのにサンプルは26万しかない。素朴に計算した値は信用できない。

そこで前半で遷移確率を学習し、後半で「実際に符号化したら何ビットかかるか」を測る。
これは自己採点にならないので、下回れば本物。
"""
import os, sys, json
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, entropy as E

BLOB = ("/path/to/localai/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")
TENSOR = "v.blk.0.mlp.linear_fc1.weight"


def codes(W, k, cb_bits, G, seed=0):
    X = C._grouped(W, G); s = C._scales(X)
    Xn = (X / s).reshape(-1, k).astype(np.float32)
    Cb = C._kmeans(Xn, 2 ** cb_bits, seed=seed)
    return C._assign(Xn, Cb)


def holdout_order1(idx, ncode, alpha=0.5):
    """前半で学習→後半で実測。加法スムージング付き（未知の遷移でも有限ビットで済む）。"""
    n = len(idx); half = n // 2
    tr, te = idx[:half], idx[half:]
    # 学習: 遷移カウント（疎行列としてdictで持つ）
    from collections import defaultdict
    trans = defaultdict(lambda: defaultdict(int))
    row = np.zeros(ncode, np.float64)
    for a, b in zip(tr[:-1], tr[1:]):
        trans[int(a)][int(b)] += 1
        row[a] += 1
    # 評価: 後半を符号化したときの実ビット数
    bits = 0.0
    denom_const = alpha * ncode
    for a, b in zip(te[:-1], te[1:]):
        a, b = int(a), int(b)
        c = trans[a].get(b, 0)
        p = (c + alpha) / (row[a] + denom_const)
        bits -= np.log2(p)
    return bits / (len(te) - 1)


def holdout_order0(idx, ncode, alpha=0.5):
    n = len(idx); half = n // 2
    tr, te = idx[:half], idx[half:]
    cnt = np.bincount(tr, minlength=ncode).astype(np.float64)
    p = (cnt + alpha) / (cnt.sum() + alpha * ncode)
    return float(-np.log2(p[te]).mean())


r = gguf.Reader(BLOB)
W, _ = r.load(TENSOR); W = W.astype(np.float32)

print(f"{'設定':<22}{'名目':>8}{'素朴な文脈':>11}{'検証済み0次':>12}{'検証済み1次':>12}")
print("-" * 67)
rows = []
for k, cb, G in [(8, 4, 128), (8, 8, 128), (8, 10, 128), (16, 8, 256), (16, 12, 256)]:
    idx = codes(W, k, cb, G)
    ncode = 2 ** cb
    sb = 16 / G
    naive = E.conditional_entropy(idx, ncode) / k + sb
    h0 = holdout_order0(idx, ncode) / k + sb
    h1 = holdout_order1(idx, ncode) / k + sb
    nom = cb / k + sb
    print(f"k={k:2d},コード{ncode:5d}{'':<6}{nom:>8.4f}{naive:>11.4f}{h0:>12.4f}{h1:>12.4f}")
    rows.append(dict(k=k, ncode=ncode, 名目=round(nom,4), 素朴な文脈=round(naive,4),
                     検証済み0次=round(h0,4), 検証済み1次=round(h1,4)))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "verify_context.json")
json.dump(rows, open(out,"w"), ensure_ascii=False, indent=2)
print("\n保存:", out)
