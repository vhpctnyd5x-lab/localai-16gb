"""GGUF書き出し。圧縮した重みを実モデルに戻して、本当に動かして測るための道具。

やり方: 元のGGUFを読み、指定したテンソルだけ我々のレシピで圧縮→復元した値に差し替え、
F16として書き出す。ファイルは大きくなるが「その重みで実際に推論したらどうなるか」を
perplexityと実速度で測れるようになる。これが無いと世界の手法と同じ土俵に立てない。
"""
import struct
import numpy as np
import gguf as G


def _w_str(f, s):
    b = s.encode("utf-8")
    f.write(struct.pack("<Q", len(b))); f.write(b)


def _w_val(f, t, v, raw=None):
    """メタデータ1個を書く。raw があればバイト列をそのまま流す（配列の丸写し用）。"""
    simple = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i",
              6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
    f.write(struct.pack("<I", t))
    if t in simple:
        f.write(struct.pack(simple[t], v))
    elif t == 8:
        _w_str(f, v)
    else:
        raise ValueError(f"未対応の型 {t}")


class Copier:
    """元GGUFのメタデータをそのまま引き継ぎ、テンソルだけ差し替える。"""

    def __init__(self, src_path):
        self.r = G.Reader(src_path)
        self.src = src_path

    def _copy_metadata_bytes(self):
        """メタデータ領域を生バイトで丸ごと写す（型解釈の取りこぼしを避ける）。"""
        f = open(self.src, "rb")
        f.seek(0)
        head = f.read(24)                       # magic, version, n_tensors, n_kv
        # メタデータの終端 = テンソル情報の開始位置を求めるため、リーダの結果を利用
        # リーダは全部読み終えた位置を data_start 手前に持っている
        f.close()
        return head

    def write(self, out_path, replace):
        """replace: {テンソル名: ndarray(float32)}  指定したものだけF16で差し替える。"""
        r = self.r
        src = open(self.src, "rb")

        # --- メタデータ部分を生コピー ---
        src.seek(0)
        magic_ver = src.read(8)
        n_tensors, n_kv = struct.unpack("<QQ", src.read(16))
        # メタデータKVの終端位置を実測するため、リーダと同じ手順で読み飛ばす
        rr = G.Reader(self.src)          # 位置情報を得るために再パース
        # rr のファイルハンドルは KV を読み終えた後、テンソル情報も読んでいる。
        # KV終端は自前で測り直す。
        src.seek(24)
        tmp = G.Reader.__new__(G.Reader)
        tmp.f = src
        for _ in range(n_kv):
            tmp._str()
            tmp._value()
        kv_end = src.tell()
        src.seek(24)
        kv_blob = src.read(kv_end - 24)

        # --- 新しいテンソル情報を組み立てる ---
        names = list(r.tensors.keys())
        infos, blobs = [], {}
        align = r.meta.get("general.alignment", 32)
        offset = 0
        for name in names:
            dims, ttype, off = r.tensors[name]
            if name in replace:
                arr = np.ascontiguousarray(replace[name].astype(np.float16))
                data = arr.tobytes()
                new_type = 1                      # F16
            else:
                _, _, blk_b = G.TYPES.get(ttype, (None, None, None))
                n = 1
                for d in dims:
                    n *= d
                if ttype in G.TYPES:
                    blk_n, blk_b = G.TYPES[ttype][1], G.TYPES[ttype][2]
                    nbytes = n // blk_n * blk_b
                else:
                    raise ValueError(f"未対応の型のテンソルがある: {name} type={ttype}")
                src.seek(r.data_start + off)
                data = src.read(nbytes)
                new_type = ttype
            pad = (-len(data)) % align
            blobs[name] = data + b"\x00" * pad
            infos.append((name, dims, new_type, offset))
            offset += len(data) + pad

        # --- 書き出し ---
        with open(out_path, "wb") as f:
            f.write(magic_ver)
            f.write(struct.pack("<QQ", n_tensors, n_kv))
            f.write(kv_blob)
            for name, dims, ttype, off in infos:
                _w_str(f, name)
                f.write(struct.pack("<I", len(dims)))
                f.write(struct.pack(f"<{len(dims)}Q", *dims))
                f.write(struct.pack("<I", ttype))
                f.write(struct.pack("<Q", off))
            pos = f.tell()
            f.write(b"\x00" * ((-pos) % align))
            for name, _, _, _ in infos:
                f.write(blobs[name])
        src.close()
        return out_path
