"""コード番号列をさらに縮める（＝「右クリックで圧縮」を専用設計にしたもの）。

積量子化の出力は「コード番号の列」。この番号は均等に使われていないので、
よく出る番号に短いビットを割り当てれば、名目ビット数より小さくできる。
さらに隣の番号との相関を使えばもっと縮む。
"""
import heapq
import subprocess
import numpy as np


def entropy(counts):
    """理想的なエントロピー符号化での平均ビット数（下限）。"""
    c = np.asarray(counts, np.float64)
    c = c[c > 0]
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def huffman_bits(idx, ncode):
    """実際のハフマン符号での平均ビット数（整数長の制約つき＝現実の値）。"""
    counts = np.bincount(idx, minlength=ncode)
    nz = [(int(c), i) for i, c in enumerate(counts) if c > 0]
    if len(nz) == 1:
        return 1.0
    # マージ1回ごとに、その部分木に属する全要素の符号長が1増える。
    # よってマージ重みの総和 = 総ビット数。
    heap = [(c, i) for c, i in nz]
    heapq.heapify(heap)
    total = 0
    while len(heap) > 1:
        a = heapq.heappop(heap)
        b = heapq.heappop(heap)
        m = a[0] + b[0]
        total += m                         # マージ1回ごとに深さ+1が全要素に効く
        heapq.heappush(heap, (m, -1))
    return total / counts.sum()


# ★ 2026-09-07 の注記: この関数は idx を1本の列とみなして隣どうしの遷移を数える。
#   グループ（テンソルや行）を並べて渡すと、**あるグループの最後と次の先頭**を
#   つながっているものとして数えてしまう。グループ数が多いほど薄まるが、
#   短いグループを大量に渡すときは 別々に呼ぶこと。
def conditional_entropy(idx, ncode):
    """直前のコードで条件づけたエントロピー（文脈モデル＝専用圧縮器の肝）。"""
    a = idx[:-1].astype(np.int64)
    b = idx[1:].astype(np.int64)
    # ★ 2026-09-07 追加: ncode が大きいと ncode×ncode の表がメモリを食い尽くす。
    #   ncode=2**16 なら 42.9億要素＝数十GB。黙って落ちる前に断る。
    if ncode > 4096:
        raise ValueError(
            "ncode=%d は大きすぎます（%d×%d の表を作ろうとしています）。"
            "疎な数え方に替えるか、ncode を下げてください。" % (ncode, ncode, ncode))
    joint = np.bincount(a * ncode + b, minlength=ncode * ncode).reshape(ncode, ncode)
    tot = joint.sum()
    if tot == 0:
        return 0.0
    row = joint.sum(1)
    h = 0.0
    for i in range(ncode):
        if row[i] == 0:
            continue
        h += (row[i] / tot) * entropy(joint[i])
    return float(h)


def generic_compress(idx, ncode, tool):
    """汎用圧縮器（xz / zstd）に素のバイト列を食わせた場合の実測ビット数。"""
    bits = max(1, int(np.ceil(np.log2(ncode))))
    if bits <= 8:
        raw = idx.astype(np.uint8).tobytes()
    else:
        raw = idx.astype(np.uint16).tobytes()
    try:
        cmd = {"xz": ["xz", "-9e", "-c"], "zstd": ["zstd", "-19", "-c", "-q"]}[tool]
        out = subprocess.run(cmd, input=raw, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=600).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return len(out) * 8 / len(idx)


def analyze(idx, ncode, k, G, tools=("xz",)):
    """コード列1本を多角的に評価し、1重みあたりビット数に換算して返す。"""
    counts = np.bincount(idx, minlength=ncode)
    nominal = np.log2(ncode)
    res = {
        "名目": nominal / k,
        "エントロピー下限": entropy(counts) / k,
        "ハフマン": huffman_bits(idx, ncode) / k,
        "文脈つき下限": conditional_entropy(idx, ncode) / k,
    }
    for t in tools:
        v = generic_compress(idx, ncode, t)
        if v is not None:
            res[f"汎用{t}"] = v / k
    scale_bits = 16 / G
    return {kk: vv + scale_bits for kk, vv in res.items()}, counts
