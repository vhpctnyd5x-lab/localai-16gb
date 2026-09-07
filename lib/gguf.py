"""最小限のGGUFリーダー。実モデルの重み行列を1枚だけ取り出すための道具。

対応する量子化: F32 / F16 / Q8_0 / Q6_K / Q4_K。
（llama.cpp の ggml-quants.c の定義に合わせてある）
"""
import struct
import numpy as np

# ggml_type -> (名前, ブロックあたりの要素数, ブロックあたりのバイト数)
TYPES = {
    0:  ("F32",  1,  4),
    1:  ("F16",  1,  2),
    8:  ("Q8_0", 32, 34),
    12: ("Q4_K", 256, 144),
    14: ("Q6_K", 256, 210),
}


class Reader:
    def __init__(self, path, in_memory=False):
        self.path = path
        if in_memory:
            import io
            with open(path, "rb") as fh:
                self.f = io.BytesIO(fh.read())   # 一度だけ読んで以後はメモリから
        else:
            self.f = open(path, "rb")
        magic = self.f.read(4)
        assert magic == b"GGUF", f"GGUFではない: {magic!r}"
        self.version, = struct.unpack("<I", self.f.read(4))
        n_tensors, = struct.unpack("<Q", self.f.read(8))
        n_kv, = struct.unpack("<Q", self.f.read(8))
        self.meta = {}
        for _ in range(n_kv):
            k = self._str()
            self.meta[k] = self._value()
        self.tensors = {}
        for _ in range(n_tensors):
            name = self._str()
            ndim, = struct.unpack("<I", self.f.read(4))
            dims = struct.unpack(f"<{ndim}Q", self.f.read(8 * ndim))
            ttype, = struct.unpack("<I", self.f.read(4))
            offset, = struct.unpack("<Q", self.f.read(8))
            self.tensors[name] = (dims, ttype, offset)
        align = self.meta.get("general.alignment", 32)
        pos = self.f.tell()
        self.data_start = (pos + align - 1) // align * align

    # --- メタデータのパース ---
    def _str(self):
        n, = struct.unpack("<Q", self.f.read(8))
        return self.f.read(n).decode("utf-8", "replace")

    def _value(self, t=None):
        if t is None:
            t, = struct.unpack("<I", self.f.read(4))
        simple = {0: ("<B", 1), 1: ("<b", 1), 2: ("<H", 2), 3: ("<h", 2),
                  4: ("<I", 4), 5: ("<i", 4), 6: ("<f", 4), 7: ("<?", 1),
                  10: ("<Q", 8), 11: ("<q", 8), 12: ("<d", 8)}
        if t in simple:
            fmt, n = simple[t]
            return struct.unpack(fmt, self.f.read(n))[0]
        if t == 8:
            return self._str()
        if t == 9:  # 配列
            et, = struct.unpack("<I", self.f.read(4))
            n, = struct.unpack("<Q", self.f.read(8))
            if n > 100000:  # 語彙などの巨大配列は読み飛ばす
                if et == 8:
                    for _ in range(n):
                        ln, = struct.unpack("<Q", self.f.read(8))
                        self.f.seek(ln, 1)
                else:
                    sz = {0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}[et]
                    self.f.seek(sz * n, 1)
                return f"<{n}要素・読み飛ばし>"
            return [self._value(et) for _ in range(n)]
        raise ValueError(f"未知の型 {t}")

    # --- テンソル取得 ---
    def list_tensors(self):
        out = []
        for name, (dims, t, off) in self.tensors.items():
            out.append((name, dims, TYPES.get(t, (f"type{t}",))[0]))
        return out

    def load(self, name):
        """テンソルを float32 の ndarray で返す（shape は行優先 (out, in)）。"""
        dims, ttype, off = self.tensors[name]
        if ttype not in TYPES:
            raise ValueError(f"未対応の量子化型 {ttype}: {name}")
        tname, blk_n, blk_b = TYPES[ttype]
        n = 1
        for d in dims:
            n *= d
        nbytes = n // blk_n * blk_b
        self.f.seek(self.data_start + off)
        raw = np.frombuffer(self.f.read(nbytes), dtype=np.uint8)
        flat = DEQUANT[tname](raw, n)
        # GGUFのdimsは (ne0=列, ne1=行) の順
        shape = tuple(reversed(dims))
        return flat.reshape(shape), tname


# ---------- 逆量子化 ----------
def _f32(raw, n):
    return raw.view(np.float32)[:n].astype(np.float32)


def _f16(raw, n):
    return raw.view(np.float16)[:n].astype(np.float32)


def _q8_0(raw, n):
    b = raw.reshape(-1, 34)
    d = b[:, :2].copy().view(np.float16).astype(np.float32)      # (nb,1)
    q = b[:, 2:].view(np.int8).astype(np.float32)                # (nb,32)
    return (q * d).ravel()[:n]


def _q4_k(raw, n):
    """Q4_K: 256要素/144バイト。d(f16) dmin(f16) scales(12B) qs(128B)"""
    b = raw.reshape(-1, 144)
    nb = b.shape[0]
    d = b[:, 0:2].copy().view(np.float16).astype(np.float32)     # (nb,1)
    dmin = b[:, 2:4].copy().view(np.float16).astype(np.float32)
    sc_raw = b[:, 4:16]                                          # (nb,12)
    qs = b[:, 16:144]                                            # (nb,128)

    # 12バイトから 8個の (scale, min) 6bit値を復元
    sc = np.zeros((nb, 8), np.float32)
    mn = np.zeros((nb, 8), np.float32)
    for j in range(8):
        if j < 4:
            s = sc_raw[:, j] & 63
            m = sc_raw[:, j + 4] & 63
        else:
            s = (sc_raw[:, j + 4] & 0x0F) | ((sc_raw[:, j - 4] >> 6) << 4)
            m = (sc_raw[:, j + 4] >> 4) | ((sc_raw[:, j] >> 6) << 4)
        sc[:, j] = s
        mn[:, j] = m

    # qs は 32要素ずつ 8サブブロック。バイト i の下位/上位ニブル
    q = np.empty((nb, 256), np.float32)
    lo = (qs & 0x0F).astype(np.float32)
    hi = (qs >> 4).astype(np.float32)
    for pair in range(4):                # 64バイトごとに 2サブブロック
        seg = slice(pair * 32, pair * 32 + 32)
        q[:, pair * 64: pair * 64 + 32] = lo[:, seg]
        q[:, pair * 64 + 32: pair * 64 + 64] = hi[:, seg]

    d_sub = (d * sc).repeat(32, axis=1)
    m_sub = (dmin * mn).repeat(32, axis=1)
    return (d_sub * q - m_sub).ravel()[:n]


def _q6_k(raw, n):
    """Q6_K: 256要素/210バイト。ql(128) qh(64) scales(int8 x16) d(f16)"""
    b = raw.reshape(-1, 210)
    nb = b.shape[0]
    ql = b[:, 0:128]
    qh = b[:, 128:192]
    sc = b[:, 192:208].view(np.int8).astype(np.float32)          # (nb,16)
    d = b[:, 208:210].copy().view(np.float16).astype(np.float32)  # (nb,1)

    q = np.empty((nb, 256), np.float32)
    for half in range(2):                # 128要素ずつ
        qlo = ql[:, half * 64: half * 64 + 64]
        qho = qh[:, half * 32: half * 32 + 32]
        base = half * 128
        for k in range(4):
            lo = (qlo[:, (k % 2) * 32:(k % 2) * 32 + 32] >> (4 * (k // 2))) & 0x0F
            hi = (qho >> (2 * k)) & 0x03
            v = (lo.astype(np.int16) | (hi.astype(np.int16) << 4)) - 32
            q[:, base + k * 32: base + k * 32 + 32] = v
    d_sub = (d * sc).repeat(16, axis=1)
    return (d_sub * q).ravel()[:n]


DEQUANT = {"F32": _f32, "F16": _f16, "Q8_0": _q8_0, "Q4_K": _q4_k, "Q6_K": _q6_k}
