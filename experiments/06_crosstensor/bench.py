"""実験06: 回転はどこで効くのか、そして結論は他の層でも成り立つのか。

実験04で回転は逆効果だった。仮説:
  回転は「少数の外れ値を散らす」ための道具。対象テンソルの尖り(kurtosis)は約3.0＝
  すでに正規分布そのもので、散らすべき外れ値が無い。一方ベクトル量子化は
  「重みの並びに構造があること」を利用するので、回転はその構造を壊すだけ損。
予測:
  (a) 外れ値の多いテンソルでは回転がスカラー量子化を助ける。
  (b) ベクトル量子化に対しては、どのテンソルでも回転は中立〜有害。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, wcodec as C, rotate

BLOB = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
        "sha256-81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490")
TENSORS = ["v.blk.0.mlp.linear_fc1.weight",   # 視覚側 F16 (真の全精度)
           "blk.0.attn_qkv.weight",           # LLM本体 Q4_K
           "blk.0.ffn_gate.weight",           # LLM本体 Q4_K
           "blk.10.ffn_up.weight"]            # 中間層

def kurt(W):
    z = (W - W.mean()) / W.std()
    return float((z ** 4).mean())

r_ = gguf.Reader(BLOB)
allrows = []
for name in TENSORS:
    W0, tname = r_.load(name)
    W0 = np.ascontiguousarray(W0.astype(np.float32))
    out, inn = W0.shape
    if inn & (inn - 1):     # 2のべき乗でなければ回転できないので末尾を切る
        p = 1 << (inn.bit_length() - 1)
        W0 = np.ascontiguousarray(W0[:, :p]); inn = p
    rng = np.random.default_rng(999)
    X0 = rng.standard_t(4, size=(inn, 128)).astype(np.float32)
    X0[rng.choice(inn, max(1, inn // 100), replace=False)] *= 20.
    rot_W, rot_x, _ = rotate.make(inn, seed=0)

    print(f"\n=== {name}  {W0.shape}  元={tname}  尖り={kurt(W0):.2f} "
          f"(正規分布なら3.0) ===")
    print(f"{'方式':<30}{'bit/重み':>9}{'回転なし':>10}{'回転あり':>10}{'差':>9}")
    print("-" * 68)
    Wr = rot_W(W0); Xr = rot_x(X0)
    print(f"{'(回転後の尖り)':<30}{'':>9}{'':>10}{kurt(Wr):>10.2f}")
    methods = [
        ("スカラー RTN 4bit", lambda W: C.rtn(W, 4, 128)),
        ("スカラー RTN 2bit", lambda W: C.rtn(W, 2, 128)),
        ("スカラー 三値",      lambda W: C.ternary(W, 128)),
        ("ベクトル PVQ コード16",  lambda W: C.pvq(W, k=8, cb_bits=4, G=128)),
        ("ベクトル PVQ コード256", lambda W: C.pvq(W, k=8, cb_bits=8, G=128)),
    ]
    for label, fn in methods:
        Wh, bpw, _ = fn(W0); _, a = C.evaluate(W0, Wh, X=X0)
        Wh2, _, _ = fn(Wr);  _, b = C.evaluate(Wr, Wh2, X=Xr)
        mark = "改善" if b < a * 0.99 else ("悪化" if b > a * 1.01 else "中立")
        print(f"{label:<30}{bpw:>9.3f}{a:>10.4f}{b:>10.4f}{mark:>9}")
        allrows.append(dict(tensor=name, 方式=label, bpw=round(bpw,4),
                            回転なし=round(float(a),5), 回転あり=round(float(b),5),
                            判定=mark, 尖り=round(kurt(W0),3)))

json.dump(allrows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "results", "crosstensor.json"), "w"),
          ensure_ascii=False, indent=2)
print("\n保存完了")
