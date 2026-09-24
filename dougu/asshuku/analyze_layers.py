#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_layers.py — 層ごとの Block Influence を領域間で突き合わせる（実験52）。

  BI[層] = 1 - E_t[cos(h_in, h_out)]   小さいほど「残差にほとんど何も足していない」
  REL[層] = E_t[‖Δ‖/‖h_in‖]

実験48で「領域ごとに要る専門家が違う」と分かった。**層でも同じことが起きるか**を見る。
"""
import argparse, sys
from collections import defaultdict

def load(p):
    d = {}
    for line in open(p, encoding='utf-8'):
        if line.startswith('#') or not line.strip(): continue
        a = line.split('\t')
        d[int(a[0])] = dict(BI=float(a[1]), cos=float(a[2]), rel=float(a[3]),
                            cos_min=float(a[4]), n=int(a[5]))
    return d

def bar(v, lo, hi, w=28):
    if hi <= lo: return ''
    k = int(round(w * (v - lo) / (hi - lo)))
    return '█'*max(0, min(w, k))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--score', nargs='+', required=True, help='領域名=TSV')
    ap.add_argument('--drop-n', type=int, default=6)
    a = ap.parse_args()
    doms, D = [], {}
    for kv in a.score:
        k, v = kv.split('=', 1); doms.append(k); D[k] = load(v)
    layers = sorted(set.intersection(*[set(D[k]) for k in doms]))

    print(f'■ 層ごとの Block Influence（小さいほど抜きやすい）  領域 {doms}\n')
    allv = [D[k][l]['BI'] for k in doms for l in layers]
    lo, hi = min(allv), max(allv)
    hdr = '  層  ' + ''.join(f'{k:>9s}' for k in doms) + '   平均   ' + f'（{lo:.3f}〜{hi:.3f}）'
    print(hdr)
    avg = {}
    for l in layers:
        vs = [D[k][l]['BI'] for k in doms]
        m = sum(vs)/len(vs); avg[l] = m
        print(f'  {l:>2d}  ' + ''.join(f'{v:>9.4f}' for v in vs) + f'  {m:>6.4f}  {bar(m, lo, hi)}')

    print(f'\n■ 領域ごとの「抜きやすい順」上位{a.drop_n}（層0,1と最後の2層は守る前提）')
    n = max(layers)+1
    prot = {0, 1, n-2, n-1}
    tops = {}
    for k in doms:
        c = sorted((D[k][l]['BI'], l) for l in layers if l not in prot)
        tops[k] = [l for _, l in c[:a.drop_n]]
        print(f'   {k:>5s}: {tops[k]}')
    inter = set.intersection(*[set(v) for v in tops.values()])
    union = set.union(*[set(v) for v in tops.values()])
    print(f'   全領域が一致: {sorted(inter)}（{len(inter)}/{a.drop_n}）')
    print(f'   どれかが選ぶ: {sorted(union)}（{len(union)}個）')

    c = sorted((avg[l], l) for l in layers if l not in prot)
    rec = sorted(l for _, l in c[:a.drop_n])
    print(f'\n■ 平均BIで選んだ推奨: {rec}')
    print(f'   その層の平均BI: ' + ', '.join(f'{l}:{avg[l]:.4f}' for l in rec))
    print(f'   守った層の平均BI: ' + ', '.join(f'{l}:{avg[l]:.4f}' for l in sorted(prot)))

    # ★ max-min: 「最悪の領域での BI」が小さい層から抜く（実験48の fair と同じ考え方）
    mx = {l: max(D[k][l]['BI'] for k in doms) for l in layers}
    c2 = sorted((mx[l], l) for l in layers if l not in prot)
    rec2 = sorted(l for _, l in c2[:a.drop_n])
    print(f'\n■ ★max-minで選んだ推奨（最悪の領域でのBIが小さい順）: {rec2}')
    print(f'   最悪BI: ' + ', '.join(f'{l}:{mx[l]:.4f}' for l in rec2))
    print(f'   平均BI版との違い: 平均={sorted(rec)} / maxmin={rec2}'
          f'  重なり {len(set(rec)&set(rec2))}/{a.drop_n}')
    for n_drop in (2, 4, 6, 8, 10, 12):
        r = sorted(l for _, l in c2[:n_drop])
        print(f'   {n_drop:>2d}層抜くなら: {r}   （最悪BIの上限 {max(mx[l] for l in r):.4f}）')

    print(f'\n■ 参考: 層が足す量の相対的な大きさ REL（‖Δ‖/‖h_in‖）')
    r = [(sum(D[k][l]['rel'] for k in doms)/len(doms), l) for l in layers]
    r.sort()
    print('   小さい順: ' + ', '.join(f'{l}:{v:.3f}' for v, l in r[:8]))
    print('   大きい順: ' + ', '.join(f'{l}:{v:.3f}' for v, l in r[-5:]))

main()
