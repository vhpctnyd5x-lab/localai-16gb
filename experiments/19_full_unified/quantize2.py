"""統合レシピをモデル全体に適用する（堅牢版）。

前版の失敗から直したこと:
  1. チェックポイントを**層ごとの個別ファイル**に。全体の書き直しをしないので
     処理時間が層数に依存しない（前版は10層ごとに8GBを書き直していた）。
  2. 量子化した重みを**RAMに溜めない**。使い終わったら解放する
     （前版はスワップを13GB使い切って停止した）。
  3. float16で保存。容量半分。
  4. I/Oエラーを**再試行**する（exFAT経由で一度失敗している）。
  5. ログをディスクに残す。
  6. 既存の層はスキップ。何度でも中断・再開できる。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import gguf, ggufwrite, forward, recipe as RP

MODEL = ("/Volumes/Mac Windows/LocalAI/ollama-models/blobs/"
         "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
NAME = os.environ.get("NAME", "unified")
CKPT = os.path.join(ROOT, "data", "ckpt", NAME)
LOG = os.path.join(ROOT, "data", "ckpt", NAME + ".log")
NTOK = int(os.environ.get("NTOK", "1024"))
RANK = int(os.environ.get("RANK", "32"))
K = int(os.environ.get("K", "8"))
CB = int(os.environ.get("CB", "8"))
GRP = int(os.environ.get("GRP", "256"))
os.makedirs(CKPT, exist_ok=True)


def say(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def retry(fn, what, n=4):
    """外部SSDのI/Oは時々こける。数回粘ってから諦める。"""
    for i in range(n):
        try:
            return fn()
        except OSError as e:
            say(f"  I/O失敗({what}) {i+1}/{n}回目: {e}")
            time.sleep(5 * (i + 1))
    raise OSError(f"{what} が {n} 回失敗")


toks = json.load(open(os.path.join(ROOT, "data/calib/tokens_big.json")))[:NTOK]
m = forward.Model(MODEL, in_memory=True)
targets = {n for n, (d, t, o) in m.r.tensors.items()
           if len(d) == 2 and n.startswith("blk.") and n.endswith(".weight")
           and ("attn" in n or "ffn" in n)}
have = {f[:-4] for f in os.listdir(CKPT) if f.endswith(".npy")}
say(f"対象{len(targets)}層 / 済み{len(have)}層 / 残り{len(targets - have)}層 "
    f"(較正{len(toks)}トークン, ランク{RANK} k={K} コード{2**CB} G={GRP})")

st = {"n": len(have), "t0": time.time(), "bits": 0.0, "w": 0}


def quantize(name, W, h):
    p = os.path.join(CKPT, name + ".npy")
    if os.path.exists(p):
        return retry(lambda: np.load(p).astype(np.float32), f"読込 {name}")
    X = np.ascontiguousarray(h.T.astype(np.float32))
    inn = W.shape[1]
    t0 = time.time()
    try:
        if X.shape[1] >= inn:
            Wh, bpw = RP.fit(W, X, rank=RANK, k=K, cb_bits=CB, G=GRP)
        else:
            # 標本不足で完全なヘッセ行列を使うと壊れる（序盤の失敗の教訓）。対角のみに落とす。
            imp = np.sqrt((X ** 2).mean(1))
            imp /= np.exp(np.log(imp + 1e-30).mean())
            s = imp ** 0.75
            Wh, bpw = RP.fit(W * s[None, :], np.eye(inn, dtype=np.float32),
                             rank=RANK, k=K, cb_bits=CB, G=GRP)
            Wh = Wh / s[None, :]
    except Exception as e:
        say(f"  !! {name} 失敗({type(e).__name__}: {e}) → 元の重みのまま")
        Wh, bpw = W.astype(np.float32), 16.0
    retry(lambda: np.save(p, Wh.astype(np.float16)), f"保存 {name}")
    st["n"] += 1; st["bits"] += bpw * W.size; st["w"] += W.size
    say(f"  [{st['n']:3d}/{len(targets)}] {name:<30} {bpw:.3f}bit "
        f"{time.time()-t0:.0f}秒 累計{(time.time()-st['t0'])/60:.0f}分")
    del X
    return Wh.astype(np.float32)


forward.run(m, toks, quantizer=(targets, quantize))
if st["w"]:
    say(f"今回量子化した分の平均 {st['bits']/st['w']:.4f} bit/重み")
say("全層完了。GGUFを組み立てる。")

# 組み立ては層を1枚ずつ読みながら行う（全部を同時に持たない）
class Lazy(dict):
    def __contains__(self, k):
        return os.path.exists(os.path.join(CKPT, k + ".npy"))
    def __getitem__(self, k):
        return np.load(os.path.join(CKPT, k + ".npy")).astype(np.float32)

OUT = os.path.join(ROOT, "data/models", NAME + ".gguf")
ggufwrite.Copier(MODEL).write(OUT, Lazy())
say(f"書き出し: {OUT}  {os.path.getsize(OUT)/1e9:.2f}GB")
