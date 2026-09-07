import os
"""実モデルの重み行列で、1ビット未満まで含む各コーデックを比較する。

使い方:
  /usr/bin/python3 bench.py            # 既定のテンソル1枚
  /usr/bin/python3 bench.py --tensor blk.0.ffn_gate.weight
"""
import argparse, json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C

BLOB = (os.environ.get("MODEL_BLOB") or "/path/to/localai/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")


def build_codecs():
    return [
        ("基準8bit", lambda W: C.rtn(W, 8, 128)),
        ("基準4bit", lambda W: C.rtn(W, 4, 128)),
        ("基準2bit", lambda W: C.rtn(W, 2, 128)),
        ("1bit級", lambda W: C.ternary(W, 128)),
        ("1bit未満", lambda W: C.pvq(W, k=4, cb_bits=4, G=128)),   # 1.0bit
        ("1bit未満", lambda W: C.pvq(W, k=8, cb_bits=6, G=128)),   # 0.75bit
        ("1bit未満", lambda W: C.pvq(W, k=8, cb_bits=4, G=128)),   # 0.5bit
        ("1bit未満", lambda W: C.pvq(W, k=8, cb_bits=4, G=256)),   # 0.56→0.5bit
        ("1bit未満", lambda W: C.pvq(W, k=16, cb_bits=8, G=256)),  # 0.5bit
        ("1bit未満", lambda W: C.pvq(W, k=8, cb_bits=4, G=128, random_codebook=True)),
        ("ハイブリッド", lambda W: C.hybrid(W, 0.01, 8, G=128)),
        ("ハイブリッド", lambda W: C.hybrid(W, 0.03, 8, G=128)),
        ("ハイブリッド", lambda W: C.hybrid(
            W, 0.03, 8, G=128, sub=lambda M: C.pvq(M, k=16, cb_bits=8, G=256))),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tensor", default="v.blk.0.mlp.linear_fc1.weight")
    ap.add_argument("--blob", default=BLOB)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))
    a = ap.parse_args()

    r = gguf.Reader(a.blob)
    W, tname = r.load(a.tensor)
    W = W.astype(np.float32)
    print(f"対象: {a.tensor}  {W.shape}  元の格納形式={tname}  std={W.std():.5f}")
    print(f"{'区分':<12}{'方式':<44}{'bit/重み':>9}{'重み誤差':>10}{'出力誤差':>10}{'秒':>7}")
    print("-" * 94)

    rows = []
    for cat, fn in build_codecs():
        t0 = time.time()
        Wh, bpw, label = fn(W)
        rw, ry = C.evaluate(W, Wh)
        dt = time.time() - t0
        print(f"{cat:<12}{label:<44}{bpw:>9.3f}{rw:>10.4f}{ry:>10.4f}{dt:>7.1f}")
        rows.append(dict(区分=cat, 方式=label, bpw=round(bpw, 4),
                         重み誤差=round(float(rw), 5), 出力誤差=round(float(ry), 5)))

    os.makedirs(a.out, exist_ok=True)
    p = os.path.join(a.out, a.tensor.replace("/", "_") + ".json")
    with open(p, "w") as f:
        json.dump(dict(tensor=a.tensor, shape=list(W.shape), stored_as=tname, rows=rows),
                  f, ensure_ascii=False, indent=2)
    print(f"\n保存: {p}")


if __name__ == "__main__":
    main()
