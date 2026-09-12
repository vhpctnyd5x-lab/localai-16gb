#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eyes.py -- 画面を見て、文字を読む

  やっていること
  ────────────
    ① screencapture で画面を1枚撮る（macOS が最初から持っている）
    ② tools/see（Vision）で、そこに写っている文字を座標つきで読む
    ③ 「押したい文字」を探して、押すべき場所（点）を返す

  ネットには出ない。全部この機械の中で終わる。

  【つまずいたところ】
  Retina の画面では、撮った絵が画面の2倍の大きさになる。
      画面   1792 × 1120
      撮った絵 3584 × 2240
  読み取った座標をそのまま押すと、画面の外を押してしまう。
  だから必ず「絵の大きさ ÷ 画面の大きさ」で割り戻す。
"""
import json, os, subprocess, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
SEE = os.path.join(HERE, "tools", "see")
POINT = os.path.join(HERE, "tools", "point")


def ready():
    return os.path.exists(SEE)


def screen_size():
    """画面（押すときに使う座標）の大きさ"""
    try:
        d = json.loads(subprocess.run([POINT, "screen"], capture_output=True,
                                      text=True, timeout=10).stdout)
        return d["幅"], d["高さ"]
    except Exception:
        return None, None


def shot(path=None, window=None):
    """画面を1枚撮る。

    window にアプリ名を渡すと、その窓だけを撮る（前に出してから撮る）
    """
    path = path or os.path.join(tempfile.gettempdir(),
                                f"kernel-shot-{int(time.time()*1000)}.png")
    if window:
        subprocess.run(["osascript", "-e",
                        f'tell application "{window}" to activate'],
                       capture_output=True, timeout=10)
        time.sleep(0.6)
    # -x は「カシャッ」という音を鳴らさない。人の作業のじゃまをしない
    r = subprocess.run(["screencapture", "-x", "-t", "png", path],
                       capture_output=True, timeout=25)
    if r.returncode != 0 or not os.path.exists(path):
        raise Exception("画面を撮れませんでした。"
                        "システム設定 → プライバシーとセキュリティ → 画面収録 "
                        "で許可が要ります")
    return path


def read(path, fast=False, langs="ja-JP,en-US"):
    """画像の中の文字を読む。座標は「画面の座標」に直して返す"""
    if not ready():
        raise Exception("読み取りの道具がありません（tools/see）")
    argv = [SEE, path, "--lang", langs] + (["--fast"] if fast else [])
    r = subprocess.run(argv, capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        raise Exception((r.stderr or "読めませんでした").strip()[:200])
    d = json.loads(r.stdout)

    # Retina のぶんを割り戻す
    sw, sh = screen_size()
    iw = d["大きさ"]["幅"]
    scale = (iw / sw) if (sw and iw) else 1.0
    if scale and abs(scale - 1.0) > 0.01:
        for it in d["文字"]:
            for k in ("箱", "まんなか"):
                it[k]["x"] = int(it[k]["x"] / scale)
                it[k]["y"] = int(it[k]["y"] / scale)
            if "幅" in it["箱"]:
                it["箱"]["幅"] = int(it["箱"]["幅"] / scale)
                it["箱"]["高さ"] = int(it["箱"]["高さ"] / scale)
    d["倍率"] = round(scale, 2)
    return d


def look(window=None, fast=False, keep=False):
    """撮って、読む。いちばんよく使う入口"""
    p = shot(window=window)
    try:
        return read(p, fast=fast)
    finally:
        if not keep:
            try: os.remove(p)
            except OSError: pass


def find(text, seen=None, window=None, fast=False):
    """画面から、その文字を探す。

    戻り値: [{"文", "まんなか": {"x","y"}, "確からしさ"}] を、近い順に
    """
    d = seen or look(window=window, fast=fast)
    q = text.strip().lower()
    if not q:
        return []
    exact, part = [], []
    for it in d["文字"]:
        s = it["文"].strip().lower()
        if s == q:
            exact.append(it)
        elif q in s or s in q:
            part.append(it)
    # ぴったり一致 → 部分一致。同じ中では、確からしさの高い順
    exact.sort(key=lambda x: -x["確からしさ"])
    part.sort(key=lambda x: -x["確からしさ"])
    return exact + part


def text_of(window=None, fast=False):
    """画面に出ている文字を、まるごと1つの文字列で"""
    return look(window=window, fast=fast)["全文"]


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        hits = find(" ".join(sys.argv[1:]))
        if not hits:
            print("  見つかりませんでした")
        for h in hits[:10]:
            c = h["まんなか"]
            print(f"  ({c['x']:>5},{c['y']:>5}) {h['確からしさ']:.2f}  {h['文'][:50]}")
    else:
        d = look()
        print(f"  画面 {screen_size()} ／ 撮った絵 "
              f"{d['大きさ']['幅']}×{d['大きさ']['高さ']} ／ 倍率 {d['倍率']}")
        print(f"  読めた文字: {len(d['文字'])} 個\n")
        for it in d["文字"][:20]:
            c = it["まんなか"]
            print(f"  ({c['x']:>5},{c['y']:>5}) {it['文'][:56]}")
