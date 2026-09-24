#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prune_layers.py — GGUF から層をまるごと抜く（実験52）。

専門家の手術（prune_experts.py）との違い:
  ・専門家 : テンソルの中身を切り出すだけ。名前は変わらない。→ ヘッダは数値の上書きで済む
  ・層     : テンソル名 `blk.N.*` が変わる（詰め直すので）。→ **テンソル情報の節を作り直す**

安全のための設計:
  KV節（トークナイザ15万語が入っている）は **バイトごとそのままコピー** し、
  `<arch>.block_count` の u32 だけ上書きする。作り直すのはテンソル情報の節だけ。

  ★ 層は残差ブロックなので、抜いても後段は動く（形が変わらない）。
    ただし抜きすぎると当然壊れる。BI（Block Influence）の低い層から抜くこと。

使い方:
  python3 prune_layers.py --in a.gguf --out b.gguf --drop 22,25,28
  python3 prune_layers.py --in a.gguf --out b.gguf --scores layer.tsv --drop-n 6
"""
import argparse, os, struct, sys

BLK = {0:(1,4), 1:(1,2), 2:(32,18), 3:(32,20), 6:(32,22), 7:(32,24),
       8:(32,34), 9:(32,36), 10:(256,84), 11:(256,110),
       12:(256,144), 13:(256,176), 14:(256,210), 15:(256,292), 30:(1,2)}

def nbytes(dims, ttype, name=''):
    if ttype not in BLK:
        raise SystemExit(f'未知の ggml 型 {ttype}（テンソル {name}）')
    el, by = BLK[ttype]
    n = 1
    for d in dims: n *= d
    assert n % el == 0, f'ブロックで割り切れない: {name}'
    return n // el * by

class Header:
    def __init__(self, f):
        self.f = f
        assert f.read(4) == b'GGUF', 'GGUFではない'
        self.version, = struct.unpack('<I', f.read(4))
        self.n_tensors, = struct.unpack('<Q', f.read(8))
        self.n_kv, = struct.unpack('<Q', f.read(8))
        self.kv_pos, self.meta = {}, {}
        self.arrays_48 = []          # 層数と同じ長さの配列があれば警告する
        for _ in range(self.n_kv):
            k = self._str()
            t, = struct.unpack('<I', f.read(4))
            pos = f.tell()
            v = self._val(t)
            self.kv_pos[k] = (pos, t)
            self.meta[k] = v
        self.kv_end = f.tell()
        self.tensors = []            # [name, dims, type, data_off]
        for _ in range(self.n_tensors):
            name = self._str()
            nd, = struct.unpack('<I', f.read(4))
            dims = list(struct.unpack('<%dQ' % nd, f.read(8*nd)))
            ttype, = struct.unpack('<I', f.read(4))
            off, = struct.unpack('<Q', f.read(8))
            self.tensors.append([name, dims, ttype, off])
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
            for _ in range(n): self._val(et)
            return ('ARRAY', et, n)
        raise ValueError('未知のKV型 %d' % t)

def wstr(s):
    b = s.encode('utf-8')
    return struct.pack('<Q', len(b)) + b

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in',  dest='src', required=True)
    ap.add_argument('--out', dest='dst', required=True)
    ap.add_argument('--drop', default='', help='抜く層の番号（カンマ区切り）')
    ap.add_argument('--scores', default='', help='layer-score の TSV')
    ap.add_argument('--drop-n', type=int, default=0, help='BIの低い層を N 個抜く')
    ap.add_argument('--protect', default='', help='絶対に抜かない層（既定: 最初と最後の2層）')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    f = open(a.src, 'rb')
    h = Header(f)
    arch = h.meta['general.architecture']
    bck = f'{arch}.block_count'
    n_layer = h.meta[bck]
    print(f'{arch} / 層 {n_layer} / テンソル {h.n_tensors} / align {h.align}')

    # 層数と同じ長さの配列KVがあると、層を抜いたときに整合しなくなる
    for k, v in h.meta.items():
        if isinstance(v, tuple) and v[0] == 'ARRAY' and v[2] == n_layer:
            print(f'  ★注意: 層数と同じ長さの配列KVがある: {k}（{v[2]}件）。手当てが要るかもしれない')

    # --- 抜く層を決める
    if a.drop:
        drop = sorted(int(x) for x in a.drop.split(','))
    elif a.scores and a.drop_n > 0:
        bi = {}
        for line in open(a.scores, encoding='utf-8'):
            if line.startswith('#') or not line.strip(): continue
            p = line.split('\t'); bi[int(p[0])] = float(p[1])
        prot = set(int(x) for x in a.protect.split(',') if x) or {0, 1, n_layer-2, n_layer-1}
        cand = sorted((v, k) for k, v in bi.items() if k not in prot)
        drop = sorted(k for _, k in cand[:a.drop_n])
        print(f'  守る層: {sorted(prot)}')
    else:
        sys.exit('--drop か（--scores と --drop-n）が要る')
    drop_set = set(drop)
    assert all(0 <= d < n_layer for d in drop), '層番号が範囲外'
    keep_layers = [i for i in range(n_layer) if i not in drop_set]
    remap = {old: new for new, old in enumerate(keep_layers)}
    print(f'  抜く層 ({len(drop)}個): {drop}')
    print(f'  残る層: {len(keep_layers)} 個')

    # --- 新しいテンソル一覧を作る
    new_tensors = []       # (新しい名前, dims, type, 元のdata_off)
    for name, dims, ttype, off in h.tensors:
        if name.startswith('blk.'):
            il = int(name.split('.')[1])
            if il in drop_set:
                continue
            rest = name.split('.', 2)[2]
            new_tensors.append((f'blk.{remap[il]}.{rest}', dims, ttype, off))
        else:
            new_tensors.append((name, dims, ttype, off))
    print(f'  テンソル {h.n_tensors} → {len(new_tensors)}')

    # --- 新しいヘッダの長さを求める（オフセットを決めるのに要る）
    info = bytearray()
    for name, dims, ttype, _ in new_tensors:
        info += wstr(name)
        info += struct.pack('<I', len(dims))
        info += struct.pack('<%dQ' % len(dims), *dims)
        info += struct.pack('<I', ttype)
        info += struct.pack('<Q', 0)          # あとで埋める
    new_header_end = h.kv_end + len(info)
    new_data_start = (new_header_end + h.align - 1)//h.align*h.align

    # --- data offset を決めて info に書き戻す
    cur = 0
    offs = []
    for name, dims, ttype, _ in new_tensors:
        cur = (cur + h.align - 1)//h.align*h.align
        offs.append(cur)
        cur += nbytes(dims, ttype, name)
    total_new = cur
    total_old = sum(nbytes(t[1], t[2], t[0]) for t in h.tensors)
    print(f'  データ部: {total_old/1e9:.3f} GB → {total_new/1e9:.3f} GB '
          f'（{100*(1-total_new/total_old):.1f}% 減）')
    print(f'  ファイル全体の見込み: {(new_data_start+total_new)/1e9:.3f} GB')
    if a.dry_run:
        return

    # info の offset 欄を埋め直す
    info = bytearray(); 
    for (name, dims, ttype, _), o in zip(new_tensors, offs):
        info += wstr(name)
        info += struct.pack('<I', len(dims))
        info += struct.pack('<%dQ' % len(dims), *dims)
        info += struct.pack('<I', ttype)
        info += struct.pack('<Q', o)
    assert h.kv_end + len(info) == new_header_end, 'ヘッダ長がずれた'

    # --- 書き出し
    f.seek(0); head = bytearray(f.read(h.kv_end))
    struct.pack_into('<Q', head, 8, len(new_tensors))          # n_tensors
    struct.pack_into('<I', head, h.kv_pos[bck][0], len(keep_layers))   # block_count
    out = open(a.dst, 'wb')
    out.write(head); out.write(info)
    pad = new_data_start - new_header_end
    if pad: out.write(b'\x00'*pad)

    CH = 8*1024*1024
    for idx, ((name, dims, ttype, old_off), o) in enumerate(zip(new_tensors, offs)):
        while out.tell() - new_data_start < o:
            out.write(b'\x00'*min(CH, o - (out.tell()-new_data_start)))
        f.seek(h.data_start + old_off)
        left = nbytes(dims, ttype, name)
        while left:
            b = f.read(min(CH, left)); out.write(b); left -= len(b)
        if idx % 100 == 0:
            print(f'  {idx}/{len(new_tensors)}  {out.tell()/1e9:.2f} GB', flush=True)
    out.close(); f.close()
    print(f'できた: {a.dst}  {os.path.getsize(a.dst)/1e9:.3f} GB')

main()
