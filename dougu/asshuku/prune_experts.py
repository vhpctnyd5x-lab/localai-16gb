#!/usr/bin/env python3
"""prune_experts.py — MoE の専門家を GGUF から直接削る（逆量子化しない）。

設計の要点:
  ヘッダ（メタデータ＋テンソル情報）は**丸ごとコピーして固定長の数値だけ上書き**する。
  トークナイザの15万語を作り直さずに済むので、書き戻しで壊す危険がない。
  書き換えるのは3種類だけ:
    - KV の expert_count (u32)
    - 専門家テンソルの最終次元 ne[last] (u64)
    - 各テンソルの data offset (u64)

  専門家1個ぶんのバイト列は連続していてブロック境界に載っているので、そのまま切り出せる。

使い方:
  python3 prune_experts.py --in <gguf> --out <gguf> --scores <tsv> --keep 96
"""
import argparse, os, struct, sys

# ggml の型 -> (1ブロックの要素数, 1ブロックのバイト数)
BLK = {0:(1,4), 1:(1,2), 2:(32,18), 3:(32,20), 6:(32,22), 7:(32,24),
       8:(32,34), 9:(32,36), 10:(256,84), 11:(256,110),
       12:(256,144), 13:(256,176), 14:(256,210), 15:(256,292),
       16:(256,66), 17:(256,74), 18:(256,98), 19:(256,50), 20:(32,18),   # IQ2_XXS IQ2_XS IQ3_XXS IQ1_S IQ4_NL（9/24 IQ 版を刈れずに落ちた）
       21:(256,110), 22:(256,82), 23:(256,136), 29:(256,56),              # IQ3_S IQ2_S IQ4_XS IQ1_M
       30:(1,2)}          # 30 = BF16。Qwen3-Next の ffn_gate_inp_shexp がこれ（実験49で追加）
TYPENAME = {0:'F32',1:'F16',2:'Q4_0',3:'Q4_1',6:'Q5_0',7:'Q5_1',8:'Q8_0',9:'Q8_1',
            10:'Q2_K',11:'Q3_K',12:'Q4_K',13:'Q5_K',14:'Q6_K',15:'Q8_K',16:'IQ2_XXS',17:'IQ2_XS',
            18:'IQ3_XXS',19:'IQ1_S',20:'IQ4_NL',21:'IQ3_S',22:'IQ2_S',23:'IQ4_XS',29:'IQ1_M',30:'BF16'}

class HeaderParser:
    """ヘッダを走査して、後で上書きしたい場所のファイル内オフセットを覚える。"""
    def __init__(self, f):
        self.f = f
        assert f.read(4) == b'GGUF', 'GGUFではない'
        self.version, = struct.unpack('<I', f.read(4))
        self.n_tensors, = struct.unpack('<Q', f.read(8))
        self.n_kv, = struct.unpack('<Q', f.read(8))
        self.kv_pos = {}        # key -> (値のファイル内オフセット, 型)
        self.meta = {}
        for _ in range(self.n_kv):
            k = self._str()
            t, = struct.unpack('<I', f.read(4))
            pos = f.tell()
            v = self._val(t)
            self.kv_pos[k] = (pos, t)
            self.meta[k] = v
        self.tensors = []       # (name, dims, type, off_pos, dims_pos, data_off)
        for _ in range(self.n_tensors):
            name = self._str()
            nd, = struct.unpack('<I', f.read(4))
            dims_pos = f.tell()
            dims = struct.unpack('<%dQ' % nd, f.read(8*nd))
            ttype, = struct.unpack('<I', f.read(4))
            off_pos = f.tell()
            data_off, = struct.unpack('<Q', f.read(8))
            self.tensors.append([name, list(dims), ttype, off_pos, dims_pos, data_off])
        self.header_end = f.tell()
        self.align = self.meta.get('general.alignment', 32)
        self.data_start = (self.header_end + self.align - 1)//self.align*self.align

    def _str(self):
        n, = struct.unpack('<Q', self.f.read(8))
        return self.f.read(n).decode('utf-8', 'replace')

    def _val(self, t):
        s = {0:('<B',1),1:('<b',1),2:('<H',2),3:('<h',2),4:('<I',4),5:('<i',4),
             6:('<f',4),7:('<?',1),10:('<Q',8),11:('<q',8),12:('<d',8)}
        if t in s:
            fmt, n = s[t]; return struct.unpack(fmt, self.f.read(n))[0]
        if t == 8: return self._str()
        if t == 9:
            et, = struct.unpack('<I', self.f.read(4))
            n,  = struct.unpack('<Q', self.f.read(8))
            return [self._val(et) for _ in range(n)]
        raise ValueError('未知のKV型 %d' % t)

def nbytes(dims, ttype, name=''):
    if ttype not in BLK:
        raise SystemExit(f'未知の ggml 型 {ttype}（テンソル {name}）。BLK に足すこと。')
    el, by = BLK[ttype]
    n = 1
    for d in dims: n *= d
    assert n % el == 0, 'ブロックで割り切れない'
    return n // el * by

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in',  dest='src', required=True)
    ap.add_argument('--out', dest='dst', required=True)
    ap.add_argument('--scores', required=True)
    ap.add_argument('--keep', type=int, required=True, help='残す専門家の数')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    # --- 採点を読む: 層 -> [(score, expert), ...]
    per_layer = {}
    for line in open(a.scores, encoding='utf-8'):
        if line.startswith('#'): continue
        p = line.split('\t')
        per_layer.setdefault(int(p[0]), []).append((float(p[2]), int(p[1])))

    f = open(a.src, 'rb')
    h = HeaderParser(f)
    arch = h.meta['general.architecture']
    ck = f'{arch}.expert_count'
    n_exp = h.meta[ck]
    print(f'{arch} / 専門家 {n_exp} → {a.keep} / テンソル {h.n_tensors} / align {h.align}')
    assert 0 < a.keep < n_exp

    # --- 層ごとに残す専門家（スコア降順の上位 keep 個、元の順で並べ直す）
    keep = {}
    for il, v in per_layer.items():
        v.sort(reverse=True)
        keep[il] = sorted(e for _, e in v[:a.keep])
    print(f'採点のある層: {len(keep)}  例) 層0で捨てる数 = {n_exp - len(keep[0])}')

    # --- 専門家次元を持つテンソルを見つける（最終次元が n_exp のもの）
    plan = []      # (tensor, per_expert_bytes or None)
    n_cut = 0
    for t in h.tensors:
        name, dims, ttype = t[0], t[1], t[2]
        il = None
        if name.startswith('blk.'):
            il = int(name.split('.')[1])
        # 名前で明示的に選ぶ。attn_k_norm/attn_q_norm は形が [128] で
        # 専門家数と偶然一致するため、形だけで判定すると壊す。
        is_exp = name.endswith('_exps.weight') or name.endswith('ffn_gate_inp.weight')
        if is_exp and il is not None and il in keep and dims and dims[-1] == n_exp:
            per = nbytes(dims[:-1], ttype, name)
            plan.append((t, per, il)); n_cut += 1
        else:
            plan.append((t, None, None))
    print(f'切り出すテンソル: {n_cut} 本')
    for t, per, il in plan[:6]:
        if per: print(f'   {t[0]:34s} {TYPENAME.get(t[2],t[2]):5s} {t[1]}  1専門家={per}B')

    # --- 新しい offset を決める（ヘッダの長さは変わらない）
    new_off, cur = {}, 0
    total_old = total_new = 0
    for t, per, il in plan:
        sz_old = nbytes(t[1], t[2], t[0])
        sz_new = per * a.keep if per else sz_old
        cur = (cur + h.align - 1)//h.align*h.align
        new_off[t[0]] = cur
        cur += sz_new
        total_old += sz_old; total_new += sz_new
    print(f'データ部: {total_old/1e9:.3f} GB → {total_new/1e9:.3f} GB '
          f'（{100*(1-total_new/total_old):.1f}% 減）')
    print(f'ファイル全体の見込み: {(h.data_start+total_new)/1e9:.3f} GB')
    if a.dry_run:
        return

    # --- ヘッダをコピーして固定長の数値だけ上書き
    f.seek(0); head = bytearray(f.read(h.header_end))
    struct.pack_into('<I', head, h.kv_pos[ck][0], a.keep)          # expert_count
    for t, per, il in plan:
        struct.pack_into('<Q', head, t[3], new_off[t[0]])          # data offset
        if per:
            nd = len(t[1])
            struct.pack_into('<Q', head, t[4] + 8*(nd-1), a.keep)  # ne[last]
    out = open(a.dst, 'wb')
    out.write(head)
    pad = h.data_start - h.header_end
    if pad: out.write(b'\x00'*pad)

    CH = 8*1024*1024
    for idx, (t, per, il) in enumerate(plan):
        while out.tell() - h.data_start < new_off[t[0]]:
            out.write(b'\x00'*min(CH, new_off[t[0]] - (out.tell()-h.data_start)))
        base = h.data_start + t[5]
        if per is None:
            f.seek(base); left = nbytes(t[1], t[2], t[0])
            while left: b = f.read(min(CH,left)); out.write(b); left -= len(b)
        else:
            for e in keep[il]:
                f.seek(base + per*e); left = per
                while left: b = f.read(min(CH,left)); out.write(b); left -= len(b)
        if idx % 100 == 0:
            print(f'  {idx}/{len(plan)}  {out.tell()/1e9:.2f} GB', flush=True)
    out.close(); f.close()
    print(f'できた: {a.dst}  {os.path.getsize(a.dst)/1e9:.3f} GB')

main()
