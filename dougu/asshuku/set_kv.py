#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""set_kv.py — GGUF のメタデータの数値を1個だけ書き換える（実験50）。

ヘッダの固定長の数値を上書きするだけなので、データ部もトークナイザも触らない。
`prune_experts.py` と同じ考え方。用途の例:

  # 1トークンに使う専門家の数を 8 → 6 に減らす（読むバイト数が25%減る）
  python3 set_kv.py --in a.gguf --out b.gguf --set qwen3moe.expert_used_count=6

--out を省くと **その場で書き換える**（コピーを作らない。大きいファイル向け）。
"""
import argparse, os, shutil, struct, sys

class Header:
    def __init__(self, f):
        self.f = f
        assert f.read(4) == b'GGUF', 'GGUFではない'
        self.version, = struct.unpack('<I', f.read(4))
        self.n_tensors, = struct.unpack('<Q', f.read(8))
        self.n_kv, = struct.unpack('<Q', f.read(8))
        self.kv = {}                    # key -> (値のオフセット, 型, 現在値)
        for _ in range(self.n_kv):
            k = self._str()
            t, = struct.unpack('<I', f.read(4))
            pos = f.tell()
            v = self._val(t)
            self.kv[k] = (pos, t, v)

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
            for _ in range(n): self._val(et)      # 中身は読み飛ばす
            return f'<配列 {n}件>'
        raise ValueError('未知のKV型 %d' % t)

FMT = {0:'<B',1:'<b',2:'<H',3:'<h',4:'<I',5:'<i',6:'<f',7:'<?',10:'<Q',11:'<q',12:'<d'}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='src', required=True)
    ap.add_argument('--out', dest='dst', default='')
    ap.add_argument('--set', action='append', default=[], help='key=値（数値のみ）')
    ap.add_argument('--show', default='', help='この文字を含むキーを表示して終わる')
    a = ap.parse_args()

    with open(a.src, 'rb') as f:
        h = Header(f)
    if a.show:
        for k, (pos, t, v) in h.kv.items():
            if a.show in k: print(f'  {k:45s} 型{t:<3d} = {v}')
        return
    if not a.set:
        sys.exit('--set か --show が要る')

    dst = a.dst or a.src
    if a.dst:
        print(f'コピー中… {os.path.getsize(a.src)/1e9:.2f} GB')
        shutil.copyfile(a.src, a.dst)
    with open(dst, 'r+b') as f:
        for kv in a.set:
            k, v = kv.split('=', 1)
            if k not in h.kv: sys.exit(f'そのキーは無い: {k}')
            pos, t, old = h.kv[k]
            if t not in FMT: sys.exit(f'{k} は数値ではない（型{t}）')
            new = float(v) if t in (6, 12) else int(v)
            f.seek(pos); f.write(struct.pack(FMT[t], new))
            print(f'  {k}: {old} → {new}')
    print(f'できた: {dst}')

main()
