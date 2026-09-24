#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_scores.py — 領域別の採点を合成して「何を残すか」を決める（実験48）。

採点値 S[層][専門家] = Σ_t g_norm × ‖down‖₂ は**トークンについての和**なので、
領域別に採って足すことは「混ぜた較正文で1回採る」ことと等価。
だから領域別に採る方が情報が多い（混合も和集合も、あとから作れる）。

  方式:
    sum   素直な和。=混合較正そのもの。活性の大きい領域が強く出る。
    norm  層ごとに領域内で正規化してから和。どの領域も同じ発言力を持つ。
    union 領域ごとの順位を総当たりで交互に拾う。順位だけ見る。
    fair  ★いま一番飢えている領域に次の1個を選ばせる（max-min 公平）。
          「残せた経路重みの割合」が領域間でそろうように詰める。大きさも見る。

出力は prune_experts.py がそのまま読める TSV。score 列に順位を反転した値を入れるので、
--keep N がここで決めた集合をそのまま再現する。

  python3 merge_scores.py --score ja=A.tsv code=B.tsv en=C.tsv --report --simulate --keep 96
  python3 merge_scores.py --score ja=A.tsv code=B.tsv en=C.tsv --mode fair --out fair.tsv
"""
import argparse
from collections import defaultdict

def load(spec):
    """TSV -> {層: {専門家: score}}。 'A.tsv+B.tsv' と書くと足し合わせる
       （採点はトークンについての和なので、足すことは較正文をつなぐことと同じ）。"""
    d = defaultdict(lambda: defaultdict(float))
    for path in spec.split('+'):
        for line in open(path, encoding='utf-8'):
            if line.startswith('#') or not line.strip():
                continue
            p = line.split('\t')
            d[int(p[0])][int(p[1])] += float(p[2])
    return {l: dict(v) for l, v in d.items()}

def order_for(mode, l, doms, D, W, n_exp):
    """その層の専門家を「残したい順」に並べて返す。keep 個なら先頭 keep 個。"""
    S = {k: D[k][l] for k in doms}
    tot = {k: max(1e-9, sum(S[k].values())) for k in doms}

    if mode.startswith('only:'):
        k = mode[5:]
        return sorted(range(n_exp), key=lambda e: -S[k].get(e, 0.0))

    if mode in ('sum', 'norm'):
        def val(e):
            return sum(W[k] * (S[k].get(e, 0.0) / (tot[k] if mode == 'norm' else 1.0))
                       for k in doms)
        return sorted(range(n_exp), key=lambda e: -val(e))

    if mode == 'union':                       # 順位を総当たりで交互に拾う
        rank = {k: sorted(range(n_exp), key=lambda e: -S[k].get(e, 0.0)) for k in doms}
        reps = {k: max(1, int(round(W[k]))) for k in doms}
        seq, taken, pos = [], set(), {k: 0 for k in doms}
        while len(seq) < n_exp:
            for k in doms:
                for _ in range(reps[k]):
                    while pos[k] < n_exp and rank[k][pos[k]] in taken:
                        pos[k] += 1
                    if pos[k] < n_exp:
                        e = rank[k][pos[k]]; taken.add(e); seq.append(e); pos[k] += 1
                    if len(seq) >= n_exp: break
                if len(seq) >= n_exp: break
        return seq

    if mode == 'fair':                        # 一番飢えている領域に選ばせる
        # ★ 注意: fair で --weights を使ってはいけない（実験48で確認）。
        #   飢え度が got/tot/W なので、W=2 にすると「その領域が他の2倍の割合を持つまで」
        #   独占し続ける。飽和するまで止まらないので、実質「その領域だけで採点」になる。
        #   ja=2 で ja 99.13% / code 86.23% となり、ja単独（85.25%）とほぼ同じ壊れ方をする。
        #   **重みを振りたいときは mode=norm を使うこと。**あちらは線形に効く。
        got = {k: 0.0 for k in doms}
        left, seq = set(range(n_exp)), []
        while left:
            k = min(doms, key=lambda k: got[k] / tot[k] / W[k])
            e = max(left, key=lambda e: S[k].get(e, 0.0))
            left.discard(e); seq.append(e)
            for k2 in doms:
                got[k2] += S[k2].get(e, 0.0)
        return seq

    raise ValueError(mode)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--score', nargs='+', required=True, help="領域名=TSV（'A.tsv+B.tsv' で足せる）")
    ap.add_argument('--mode', default='fair', choices=['sum', 'norm', 'union', 'fair'])
    ap.add_argument('--weights', default='', help='ja=2,code=1,en=1（norm と一緒に使うこと）')
    ap.add_argument('--keep', type=int, default=96)
    ap.add_argument('--out', default='')
    ap.add_argument('--report', action='store_true', help='領域どうしの食い違いを見る')
    ap.add_argument('--simulate', action='store_true', help='削る前に各方式の残存経路重みを見積る')
    a = ap.parse_args()

    doms, D = [], {}
    for kv in a.score:
        k, v = kv.split('=', 1); doms.append(k); D[k] = load(v)
    W = {k: 1.0 for k in doms}
    for kv in filter(None, a.weights.split(',')):
        k, v = kv.split('='); W[k] = float(v)
    layers = sorted(set.intersection(*[set(D[k]) for k in doms]))
    n_exp = max(max(D[k][l]) for k in doms for l in layers) + 1
    for k in doms:                                     # 欠けている専門家は 0 で埋める
        for l in layers:
            for e in range(n_exp):
                D[k][l].setdefault(e, 0.0)

    if a.report:
        print(f'領域 {doms} / 層 {len(layers)} / 専門家 {n_exp} / 上位 {a.keep} で比較\n')
        top = {k: {l: set(order_for('only:' + k, l, doms, D, W, n_exp)[:a.keep])
                   for l in layers} for k in doms}
        print('■ 領域どうしの上位集合の重なり（層平均。1.00 なら完全一致）')
        for i in range(len(doms)):
            for j in range(i + 1, len(doms)):
                x, y = doms[i], doms[j]
                ov = [len(top[x][l] & top[y][l]) / a.keep for l in layers]
                lo = ov.index(min(ov))
                print(f'   {x:>4s} ∩ {y:<4s}  平均 {sum(ov)/len(ov):.3f}  '
                      f'（最小 {min(ov):.3f} = 層{layers[lo]} / 最大 {max(ov):.3f}）')
        allt = [len(set.intersection(*[top[k][l] for k in doms])) for l in layers]
        anyt = [len(set.union(*[top[k][l] for k in doms])) for l in layers]
        print(f'\n■ 全領域が上位に入れる専門家     平均 {sum(allt)/len(allt):.1f} 個 / {a.keep}')
        print(f'■ どれか1領域でも上位に入る数     平均 {sum(anyt)/len(anyt):.1f} 個 / {n_exp}')
        print(f'   → {a.keep} 個しか残せないので 平均 {sum(anyt)/len(anyt)-a.keep:+.1f} 個ぶん溢れる')
        if 'ja' in doms:
            print()
            for k in doms:
                if k == 'ja': continue
                lost = [len(top[k][l] - top['ja'][l]) for l in layers]
                w = [sum(D[k][l][e] for e in top[k][l] - top['ja'][l])
                     / max(1e-9, sum(D[k][l].values())) for l in layers]
                print(f'■ ja の上位{a.keep}から漏れた {k} の上位{a.keep}: '
                      f'平均 {sum(lost)/len(lost):.1f} 個 / '
                      f'{k} の経路重みの {100*sum(w)/len(w):.2f}% を失う')
        print()

    if a.simulate:
        print(f'■ 残す数 {a.keep} での見積り — 各領域の経路重みが何%残るか（層平均 / 最悪の層）\n')
        print(f'   {"方式":<10s}' + ''.join(f'{k:>20s}' for k in doms))
        for mode in ['sum', 'norm', 'union', 'fair'] + ['only:' + k for k in doms]:
            row = {k: [] for k in doms}
            for l in layers:
                ks = set(order_for(mode, l, doms, D, W, n_exp)[:a.keep])
                for k in doms:
                    tot = max(1e-9, sum(D[k][l].values()))
                    row[k].append(sum(D[k][l][e] for e in ks) / tot)
            print(f'   {mode:<10s}' + ''.join(
                f'{100*sum(row[k])/len(row[k]):>12.2f}% /{100*min(row[k]):>5.1f}%' for k in doms))
        print()

    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            f.write(f'# merge_scores mode={a.mode} doms={",".join(doms)} '
                    f'weights={",".join(f"{k}={W[k]:g}" for k in doms)}\n')
            f.write('# layer\texpert\tscore\thits\tmean\n')
            for l in layers:
                seq = order_for(a.mode, l, doms, D, W, n_exp)
                for i, e in enumerate(seq):
                    f.write(f'{l}\t{e}\t{float(n_exp-i):.6f}\t0\t0.000000\n')
        print(f'書いた: {a.out}  ({len(layers)}層 × {n_exp}専門家 / mode={a.mode})')

main()
