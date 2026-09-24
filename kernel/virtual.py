#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
virtual.py -- 実行する前に、頭の中でフォルダを動かしてみる

  ────────────────────────────────────────────────
  なぜ作ったか
  ────────────────────────────────────────────────
  これまでの「下見」は、動くファイルの名前をならべるだけだった。
  ひな形（テンプレート）の文章を出しているのと変わらず、
  肝心の2つが見えていなかった。

    ① 実行したあと、フォルダがどんな姿になるのか
    ② 行き先に同じ名前のファイルがすでにあるかどうか
       （shutil.move は黙って上書きする。②は本物の事故になる）

  ────────────────────────────────────────────────
  やること
  ────────────────────────────────────────────────
  本物のフォルダの「名前と大きさの一覧」だけをメモリに写す。
  ファイルの中身は読まない。コピーもしない。作りもしない。

      写す  … listdir と stat だけ。1件あたり数マイクロ秒
      動かす… メモリの中の辞書を書き換えるだけ
      比べる… 前と後ろを突き合わせて、変わったところを出す

  そのうえで、名前がぶつかるものを見つけたら、実行を止める。
"""
import os


def snapshot(dirs):
    """フォルダの中身を、名前と大きさだけメモリに写す。

    中身は読まない。コピーもしない。ここが「仮想」の意味
    """
    out = {}
    for d in dirs:
        if not d or d in out or not os.path.isdir(d):
            continue
        items = {}
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.name.startswith("._"):
                        continue          # macOS が勝手に作る影のファイル
                    try:
                        items[e.name] = {"大きさ": e.stat().st_size,
                                         "フォルダ": e.is_dir()}
                    except OSError:
                        items[e.name] = {"大きさ": 0, "フォルダ": False}
        except OSError:
            continue
        out[d] = items
    return out


def simulate(pv, plan, slots):
    """下見の結果をもとに、頭の中で動かして、前と後ろを出す。

    戻り値:
      {"前": {フォルダ: [名前…]}, "後": {フォルダ: [名前…]},
       "移す": [(元, 先)…], "ぶつかる": [(元, 先)…],
       "作る": [パス…], "止める理由": [文…]}
    """
    pairs = list(pv.get("pairs") or [])
    created = [p for p in (pv.get("created"), pv.get("dest")) if p]

    # 関わるフォルダを集める。元・先・その親
    dirs = set()
    for a, b in pairs:
        dirs.add(os.path.dirname(a))
        dirs.add(os.path.dirname(b))
    for f in (pv.get("files") or []):
        dirs.add(os.path.dirname(f))
    if pv.get("src"):
        dirs.add(pv["src"])
    if pv.get("dest"):
        dirs.add(pv["dest"])

    before = snapshot(dirs)
    after = {d: dict(v) for d, v in before.items()}
    for d in dirs:
        after.setdefault(d, {})

    clash, moves = [], []
    for a, b in pairs:
        da, na = os.path.dirname(a), os.path.basename(a)
        db, nb = os.path.dirname(b), os.path.basename(b)
        info = before.get(da, {}).get(na) or {"大きさ": 0, "フォルダ": False}
        # 行き先に同じ名前のものがすでにあるか。
        # あるのに黙って動かすと、上書きで消える
        if nb in after.get(db, {}) and os.path.abspath(a) != os.path.abspath(b):
            clash.append((a, b))
        after.setdefault(da, {}).pop(na, None)
        after.setdefault(db, {})[nb] = info
        moves.append((a, b))

    # 新しくできるフォルダ
    make = []
    for c in created:
        parent, name = os.path.dirname(c), os.path.basename(c)
        if name and name not in before.get(parent, {}):
            make.append(c)
            after.setdefault(parent, {})[name] = {"大きさ": 0, "フォルダ": True}
            after.setdefault(c, {})

    stop = []
    if clash:
        stop.append(f"行き先に同じ名前のものが {len(clash)} 件あります。"
                    "このまま動かすと上書きで消えます")

    return {
        "前": {d: sorted(v) for d, v in before.items()},
        "後": {d: sorted(v) for d, v in after.items()},
        "移す": moves, "ぶつかる": clash, "作る": make,
        "止める理由": stop,
    }


def report(sim, limit=10):
    """人が読める形にする"""
    out = []
    for a, b in sim["移す"][:limit]:
        out.append(f"{os.path.basename(a)}  →  "
                   f"{os.path.basename(os.path.dirname(b))}/"
                   f"{os.path.basename(b)}")
    if len(sim["移す"]) > limit:
        out.append(f"…ほか {len(sim['移す']) - limit} 件")
    for c in sim["作る"]:
        out.append(f"（新しく作る） {os.path.basename(c)}/")
    if not sim["移す"] and not sim["作る"]:
        out.append("動くものはありません")

    for a, b in sim["ぶつかる"][:limit]:
        out.append(f"⚠ 名前がぶつかる： {os.path.basename(b)} は"
                   f" {os.path.basename(os.path.dirname(b))}/ にもうあります")

    # 実行前と実行後の姿
    changed = [d for d in sim["後"] if sim["後"][d] != sim["前"].get(d, [])]
    for d in sorted(changed)[:4]:
        b0 = sim["前"].get(d, [])
        a0 = sim["後"][d]
        out.append(f"{os.path.basename(d) or d}/ : {len(b0)} 件 → {len(a0)} 件")
        gone = [x for x in b0 if x not in a0]
        new = [x for x in a0 if x not in b0]
        if gone:
            out.append("    出ていく: " + "、".join(gone[:6])
                       + (f" …ほか{len(gone)-6}" if len(gone) > 6 else ""))
        if new:
            out.append("    入ってくる: " + "、".join(new[:6])
                       + (f" …ほか{len(new)-6}" if len(new) > 6 else ""))
    return out
