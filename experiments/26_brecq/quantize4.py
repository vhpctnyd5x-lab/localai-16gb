"""実験26-B: BRECQ＋AdaRound を載せた量子化。

quantize3（層ごとビット配分）との違いは2点だけ:

  ① **先生の活性化も一緒に流す**。
     各層で「生徒の入力 X_s」と「先生の入力 X_t」の両方を持ち、
     先生の出力に追いつくための理想の重み W* を解いてから量子化する。
     → 前の層でついたずれを、次の層が打ち消しにいく（BRECQ）

  ② 残差の割り当てを、出力誤差基準にする（AdaRound）。

【実装の肝】
forward.run を2回まわすのではなく、**先生の活性化を先に採って保存**しておき、
量子化のときに読み出す。2回まわすとRAM 16GBでは持たない。

ADAROUND=0 / BRECQ=0 で個別に切れる。効果を切り分けるため。
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import numpy as np
import forward, ggufwrite, recipe as RP, brecq

# MODEL 環境変数で元モデルの場所を差し替えられる（SSD が不安定なとき内蔵ディスクの退避コピーで回すため）
MODEL = os.environ.get("MODEL") or (
        "/path/to/localai/ollama-models/blobs/"
        "sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba")
NAME = os.environ.get("NAME", "brecq")
CKPT = os.path.join(ROOT, "data", "ckpt", NAME)
# 較正トークン列。先生の活性化は「どのトークン列で採ったか」で中身が変わるので、
# 既定以外のトークン列（個人較正など）では別の置き場にする。
# ここを分けないと、TOKENS を替えても tokens_big で採った先生の活性化が黙って再利用される。
TOKENS_PATH = os.environ.get("TOKENS", "data/calib/tokens_big.json")
_TTAG = os.path.splitext(os.path.basename(TOKENS_PATH))[0]
SENSEI = os.path.join(ROOT, "data", "ckpt",
                      "sensei_acts" if _TTAG == "tokens_big" else "sensei_acts_" + _TTAG)
LOG = os.path.join(ROOT, "data", "ckpt", NAME + ".log")
NTOK = int(os.environ.get("NTOK", "512"))
USE_ADA = os.environ.get("ADAROUND", "1") != "0"
USE_BRECQ = os.environ.get("BRECQ", "1") != "0"
# LATTICE=e8 で残差の語彙を k-means から E8 格子に替える（K=8 必須）。R2 は球の半径²。
LATTICE = os.environ.get("LATTICE") or None
R2 = float(os.environ.get("R2", "10"))
RECIPE = os.environ.get("RECIPE",
                        os.path.join(ROOT, "experiments/23_alloc/results/recipe.json"))
def _load_recipe(path):
    """レシピを読む。無い・空・壊れている なら「レシピ無し」として扱う。

    RECIPE=/dev/null で配分を切る使い方をするので、
    「存在するが中身が無い」を素通しできないと落ちる（実際に落ちた）。
    """
    try:
        with open(path, encoding="utf-8") as f:
            t = f.read().strip()
        return json.loads(t) if t else {}
    except (OSError, ValueError):
        return {}


PLAN = _load_recipe(RECIPE)
os.makedirs(CKPT, exist_ok=True)
os.makedirs(SENSEI, exist_ok=True)


def say(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    # ログ自体がSSD上にある。切断中はここで OSError になり、retry() の再試行より先に
    # 落ちていた（3回目の切断で実証）。ログが書けなくても処理は続ける。
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def retry(fn, what, n=8):
    # 切断は自動再マウントまで 1 分弱かかることがある。5+10+…+40 = 180 秒まで粘る。
    for i in range(n):
        try:
            return fn()
        except OSError as e:
            say(f"  I/O失敗({what}) {i+1}/{n}: {e}")
            time.sleep(5 * (i + 1))
    raise OSError(f"{what} が {n} 回失敗")


# 較正に使うトークン列を差し替えられるようにする。
# 汎用の文章で測るか、その人自身の文章で測るかで「どの列が大事か」が変わる。
# 同じビット数でも、使い手に合わせて痩せさせられるか——を確かめるための入口。
toks = json.load(open(os.path.join(ROOT, TOKENS_PATH)))[:NTOK]
m = forward.Model(MODEL, in_memory=True)
targets = {n for n, (d, t, o) in m.r.tensors.items()
           if len(d) == 2 and n.startswith("blk.") and n.endswith(".weight")
           and ("attn" in n or "ffn" in n)}

# BLKMAX: この番号までのブロックだけを量子化し、残りは元の精度で通す。
# 全層6時間を待たずに「浅い層を壊していないか」だけを15分で確かめるための仕組み。
# 崩壊は毎回 浅い層で起きているので、そこだけ再現できれば十分な検査になる。
BLKMAX = int(os.environ.get("BLKMAX", "-1"))
if BLKMAX >= 0:
    targets = {n for n in targets if int(n.split(".")[1]) <= BLKMAX}
    say(f"※ 簡易検査モード: blk.0〜blk.{BLKMAX} のみ量子化（{len(targets)}層）")

# TRIP: 重みが元からこれ以上離れたら即中止。
# 相対誤差1.0超え＝「ゼロを入れるより元から遠い」。実験23・26はどちらも
# これが浅い層で起きて崩壊した。気づくのに6時間かけたので、番人を置く。
TRIP = float(os.environ.get("TRIP", "0.85"))

# ---- 第1段: 先生の活性化を採って保存する（量子化なしで一度流す）----
# 先生の活性化は使い回すが、**何トークンで採ったか**を必ず控えておく。
# ここを控えないと、NTOKを変えたときに古い（短い）活性化が黙って再利用され、
# 標本不足で BRECQ が無言でスキップされる。実際にそれで一度ハマった。
MARK = os.path.join(SENSEI, "ntok.txt")
_old = None
if os.path.exists(MARK):
    try:
        _old = int(open(MARK).read().strip())
    except ValueError:
        _old = None
if _old is not None and _old < NTOK:
    say(f"先生の活性化が {_old} トークンぶんしか無い（今回は {NTOK}）。採り直す")
    for _f in os.listdir(SENSEI):
        os.remove(os.path.join(SENSEI, _f))

need = [n for n in sorted(targets) if not os.path.exists(os.path.join(SENSEI, n + ".npy"))]
if USE_BRECQ and need:
    say(f"先生の活性化を採る（{len(need)}層ぶん、{NTOK}トークン）")
    t0 = time.time()
    caught = forward.run(m, toks, capture=set(need))
    # forward.run は capture 指定時 (logits, 採取した辞書) を返す。採取ぶんは [1]。
    # [0] は logits。ここを取り違えて一度落ちた（drift.py でも同じことをやった）
    got = caught[1] if isinstance(caught, tuple) else caught
    for n, v in got.items():
        X = np.concatenate(v, 0) if isinstance(v, list) else v
        retry(lambda: np.save(os.path.join(SENSEI, n + ".npy"), X.astype(np.float16)),
              f"保存 {n}")
    del caught, got
    open(MARK, "w").write(str(NTOK))
    say(f"  採取ずみ ({(time.time()-t0)/60:.1f}分)")

have = {f[:-4] for f in os.listdir(CKPT) if f.endswith(".npy")}
say(f"対象{len(targets)}層 / 済み{len(have)}層  "
    f"[AdaRound={'入' if USE_ADA else '切'} BRECQ={'入' if USE_BRECQ else '切'}"
    f"{' 語彙=' + LATTICE if LATTICE else ''}]")
st = {"n": len(have), "t0": time.time(), "bits": 0.0, "w": 0, "zure": []}


def quantize(name, W, h):
    p = os.path.join(CKPT, name + ".npy")
    if os.path.exists(p):
        return retry(lambda: np.load(p).astype(np.float32), f"読込 {name}")
    pl = PLAN.get(name, {})
    k = int(pl.get("k", os.environ.get("K", 8)))
    cb = int(pl.get("cb", os.environ.get("CB", 8)))
    G = int(pl.get("G", 256)); rank = int(pl.get("rank", 32))

    Xs = np.ascontiguousarray(h.T.astype(np.float32))     # 生徒の入力
    inn = W.shape[1]
    Wsrc, zure = W, None

    # ---- BRECQ: 先生の出力に追いつく理想の重みを解く ----
    sp = os.path.join(SENSEI, name + ".npy")
    if USE_BRECQ and os.path.exists(sp):
        Xt = np.load(sp).astype(np.float32).T
        n = min(Xs.shape[1], Xt.shape[1])
        if n < 32:
            say(f"  ※ {name}: 標本が{n}個しか無いので BRECQ を飛ばす")
        else:
            zure = brecq.drift(Xs[:, :n], Xt[:, :n])
            Wsrc = brecq.target_weight(W, Xs[:, :n], Xt[:, :n])
            st["zure"].append(zure)
        del Xt

    t0 = time.time()
    try:
        # 以前はここに「標本 < 入力次元 なら単位行列で代用する」分岐があった。
        # だが単位行列を渡すと H が単位行列になり、
        #   ・GPTQ の誤差補償（inv(H)の上三角が対角化され、掛ける相手が消える）
        #   ・出力を意識した低ランク分解（ただのSVDに退化）
        #   ・AdaRound（列ごとの重みが全部同じになる）
        # の3つが同時に無効化されていた。標本512に対し入力次元は2048以上なので、
        # **全252層がこの経路**だった。実験22〜26で主力が一度も動いていなかった。
        # 標本が足りなくても damp を足せば H は正則になる（本家GPTQも同じ）。
        # 実測(blk.0.ffn_gate, 未使用データ採点): 出力誤差 0.378 → 0.264
        Wh, bpw = RP.fit(Wsrc, Xs, rank=rank, k=k, cb_bits=cb, G=G,
                         adaround=USE_ADA, lattice=LATTICE, R2=R2)
    except Exception as e:
        say(f"  !! {name} 失敗({type(e).__name__}: {e}) → 元の重みのまま")
        Wh, bpw = W.astype(np.float32), 16.0
    # 元の重みからどれだけ離れたか。ずれ（出力側）だけ見ていると、
    # 出力は合っているのに重みが原形を失っている状態を見逃す（実験26の敗因）。
    werr = float(np.linalg.norm(Wh - W) / (np.linalg.norm(W) + 1e-12))
    if werr > TRIP:
        say(f"  !! 中止: {name} の重み誤差 {werr:.3f} が上限 {TRIP} を超えた")
        raise SystemExit(f"重み誤差が上限超過: {name} {werr:.3f}")
    retry(lambda: np.save(p, Wh.astype(np.float16)), f"保存 {name}")
    st["n"] += 1; st["bits"] += bpw * W.size; st["w"] += W.size
    z = f" ずれ{zure:.3f}" if zure is not None else ""
    z += f" 誤差{werr:.3f}"
    vocab = f"{LATTICE}({R2:g})" if LATTICE else f"cb={cb:>2}"
    say(f"  [{st['n']:3d}/{len(targets)}] {name:<30} k={k:>2} {vocab} "
        f"{bpw:.3f}bit{z} {time.time()-t0:.0f}秒 累計{(time.time()-st['t0'])/60:.0f}分")
    del Xs
    return Wh.astype(np.float32)


forward.run(m, toks, quantizer=(targets, quantize))
if st["w"]:
    say(f"今回の平均 {st['bits']/st['w']:.4f} bit/重み")
if st["zure"]:
    z = np.array(st["zure"])
    say(f"生徒の入力のずれ: 平均{z.mean():.3f} 最大{z.max():.3f}")
say("全層完了。GGUFを組み立てる。")


class Lazy(dict):
    def __contains__(self, k):
        return os.path.exists(os.path.join(CKPT, k + ".npy"))
    def __getitem__(self, k):
        return np.load(os.path.join(CKPT, k + ".npy")).astype(np.float32)


OUT = os.path.join(ROOT, "data/models", NAME + ".gguf")
ggufwrite.Copier(MODEL).write(OUT, Lazy())
say(f"書き出し: {OUT}  {os.path.getsize(OUT)/1e9:.2f}GB")
