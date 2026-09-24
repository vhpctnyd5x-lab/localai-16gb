#!/usr/bin/env python3
"""GGUF から指定テンソルを削除する（tied embeddings を復元する用）。
使い方: python3 drop_tensor.py <入力.gguf> <出力.gguf> <削除するテンソル名>
"""
import sys, struct, os

def u32(f): return struct.unpack('<I', f.read(4))[0]
def u64(f): return struct.unpack('<Q', f.read(8))[0]
def rs(f):
    n = u64(f); return f.read(n)

def skip_val(f, t):
    if t in (0, 1, 7): f.read(1)
    elif t in (2, 3): f.read(2)
    elif t in (4, 5, 6): f.read(4)
    elif t in (10, 11, 12): f.read(8)
    elif t == 8: rs(f)
    elif t == 9:
        et = u32(f); n = u64(f)
        for _ in range(n): skip_val(f, et)
    else: raise ValueError(f"unknown kv type {t}")

SRC, DST, DROP = sys.argv[1], sys.argv[2], sys.argv[3].encode()
f = open(SRC, 'rb')
assert f.read(4) == b'GGUF', "not a GGUF file"
ver = u32(f); nt = u64(f); nkv = u64(f)
kv_start = f.tell()
align = 32
for _ in range(nkv):
    k = rs(f); t = u32(f); p0 = f.tell(); skip_val(f, t)
    if k == b'general.alignment':
        cur = f.tell(); f.seek(p0); align = u32(f); f.seek(cur)
kv_end = f.tell()

infos = []
for _ in range(nt):
    name = rs(f); nd = u32(f)
    dims = [u64(f) for _ in range(nd)]
    tt = u32(f); off = u64(f)
    infos.append({'name': name, 'nd': nd, 'dims': dims, 'type': tt, 'off': off})
info_end = f.tell()
data_start = (info_end + align - 1) // align * align
file_size = os.path.getsize(SRC)

# 各テンソルの実データ長を、offset の並びから求める
order = sorted(range(len(infos)), key=lambda i: infos[i]['off'])
for j, i in enumerate(order):
    nxt = infos[order[j + 1]]['off'] if j + 1 < len(order) else (file_size - data_start)
    infos[i]['nbytes'] = nxt - infos[i]['off']

keep = [x for x in infos if x['name'] != DROP]
if len(keep) == len(infos):
    print(f"見つからない: {DROP.decode()}"); sys.exit(1)
dropped = [x for x in infos if x['name'] == DROP][0]
print(f"削除: {dropped['name'].decode()} ({dropped['nbytes']/2**20:.2f} MiB)")

# 新しい offset を、元の並び順のまま詰めて計算
keep_sorted = sorted(keep, key=lambda x: x['off'])
pos = 0
for x in keep_sorted:
    x['newoff'] = pos
    pos += (x['nbytes'] + align - 1) // align * align

out = open(DST, 'wb')
out.write(b'GGUF')
out.write(struct.pack('<I', ver))
out.write(struct.pack('<Q', len(keep)))
out.write(struct.pack('<Q', nkv))
f.seek(kv_start); out.write(f.read(kv_end - kv_start))
for x in keep:                                    # テンソル情報は元の順序で
    out.write(struct.pack('<Q', len(x['name']))); out.write(x['name'])
    out.write(struct.pack('<I', x['nd']))
    for d in x['dims']: out.write(struct.pack('<Q', d))
    out.write(struct.pack('<I', x['type']))
    out.write(struct.pack('<Q', x['newoff']))
here = out.tell()
out.write(b'\x00' * (((here + align - 1) // align * align) - here))
new_data_start = out.tell()
for x in keep_sorted:                             # データは offset 順に
    out.seek(new_data_start + x['newoff'])
    f.seek(data_start + x['off'])
    left = x['nbytes']
    while left > 0:
        b = f.read(min(1 << 24, left))
        if not b: raise IOError("短い読み込み")
        out.write(b); left -= len(b)
    pad = ((x['nbytes'] + align - 1) // align * align) - x['nbytes']
    if pad: out.write(b'\x00' * pad)
out.close(); f.close()
print(f"書き出し: {DST} ({os.path.getsize(DST)/2**20:.1f} MiB, テンソル {len(keep)})")
