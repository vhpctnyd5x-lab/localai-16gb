#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
feedback.py -- 気づいたことを、その場で書いて残す（虫マーク）

  「おかしい」と思ったときに、いちいち人に説明しに行くのは面倒。
  その場で書いて専用のフォルダに落としておけば、あとでまとめて読める。

  1件 = マークダウン1枚。そのとき何が起きていたかも一緒に残す
  （直前の入力・出力・経過・設定・版）。あとから再現できるように。
"""
import json, os, time, platform

DIR = os.path.join(os.path.expanduser("~"), "Library",
                   "Application Support", "kernel-ai", "フィードバック")

KINDS = ["不具合", "こうしてほしい", "使いにくい", "その他"]


def _ensure():
    os.makedirs(DIR, exist_ok=True)
    return DIR


def add(text, kind="不具合", context=None):
    """1件書き足す。戻り値はできたファイルのパス"""
    text = (text or "").strip()
    if not text:
        raise ValueError("中身がからっぽです")
    if kind not in KINDS:
        kind = "その他"
    _ensure()
    t = time.localtime()
    stamp = time.strftime("%Y%m%d-%H%M%S", t)
    path = os.path.join(DIR, f"{stamp}_{kind}.md")

    ctx = context or {}
    lines = [
        f"# {kind}",
        f"- 日時: {time.strftime('%Y-%m-%d %H:%M:%S', t)}",
        f"- 環境: macOS {platform.mac_ver()[0]} / Python {platform.python_version()}",
        f"- モード: {ctx.get('モード', '—')}",
        "",
        "## 書いたこと",
        text,
        "",
    ]
    if ctx.get("入力"):
        lines += ["## そのときの入力", "```", str(ctx["入力"]), "```", ""]
    if ctx.get("出力"):
        lines += ["## そのときの返事", "```", str(ctx["出力"])[:4000], "```", ""]
    if ctx.get("経過"):
        lines += ["## そのときの経過", "```", str(ctx["経過"])[:8000], "```", ""]
    if ctx.get("設定"):
        lines += ["## そのときの設定", "```json",
                  json.dumps(ctx["設定"], ensure_ascii=False, indent=1), "```", ""]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def listing(limit=50):
    _ensure()
    out = []
    for fn in sorted(os.listdir(DIR), reverse=True)[:limit]:
        if not fn.endswith(".md"):
            continue
        p = os.path.join(DIR, fn)
        head = ""
        try:
            with open(p, encoding="utf-8") as f:
                for ln in f:
                    if ln.startswith("## 書いたこと"):
                        head = next(f, "").strip()
                        break
        except Exception:
            pass
        out.append({"名": fn, "パス": p, "さわり": head[:60]})
    return out


def folder():
    return _ensure()


if __name__ == "__main__":
    print("置き場:", folder())
    for f in listing():
        print(" -", f["名"], "|", f["さわり"])
