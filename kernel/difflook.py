#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
difflook.py -- なにが変わったかを、行ごとに見せる

  2つの見せ方を持つ。

    ① フォルダの差   … 実行の前と後で、どのファイルが増えた・減った・動いた
    ② ファイルの中身 … 1枚のテキストの、どの行が変わったか

  ②は Python が持っている difflib をそのまま使う。
  自分で書き直す理由がない（車輪の再発明はしない）。
"""
import difflib, os

# 中身を読んで比べてよい大きさ。これ以上は行数だけ見る
MAX_READ = 2_000_000
TEXT_EXT = {".txt", ".md", ".html", ".htm", ".css", ".js", ".json", ".py",
            ".csv", ".log", ".xml", ".yml", ".yaml", ".sh", ".ini", ".cfg"}


def is_text(path):
    if os.path.splitext(path)[1].lower() in TEXT_EXT:
        return True
    try:
        with open(path, "rb") as f:
            head = f.read(2048)
        return b"\0" not in head
    except OSError:
        return False


def read(path):
    try:
        if os.path.getsize(path) > MAX_READ:
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return None


def lines(a_lines, b_lines, a_name="前", b_name="後", ctx=3):
    """行の差を [(しるし, 文)] で返す。

    しるし: "+" 増えた / "-" 減った / " " そのまま / "@" 区切り
    """
    if a_lines is None or b_lines is None:
        return [("@", "中身が読めませんでした")]
    out = []
    for ln in difflib.unified_diff(a_lines, b_lines,
                                   fromfile=a_name, tofile=b_name,
                                   lineterm="", n=ctx):
        if ln.startswith("+++") or ln.startswith("---"):
            continue
        if ln.startswith("@@"):
            out.append(("@", ln.strip()))
        elif ln.startswith("+"):
            out.append(("+", ln[1:]))
        elif ln.startswith("-"):
            out.append(("-", ln[1:]))
        else:
            out.append((" ", ln[1:] if ln.startswith(" ") else ln))
    if not out:
        out = [("@", "中身は変わっていません")]
    return out


def files(a_path, b_path, ctx=3):
    """2つのファイルの中身を比べる"""
    if not os.path.exists(a_path):
        return [("@", f"ありません: {a_path}")]
    if not os.path.exists(b_path):
        return [("@", f"ありません: {b_path}")]
    if not (is_text(a_path) and is_text(b_path)):
        sa, sb = os.path.getsize(a_path), os.path.getsize(b_path)
        return [("@", f"文字のファイルではありません（{sa:,} → {sb:,} バイト）")]
    return lines(read(a_path), read(b_path),
                 os.path.basename(a_path), os.path.basename(b_path), ctx)


def folders(before, after):
    """フォルダの前と後（virtual.simulate の「前」「後」）を突き合わせる。

    戻り値: [{"場所", "増えた": [...], "減った": [...], "件数": (前, 後)}]
    """
    out = []
    for d in sorted(set(before) | set(after)):
        b = list(before.get(d, []))
        a = list(after.get(d, []))
        if b == a:
            continue
        out.append({"場所": d,
                    "増えた": [x for x in a if x not in b],
                    "減った": [x for x in b if x not in a],
                    "件数": (len(b), len(a))})
    return out


def render(rows, limit=200):
    """行の差を、人が読める文字列にする"""
    out = []
    for i, (mark, text) in enumerate(rows):
        if i >= limit:
            out.append(f"… ほか {len(rows)-limit} 行")
            break
        out.append(("  " if mark == " " else mark + " ") + text)
    return "\n".join(out)


def render_folders(rows):
    out = []
    for r in rows:
        name = os.path.basename(r["場所"]) or r["場所"]
        out.append(f"{name}/  {r['件数'][0]} 件 → {r['件数'][1]} 件")
        for x in r["減った"]:
            out.append("  - " + x)
        for x in r["増えた"]:
            out.append("  + " + x)
    return "\n".join(out) or "変わったところはありません"


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        print(render(files(sys.argv[1], sys.argv[2])))
    else:
        a = ["こんにちは", "ここは変わらない", "古い行", "おわり"]
        b = ["こんにちは", "ここは変わらない", "新しい行", "足した行", "おわり"]
        print(render(lines(a, b)))
