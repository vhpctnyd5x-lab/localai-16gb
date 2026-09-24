#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hdv.py -- 超高次元ベクトル（掛け算を1回も使わない「意味」の表し方）

  Kanerva の Binary Spatter Codes（1990年代）という古い方法。
  いま「Hyperdimensional Computing / VSA」と呼ばれている。

  ────────────────────────────────────────────────
  考え方はひとつだけ。
  「意味は、1万個の 0か1 の並びで表せる」
  ────────────────────────────────────────────────

  ふつうのAIは、意味を「小数の並び」で表す。
      写真 = [0.13, -0.55, 0.91, ...]  ← 4096個の小数
  似ているかを測るには、4096回の掛け算が要る。

  ここでは、意味を「0か1の並び」で表す。
      写真 = 1011001110...             ← 10000個のビット
  似ているかは「違うビットが何個あるか」で測る。
  → XOR して、1の数を数えるだけ。掛け算は0回。

  なぜ1万ビットも要るのか
  ──────────────────────
  でたらめに作った1万ビットの並びを2つ用意すると、
  必ず「だいたい半分（5000個）」が違う。ほとんどブレない。
  だから「4000個しか違わない」なら、それは偶然ではなく
  「意味が近い」と言い切れる。次元が高いほど、この判定が鋭くなる。
  これを Kanerva は「高次元空間のふしぎ」と呼んだ。

  3つの道具だけで組み立てる
  ──────────────────────
    たばねる(bundle) … 多数決。「AとBの両方っぽいもの」を作る
    むすぶ(bind)     … XOR。「AをBという役で使う」を作る
    ずらす(permute)  … ビットを回す。「順番」を表す

  どれも掛け算を使わない。足し算・XOR・ビットの巡回だけ。
"""
import hashlib, json, os, random

DIM = 10000                      # ビット数。1万あれば偶然の一致はまず起きない
_MASK = (1 << DIM) - 1

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------
# 基本のベクトル
# ------------------------------------------------------------------
def atom(word):
    """語ひとつぶんの、でたらめな1万ビット。

    語の名前から作るので、保存しなくても毎回同じものが出てくる。
    （1万ビット × 10万語 = 125MB を持たずに済む）
    """
    h = hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest()
    rng = random.Random(int.from_bytes(h, "big"))
    return rng.getrandbits(DIM)


def hamming(a, b):
    """違うビットの数。これが「遠さ」

    XOR して 1 を数えるだけ。int.bit_count() は Python が用意している
    """
    return (a ^ b).bit_count()


def near(a, b):
    """近さ。0.0〜1.0（1.0 で完全一致、0.5 で無関係）"""
    return 1.0 - hamming(a, b) / DIM


def bind(a, b):
    """むすぶ : XOR。

    「AをBという役で使う」を表す。
    もう一度同じもので XOR すると元に戻る（ほどける）のが大事な性質
    """
    return a ^ b


def permute(v, n=1):
    """ずらす : ビットを n だけ巡回させる。順番や入れ子を表す"""
    n %= DIM
    return ((v << n) | (v >> (DIM - n))) & _MASK


def bundle(vectors, weights=None):
    """たばねる : 多数決。

    それぞれのビットについて「1が多数か」を数え、多いほうを採る。
    足し算と比較だけ。掛け算は使わない。
    """
    vs = list(vectors)
    if not vs:
        return 0
    if len(vs) == 1:
        return vs[0]
    ws = list(weights) if weights else [1] * len(vs)

    # ビットごとの「1の数」を数える。バイト単位で処理して速くする
    counts = [0] * DIM
    for v, w in zip(vs, ws):
        b = v
        i = 0
        while b:
            if b & 1:
                counts[i] += w
            b >>= 1
            i += 1
    half = sum(ws) / 2
    out = 0
    for i in range(DIM - 1, -1, -1):
        out = (out << 1) | (1 if counts[i] > half else 0)
    return out


def bundle_bits(vectors, weights=None):
    """たばねる（ビット並列版）。1万個ぜんぶを同時に数える。

    1ビットずつ回していたら、37,903語で2分たっても終わらなかった。
    ここでは「桁上げ加算器」の考え方を使う。

      数えた回数を、2進法の「桁」ごとに1本の1万ビットとして持つ。
        面0 = 1の位, 面1 = 2の位, 面2 = 4の位 …
      1本足すときは、XOR で桁の中身、AND で桁上げ。
      これを桁が繰り上がらなくなるまで送る。

    1万個ぜんぶが、1回の XOR で同時に処理される。
    掛け算は使わない。使うのは XOR・AND・OR・NOT だけ。
    """
    vs = list(vectors)
    if not vs:
        return 0
    if len(vs) == 1:
        return vs[0]
    ws = list(weights) if weights else [1] * len(vs)

    planes = []                      # planes[i] = 2^i の位
    total = 0
    for v, w in zip(vs, ws):
        for _ in range(w):           # 重みは「その回数だけ足す」
            carry = v
            i = 0
            while carry:
                if i == len(planes):
                    planes.append(0)
                new_carry = planes[i] & carry
                planes[i] ^= carry
                carry = new_carry
                i += 1
            total += 1

    # 「数えた回数 > 半分」を、1万個ぜんぶ同時に判定する
    T = total // 2
    gt = 0                           # すでに超えていると分かったビット
    eq = _MASK                       # まだ同じ値のビット
    for i in range(len(planes) - 1, -1, -1):
        p = planes[i]
        if (T >> i) & 1:
            eq &= p                  # T側が1。同じでいられるのは p=1 のときだけ
        else:
            gt |= eq & p             # T側が0で、こちらが1 → 超えた
            eq &= ~p & _MASK
    return gt


def bundle_fast(vectors, weights=None):
    """たばねる（速い版）

    1ビットずつ回すと遅いので、バイトの表を先に作っておいて、
    8ビットまとめて数える。やっていることは同じ多数決。
    """
    vs = list(vectors)
    if not vs:
        return 0
    if len(vs) == 1:
        return vs[0]
    ws = list(weights) if weights else [1] * len(vs)
    nbytes = (DIM + 7) // 8
    counts = [0] * (nbytes * 8)
    for v, w in zip(vs, ws):
        bs = v.to_bytes(nbytes, "little")
        base = 0
        for byte in bs:
            if byte:
                for bit in _BITS[byte]:
                    counts[base + bit] += w
            base += 8
    half = sum(ws) / 2
    out = bytearray(nbytes)
    for i, c in enumerate(counts[:DIM]):
        if c > half:
            out[i >> 3] |= 1 << (i & 7)
    return int.from_bytes(bytes(out), "little")


# 0〜255 の各バイトで、立っているビットの位置
_BITS = [[i for i in range(8) if b >> i & 1] for b in range(256)]


# ------------------------------------------------------------------
# 語の「意味」を作る
# ------------------------------------------------------------------
# 速い方を既定にする
bundle_fast = bundle_bits


class Space:
    """語 → 意味ベクトル の置き場

    意味ベクトルは、その語の説明に出てくる語をたばねて作る。
    「スナップ＝写真をとること」なら、スナップの意味は
    「写真」「とる」あたりをたばねたもの、ということ。
    """

    def __init__(self):
        self.mem = {}                 # 語 → 意味ベクトル

    def learn(self, word, context, weight_head=3):
        """語ひとつを覚える。

        context は、その語の説明に出てきた語のならび。
        見出しの語そのものも、少し重くして混ぜる
        （説明が薄い語が、まったくの無意味にならないように）
        """
        vs = [atom(word)]
        ws = [weight_head]
        for w in context:
            if w and w != word:
                vs.append(atom(w))
                ws.append(1)
        self.mem[word] = bundle_fast(vs, ws)
        return self.mem[word]

    def get(self, word):
        """覚えていればその意味、なければ語そのもののベクトル"""
        return self.mem.get(word) or atom(word)

    def nearest(self, word, candidates):
        """候補の中から、いちばん近いものを選ぶ。

        戻り値: (いちばん近いもの, 近さ, 2番手との差)
        """
        v = self.get(word)
        scored = sorted(((near(v, self.get(c)), c) for c in candidates),
                        reverse=True)
        if not scored:
            return None, 0.0, 0.0
        best_s, best = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.5
        return best, best_s, best_s - second

    # --- 保存と読み込み ---
    def save(self, path):
        nbytes = (DIM + 7) // 8
        with open(path, "wb") as f:
            words = list(self.mem)
            head = json.dumps({"次元": DIM, "語": words},
                              ensure_ascii=False).encode("utf-8")
            f.write(len(head).to_bytes(4, "little"))
            f.write(head)
            for w in words:
                f.write(self.mem[w].to_bytes(nbytes, "little"))

    def load(self, path):
        nbytes = (DIM + 7) // 8
        with open(path, "rb") as f:
            n = int.from_bytes(f.read(4), "little")
            head = json.loads(f.read(n).decode("utf-8"))
            for w in head["語"]:
                self.mem[w] = int.from_bytes(f.read(nbytes), "little")
        return self


if __name__ == "__main__":
    import time
    print(f"次元: {DIM} ビット\n")

    print("■ でたらめな2つは、どれくらい違うか")
    for pair in [("りんご", "みかん"), ("あ", "い"), ("東京", "大阪")]:
        d = hamming(atom(pair[0]), atom(pair[1]))
        print(f"  {pair[0]} と {pair[1]}: {d} ビット違う（近さ {1-d/DIM:.3f}）")
    print("  → いつも「だいたい半分」。だから 0.5 から離れたら意味がある\n")

    print("■ たばねると、材料に近くなる")
    a, b, c = atom("写真"), atom("画像"), atom("カメラ")
    m = bundle_fast([a, b, c])
    print(f"  たばねたもの と 写真  : {near(m, a):.3f}")
    print(f"  たばねたもの と カメラ: {near(m, c):.3f}")
    print(f"  たばねたもの と 味噌汁: {near(m, atom('味噌汁')):.3f}\n")

    print("■ むすぶと、ほどける（XORの性質）")
    role, filler = atom("場所"), atom("東京")
    bound = bind(role, filler)
    print(f"  結んだもの と 東京        : {near(bound, filler):.3f}（無関係に見える）")
    print(f"  結んだものを場所でほどく  : {near(bind(bound, role), filler):.3f}（戻った）\n")

    t0 = time.time()
    for _ in range(1000):
        hamming(a, b)
    print(f"■ 速さ: 近さを1回測るのに {(time.time()-t0):.3f} ミリ秒")
    print("  掛け算の回数: 0")
