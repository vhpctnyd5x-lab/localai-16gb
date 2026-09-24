#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shiryo.py -- 資料しらべ。知らないことを、外の資料で埋める

  【順番（安いものから。外に出るのは最後）】
      1. 手元の辞書        10万語。外に出ない。ほぼ 0 秒
      2. 集めた記事        moji_shuu で取ってある本文。外に出ない
      3. Wikipedia         外に出る。名乗りを付け、間をあける
      4. NVIDIA の API     鍵があるときだけ。いちばん高い

  【一度きりの決まり】
  同じことを二度 外に聞かない。答えは必ず控えに書き、
  次からは控えから出す。外に出た回数も数える。

  【札にするときは pc_kind に相談する】
  説明文に「資料」の2字があるだけで 醤油→PDF のような札が
  できていた。種類の札は、必ず pc_kind に一度 聞く。
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
HIKAE = os.path.join(HERE, "shiryo_hikae.json")


def _hikae():
    if os.path.exists(HIKAE):
        try:
            return json.load(open(HIKAE, encoding="utf-8"))
        except Exception:
            pass
    return {"控え": {}, "外に出た回数": 0}


def _save(d):
    json.dump(d, open(HIKAE, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))


# ---- それぞれの出どころ -------------------------------------------
def _temoto(w):
    try:
        import lookup
        r = lookup.answer(w, max_lines=3)
        return r if r and r.strip() else None
    except Exception:
        return None


def _atsumeta(w):
    """自分で集めた記事の中を探す。外に出ない"""
    try:
        import moji_shuu
        for t in moji_shuu.yomu():
            i = t.find(w)
            if i >= 0:
                a = max(0, i - 40)
                return t[a:i + 160].replace("\n", " ").strip()
    except Exception:
        pass
    return None


def _wiki(w):
    try:
        import wiki
        r = wiki.ask(w, chars=400)
        if isinstance(r, dict):
            r = r.get("本文") or r.get("さわり")
        return r if r and str(r).strip() else None
    except Exception:
        return None


def _nvidia(q):
    try:
        import nvidia
        if not nvidia.key():
            return None            # 鍵が無いなら、はじめから呼ばない
        return nvidia.ask(q, timeout=60)
    except Exception:
        return None


DEDOKORO = [("手元の辞書", _temoto, False),
            ("集めた記事", _atsumeta, False),
            ("Wikipedia", _wiki, True),
            ("NVIDIA", _nvidia, True)]


def shiraberu(what, soto=True, verbose=False):
    """安い順に当たる。soto=False なら外に一切出ない"""
    d = _hikae()
    if what in d["控え"]:
        r = dict(d["控え"][what]); r["控えから"] = True
        return r

    t0 = time.time()
    for namae, f, deru in DEDOKORO:
        if deru and not soto:
            continue
        try:
            got = f(what)
        except Exception:
            got = None
        if verbose:
            print(f"    {namae}: {'当たり' if got else 'なし'}")
        if got:
            r = {"答え": str(got).strip()[:600], "出どころ": namae,
                 "ミリ秒": round((time.time() - t0) * 1000),
                 "控えから": False}
            d["控え"][what] = {k: v for k, v in r.items() if k != "控えから"}
            if deru:
                d["外に出た回数"] += 1
            _save(d)
            return r
    return {"答え": None, "出どころ": None,
            "ミリ秒": round((time.time() - t0) * 1000), "控えから": False}


def fuda_ni_suru(w, kind):
    """調べた語を「種類」の札にしてよいか。pc_kind に相談する"""
    try:
        import pc_kind
        if not pc_kind.ready():
            return False, "pc_kind がまだ用意できていません"
        g = pc_kind.guess(w)
        if not g or g[0] is None:
            return False, "pc_kind が黙りました（当てずっぽうになる）"
        if g[0] != kind:
            return False, f"pc_kind は「{g[0]}」だと言っています"
        return True, f"pc_kind も「{kind}」（近さ {g[1]:.2f}）"
    except Exception as e:
        return False, str(e)


def joukyou():
    d = _hikae()
    return (f"控え {len(d['控え']):,} 件 ／ 外に出た回数 {d['外に出た回数']:,}\n"
            f"  出どころの順: " + " → ".join(n for n, _, _ in DEDOKORO))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        r = shiraberu(" ".join(sys.argv[1:]), verbose=True)
        print(f"\n  出どころ: {r['出どころ']} ／ {r['ミリ秒']} ミリ秒"
              f"{'（控えから）' if r['控えから'] else ''}")
        print(f"  {r['答え']}")
    else:
        print(joukyou())
