#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corpus_collect.py -- 本人の日本語だけを集めてコーパスを作る

  カードを「数えて」作るための材料。本人の言葉づかいを写すため、
  本人が書いた文だけを集める（アシスタントの発言・コード・ログは捨てる）。

  出力: corpus/ の中に .txt
"""
import os, sys, json, re, glob, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "corpus")
HOME = os.path.expanduser("~")

KANA = re.compile(r"[ぁ-んァ-ヴ]")
# 捨てるもの：鍵らしき文字列、URL、パス、長い英数字、base64
DROP = [
    re.compile(r"(sk-|gsk_|nvapi-|ghp_|xox[baprs]-)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"[A-Za-z0-9+/]{32,}={0,2}"),
    re.compile(r"https?://\S+"),
    re.compile(r"[~/][\w./\-]{12,}"),
    re.compile(r"\b[A-Fa-f0-9]{16,}\b"),
]
CODEY = re.compile(r"^\s*(?:[{}\[\]()<>#/*|`+\-=]|def |class |import |from |\$ |> )")


SENT = re.compile(r"(?<=[。！？!?])\s*")


def split_sentences(block):
    """長い発言は文に割る。まるごと捨てると本人の言葉がほとんど残らない"""
    out = []
    for line in block.splitlines():
        for sent in SENT.split(line):
            sent = sent.strip()
            while len(sent) > 200:            # 句点の無い長文は適当に切る
                out.append(sent[:200]); sent = sent[200:]
            if sent:
                out.append(sent)
    return out


def clean_line(l):
    l = l.strip()
    if len(l) < 4 or len(l) > 200:
        return None
    if not KANA.search(l):                 # 日本語でない行は捨てる
        return None
    if CODEY.match(l):
        return None
    for p in DROP:
        if p.search(l):
            return None
    if l.count("　") > 6 or l.count("\t"):
        return None
    return l


def from_jsonl(paths, limit_mb=400):
    """会話ログから、本人(user)の発言だけを取り出す"""
    got = []
    for p in paths:
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if '"role":"user"' not in line and '"type":"user"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    m = d.get("message") or {}
                    if m.get("role") != "user":
                        continue
                    c = m.get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c
                                     if isinstance(x, dict) and x.get("type") == "text")
                    if not isinstance(c, str):
                        continue
                    # ツール結果やシステム挿入は本人の言葉ではない
                    if c.startswith(("<", "[Request interrupted", "Caveat:")):
                        continue
                    got.append(c)
        except Exception:
            continue
    return got


def from_files(patterns):
    got = []
    for pat in patterns:
        for p in glob.glob(pat, recursive=True):
            if not os.path.isfile(p):
                continue
            try:
                got.append(open(p, encoding="utf-8", errors="ignore").read())
            except Exception:
                continue
    return got


def write(name, blocks):
    os.makedirs(OUT, exist_ok=True)
    seen, lines = set(), []
    for b in blocks:
        for l in split_sentences(b):
            c = clean_line(l)
            if not c:
                continue
            h = hashlib.md5(c.encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h); lines.append(c)
    path = os.path.join(OUT, name)
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    chars = sum(len(l) for l in lines)
    print(f"  {name:22} {len(lines):>6} 行  {chars:>9} 文字")
    return chars


if __name__ == "__main__":
    print("■ 本人の日本語を集めます")
    total = 0
    total += write("01_会話ログ.txt",
                   from_jsonl(glob.glob(os.path.join(HOME, ".claude/projects/*/*.jsonl"))))
    total += write("02_メモ.txt",
                   from_files([os.path.join(HOME, ".claude/projects/*/memory/*.md")]))
    total += write("03_書類.txt",
                   from_files([os.path.join(HOME, "Documents/**/*.md"),
                               os.path.join(HOME, "Documents/**/*.txt"),
                               os.path.join(HOME, "Desktop/**/*.md"),
                               os.path.join(HOME, "Desktop/**/*.txt")]))
    print(f"  {'合計':22} {'':>6}    {total:>9} 文字")
