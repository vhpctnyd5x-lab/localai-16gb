#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mojiyosou.py -- 一文字ずつ、次に来る字を予想する

  【なぜ作るか】
  いまのカーネルは「あいうえお」という語をまるごと覚え、
  まるごと引いている。表に載っていない言い方は、そこで終わる。
  自由度が無いのは、引く単位が大きすぎるから。

  そこで単位を「一文字」まで下げる。
      「デ」の次は？   → ス（多い）、ジ、ー …
      「デスク」の次は？ → ト
  掛け算はしない。数えた表を引くだけ（字引き）。

  【おまけが本命かもしれない】
  次に来る字の「種類」を数えると、語の切れ目が分かる。
      デ ス ク ト ッ プ | の
      ↑ ここまでは次がほぼ一通り（迷わない）
                      ↑ 「プ」の次は急に何でも来る（迷う）
  迷いが増えた所が切れ目。辞書がいらない。
  これを「分岐の多さ」と呼ぶ。（枝分かれの数）

  カーネルとの関係:
      表に無い言い方 → 切れ目だけは分かる → 語として拾える
      打ち終わる前   → 続きを出せる
      言い間違い     → 近い所へ寄せられる
"""
import json, math, os, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_N = 6          # さかのぼって見る最大の文字数
MIN_HIT = 2        # この回数以上あれば、その長さの文脈を信じる
STORE = os.path.join(HERE, "moji_yosou.json")


def _clean(t):
    t = unicodedata.normalize("NFKC", t)
    return "".join(c for c in t if c not in "\r　")


class Yosou:
    """文字の並びを数えておく表"""

    def __init__(self, max_n=MAX_N):
        self.max_n = max_n
        self.tbl = {}        # 文脈(str) -> {次の字: 回数}
        self.gyaku = {}      # 逆向き。うしろから見た文脈 -> {前の字: 回数}
        self.moji = 0

    # ---- 覚える ----------------------------------------------------
    def oboeru(self, text):
        c = _clean(text)
        self._tsumu(self.tbl, c)
        self._tsumu(self.gyaku, c[::-1])   # 逆向きも同じ手で数える
        self.moji += len(text)

    def _tsumu(self, tbl, c):
        t = "\x02" * self.max_n + c
        for i in range(self.max_n, len(t)):
            nxt = t[i]
            for n in range(1, self.max_n + 1):
                ctx = t[i - n:i]
                d = tbl.get(ctx)
                if d is None:
                    d = tbl[ctx] = {}
                d[nxt] = d.get(nxt, 0) + 1

    # ---- 引く（掛け算なし。長い文脈から順に落ちていくだけ）--------
    def _hiku(self, ctx, tbl=None):
        """使える中で いちばん長い文脈 の表を返す。(表, 使った長さ)"""
        tbl = self.tbl if tbl is None else tbl
        ctx = _clean(ctx)[-self.max_n:]
        for n in range(len(ctx), 0, -1):
            d = tbl.get(ctx[-n:])
            if d and sum(d.values()) >= MIN_HIT:
                return d, n
        return {}, 0

    def tsugi(self, ctx, k=5):
        """次に来そうな字を、多い順に k 個"""
        d, n = self._hiku(ctx)
        out = sorted(d.items(), key=lambda x: -x[1])[:k]
        return [(c, v, n) for c, v in out]

    # ---- 迷いの量（＝分岐の多さ）----------------------------------
    def madoi(self, ctx, tbl=None, kata=None):
        """次に来る字の 迷いの量 を ビット で測る（エントロピー）

        はじめは「種類の数」で測っていたが、材料を 14万字→59万字 に
        増やしたら、どこも種類が増えて、しきい値が合わなくなった。
        数え上げは 量に引きずられる。
        ビットで測れば 量に左右されない。
            1 ビット = 次が 2通りで迷っている
            3 ビット = 次が 8通りで迷っている
        （ここで初めて log を使う。掛け算を解禁したのは、この一点のため）
        """
        if kata is None:
            d, _ = self._hiku(ctx, tbl)
        else:
            # 位置ごとに文脈の長さが違うと、比べものにならない。
            # ここは一度まちがえた。長さを kata 文字に揃える
            tbl = self.tbl if tbl is None else tbl
            c = _clean(ctx)[-kata:]
            d = tbl.get(c) or {}
        if not d:
            return None
        zen = 0
        for v in d.values():
            zen += v
        h = 0.0
        for v in d.values():
            p = v / zen
            h -= p * math.log2(p)
        return h

    _oboe = {}

    def kugiri(self, text, shikii=0.35):
        """語の切れ目で区切る。辞書を使わない。

        考え方（両側から見る）:
          前から:「デスクトッ」の次はほぼ「プ」だけ＝迷わない＝まだ語の中
                 「デスクトップ」の次は何でも来る＝迷う＝ここが終わり
          後ろから: 同じことを逆向きにやると、語の「始まり」が出る
          片側だけだと、先頭で必ず切れてしまう。両側で決める。
        """
        t = _clean(text)
        if len(t) < 3:
            return [t] if t else []
        # 同じ言い方は何度も来る。一度切ったら覚えておく
        oke = (t, shikii)
        if oke in self._oboe:
            return self._oboe[oke]
        n = len(t)
        K = 3                    # 文脈の長さ。ここを揃えるのが肝心
        def h(f, tb):
            v = self.madoi(f, tb, kata=K)
            return v
        mae = [h(t[:i + 1], None) for i in range(n)]
        ato = [h(t[i:][::-1], self.gyaku) for i in range(n)]

        kire = set()
        for i in range(1, n - 1):
            a, b = mae[i], mae[i - 1]
            if a is not None and b is not None and a - b >= shikii:
                kire.add(i + 1)          # 前から見て迷いが増えた＝語の終わり
            a, b = ato[i + 1], ato[i]
            if a is not None and b is not None and a - b >= shikii:
                kire.add(i + 1)          # 後ろから見て増えた＝語の始まり

        out, buf = [], ""
        for i, c in enumerate(t):
            if i in kire and buf:
                out.append(buf); buf = ""
            buf += c
        if buf:
            out.append(buf)
        if len(self._oboe) > 4000:
            self._oboe.clear()
        self._oboe[oke] = out
        return out

    # ---- 続きを書く ------------------------------------------------
    def tsuzuki(self, ctx, n=10):
        s = ""
        for _ in range(n):
            t = self.tsugi(ctx + s, 1)
            if not t:
                break
            s += t[0][0]
        return s

    # ---- しまう / 出す ----------------------------------------------
    def save(self, path=STORE):
        # 1回しか出ていない文脈は捨てる（大きさが 1/5 以下になる）
        slim = {k: v for k, v in self.tbl.items() if sum(v.values()) >= MIN_HIT}
        slim2 = {k: v for k, v in self.gyaku.items() if sum(v.values()) >= MIN_HIT}
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"max_n": self.max_n, "moji": self.moji,
                       "tbl": slim, "gyaku": slim2},
                      f, ensure_ascii=False, separators=(",", ":"))
        return os.path.getsize(path)

    def load(self, path=STORE):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.max_n, self.moji, self.tbl = d["max_n"], d["moji"], d["tbl"]
        self.gyaku = d.get("gyaku", {})
        return self


_Y = None


def yosou():
    """ふだん使うもの。固めた表があれば、そちらを使う（軽い）"""
    global _Y
    if _Y is None:
        if os.path.exists(KATAME) and os.path.exists(KATAME_G):
            try:
                _Y = karui(); return _Y
            except Exception:
                pass
        _Y = Yosou()
        if os.path.exists(STORE):
            try: _Y.load()
            except Exception: pass
    return _Y


# ==================================================================
# 固めた表 -- 8GB の機械に載せるための入れ物
#
#   実測: ディスク 20 MB の表が、メモリでは 308 MB になった（15倍）。
#   中身が重いのではない。Python の辞書 ひとつひとつに付く
#   「入れ物代」が重い。文脈 27万通り × 小さな辞書 27万個。
#
#   材料を 10倍 にすると 3 GB。8GB の機械では、もう載らない。
#   そこで、辞書をやめて 一本の長いバイト列 にする。
#       ・文脈をぜんぶ つなげて 1本にする
#       ・どこから どこまでが どの文脈かを、番地の表で持つ
#       ・引くときは 番地を 二分探索する（速さは ほぼ変わらない）
#   入れ物代が 27万個ぶん まるごと消える。
# ==================================================================
from array import array as _arr


class Katame:
    """辞書をやめて、バイト列ひとつにした表"""

    def __init__(self):
        self.k_blob = b""
        self.k_off = _arr("L")     # 文脈の切れ目（最後に終端を1つ足す）
        self.v_blob = b""
        self.v_off = _arr("L")
        self.max_n = MAX_N

    @classmethod
    def kara_tbl(cls, tbl, max_n=MAX_N):
        """ふつうの辞書を固める"""
        z = cls()
        z.max_n = max_n
        keys = sorted(tbl)
        kb, vb = bytearray(), bytearray()
        for k in keys:
            z.k_off.append(len(kb))
            kb += k.encode("utf-8")
            z.v_off.append(len(vb))
            d = tbl[k]
            for c, v in sorted(d.items(), key=lambda x: -x[1]):
                vb += c.encode("utf-8") + b"\x1f" + str(v).encode() + b"\x1e"
        z.k_off.append(len(kb)); z.v_off.append(len(vb))
        z.k_blob, z.v_blob = bytes(kb), bytes(vb)
        return z

    def __len__(self):
        return len(self.k_off) - 1

    def _sagasu(self, ctx):
        """二分探索。無ければ None"""
        b = ctx.encode("utf-8")
        lo, hi = 0, len(self)
        ko, kb = self.k_off, self.k_blob
        while lo < hi:
            mid = (lo + hi) // 2
            cur = kb[ko[mid]:ko[mid + 1]]
            if cur < b:
                lo = mid + 1
            elif cur > b:
                hi = mid
            else:
                return mid
        return None

    # Yosou の tbl の代わりに、そのまま差し込めるようにする
    def get(self, k, default=None):
        d = self.hiku(k)
        return d if d else default

    def __bool__(self):
        return len(self) > 0

    def hiku(self, ctx):
        i = self._sagasu(ctx)
        if i is None:
            return {}
        out = {}
        for rec in self.v_blob[self.v_off[i]:self.v_off[i + 1]].split(b"\x1e"):
            if not rec:
                continue
            c, _, v = rec.partition(b"\x1f")
            out[c.decode("utf-8")] = int(v)
        return out

    def save(self, path):
        with open(path, "wb") as f:
            f.write(b"KTM1")
            f.write(len(self.k_off).to_bytes(8, "little"))
            f.write(self.max_n.to_bytes(2, "little"))
            for a in (self.k_off, self.v_off):
                b = a.tobytes(); f.write(len(b).to_bytes(8, "little")); f.write(b)
            for b in (self.k_blob, self.v_blob):
                f.write(len(b).to_bytes(8, "little")); f.write(b)
        return os.path.getsize(path)

    def load(self, path):
        with open(path, "rb") as f:
            assert f.read(4) == b"KTM1"
            int.from_bytes(f.read(8), "little")
            self.max_n = int.from_bytes(f.read(2), "little")
            for name in ("k_off", "v_off"):
                n = int.from_bytes(f.read(8), "little")
                a = _arr("L"); a.frombytes(f.read(n)); setattr(self, name, a)
            for name in ("k_blob", "v_blob"):
                n = int.from_bytes(f.read(8), "little")
                setattr(self, name, f.read(n))
        return self


KATAME = os.path.join(HERE, "moji_katame.bin")
KATAME_G = os.path.join(HERE, "moji_katame_gyaku.bin")


def katameru(y=None):
    """いまの表を固めて置く（作るときに一度だけ）"""
    y = y or Yosou().load()
    a = Katame.kara_tbl(y.tbl, y.max_n).save(KATAME)
    b = Katame.kara_tbl(y.gyaku, y.max_n).save(KATAME_G)
    return a, b


def karui():
    """固めた表で動く Yosou。メモリが 22分の1 で済む"""
    y = Yosou()
    y.tbl = Katame().load(KATAME)
    y.gyaku = Katame().load(KATAME_G)
    y.max_n = y.tbl.max_n
    return y
