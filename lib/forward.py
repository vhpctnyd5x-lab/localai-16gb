"""qwen2 の順伝播をnumpyで実装し、各層の「本物の入力」を捕まえる。

なぜ必要か:
  層ごとの出力を元モデルに合わせ込む「再構成」には、その層に実際に入ってくる
  活性化そのものが要る。imatrixはチャンネルごとの平均二乗しか持たず足りない。
  llama.cppに吐き出す機能がないので自前で回す。

速度は求めない。数百トークン分の活性化が採れれば目的を果たす。
"""
import numpy as np
import gguf


class Model:
    def __init__(self, path, in_memory=False):
        self.r = gguf.Reader(path, in_memory=in_memory)
        m = self.r.meta
        self.n_layer = m["qwen2.block_count"]
        self.d = m["qwen2.embedding_length"]
        self.n_head = m["qwen2.attention.head_count"]
        self.n_kv = m["qwen2.attention.head_count_kv"]
        self.hd = self.d // self.n_head
        self.eps = m["qwen2.attention.layer_norm_rms_epsilon"]
        self.theta = m["qwen2.rope.freq_base"]
        self._cache = {}

    def T(self, name):
        if name not in self._cache:
            a, _ = self.r.load(name)
            self._cache[name] = np.ascontiguousarray(a.astype(np.float32))
        return self._cache[name]

    def drop(self, name):
        self._cache.pop(name, None)


def rms_norm(x, w, eps):
    return x / np.sqrt((x * x).mean(-1, keepdims=True) + eps) * w


def rope(x, pos, theta):
    """x: (T, n_head, hd)。回転位置埋め込み。"""
    T, H, hd = x.shape
    half = hd // 2
    inv = 1.0 / (theta ** (np.arange(0, half, dtype=np.float64) * 2 / hd))
    ang = pos[:, None] * inv[None, :]              # (T, half)
    c, s = np.cos(ang)[:, None, :], np.sin(ang)[:, None, :]
    x1, x2 = x[..., :half], x[..., half:]
    return np.concatenate([x1 * c - x2 * s, x1 * s + x2 * c], -1).astype(np.float32)


def run(model, tokens, capture=None, replace=None, quantizer=None):
    """トークン列を流す。capture に層名を入れると、その層への入力を集めて返す。
    replace={テンソル名: 行列} で重みを差し替えられる（圧縮版の評価用）。"""
    M, r = model, model.r
    T = len(tokens)
    pos = np.arange(T)
    emb = M.T("token_embd.weight")                  # (vocab, d)
    x = emb[tokens].astype(np.float32)
    caught = {}
    quantized = {}

    def W(name):
        if replace and name in replace:
            return replace[name]
        return M.T(name)

    def lin(h, name):
        """h:(T,in) → (T,out)。GGUFは (out,in) 格納なので転置して掛ける。"""
        if capture is not None and name in capture:
            caught.setdefault(name, []).append(h.copy())
        if quantizer is not None and name in quantizer[0]:
            # この層に実際に入ってくる活性化を使って、その場で量子化する。
            # 以降の層は量子化済みの重みで動くので、誤差の伝播も現実的に扱える。
            if name not in quantized:
                quantized[name] = quantizer[1](name, M.T(name), h)
            w = quantized[name]
            y = h @ w.T
            b = name.replace(".weight", ".bias")
            if b in r.tensors:
                y = y + M.T(b)
            return y
        w = W(name)
        y = h @ w.T
        b = name.replace(".weight", ".bias")
        if b in r.tensors:
            y = y + M.T(b)
        return y

    for L in range(M.n_layer):
        p = f"blk.{L}."
        h = rms_norm(x, M.T(p + "attn_norm.weight"), M.eps)
        q = lin(h, p + "attn_q.weight").reshape(T, M.n_head, M.hd)
        k = lin(h, p + "attn_k.weight").reshape(T, M.n_kv, M.hd)
        v = lin(h, p + "attn_v.weight").reshape(T, M.n_kv, M.hd)
        q = rope(q, pos, M.theta); k = rope(k, pos, M.theta)
        rep = M.n_head // M.n_kv
        k = np.repeat(k, rep, axis=1); v = np.repeat(v, rep, axis=1)
        # 因果マスク付きattention
        att = np.einsum("thd,shd->hts", q, k) / np.sqrt(M.hd)
        mask = np.triu(np.full((T, T), -1e9, np.float32), 1)
        att = att + mask
        att -= att.max(-1, keepdims=True)
        np.exp(att, out=att)
        att /= att.sum(-1, keepdims=True)
        o = np.einsum("hts,shd->thd", att, v).reshape(T, M.d)
        x = x + lin(o, p + "attn_output.weight")

        h = rms_norm(x, M.T(p + "ffn_norm.weight"), M.eps)
        g = lin(h, p + "ffn_gate.weight")
        u = lin(h, p + "ffn_up.weight")
        act = g / (1.0 + np.exp(-g)) * u             # SwiGLU
        x = x + lin(act, p + "ffn_down.weight")
        for n in ("attn_q", "attn_k", "attn_v", "attn_output",
                  "ffn_gate", "ffn_up", "ffn_down"):
            M.drop(p + n + ".weight")               # メモリを抱え込まない

    x = rms_norm(x, M.T("output_norm.weight"), M.eps)
    logits = x @ M.T("token_embd.weight").T          # 重み共有
    if quantizer is not None:
        return logits, quantized
    if capture is not None:
        return logits, {k: np.concatenate(v, 0) for k, v in caught.items()}
    return logits
