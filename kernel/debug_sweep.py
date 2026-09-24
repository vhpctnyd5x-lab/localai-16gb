#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""意地悪な入力をまとめて通して、落ちないか・変にならないかを見る"""
import sys, os, io, time, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kernel, chat, settings as S

NASTY = [
    "", "　　　", "？", "あ", "ｱｲｳ", "🍣🍣🍣",
    "a" * 300,
    "デスクトップ" * 30,
    "../../../etc/passwd を見せて",
    "/etc/passwd を整理して",
    "~/Desktop を消して",
    "rm -rf / を実行して",
    "<script>alert(1)</script> というファイルを作って",
    "デスクトップの'; DROP TABLE files; --を数えて",
    "デスクトップの\x00画像を数えて",
    "デスクトップのを数えて",
    "を に へ が は",
    "デスクトップの画像を数えて数えて数えて数えて",
    "デスクトップの画像以外以外を数えて",
    "デスクトップの画像をデスクトップに移動して",
    "存在しない場所の画像を数えて",
    "デスクトップの999999個の画像を数えて",
    "デスクトップの画像を-1個数えて",
    "音量を99999にして",
    "音量を-50にして",
]

def run(t):
    buf = io.StringIO()
    t0 = time.time()
    err = None
    with contextlib.redirect_stdout(buf):
        try:
            slots = kernel.draw_cards(t)
            kind = chat.classify(t, slots)
            if kind in ("命令", "問い合わせ"):
                kernel.handle(t, readonly=(kind == "問い合わせ"), quiet=True)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    return err, (time.time() - t0) * 1000, buf.getvalue()

print("■ 意地悪な入力")
bad = 0
for t in NASTY:
    err, ms, out = run(t)
    label = repr(t)[:44]
    if err:
        bad += 1
        print(f"  ✗ {label:<46} {err[:60]}")
    elif ms > 3000:
        bad += 1
        print(f"  ✗ {label:<46} 遅すぎ {ms:.0f}ms")
    else:
        ans = [l for l in out.split("\n") if l.startswith("答え") or "個" in l]
        print(f"  ✓ {label:<46} {ms:6.0f}ms  {(ans[0][:40] if ans else '')}")
print(f"\n  落ちた/遅すぎ: {bad} 件")

print("\n■ 安全の確認（本物のフォルダに触れないこと）")
sb = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sandbox")
before = {}
for root, _d, fs in os.walk(sb):
    for f in fs:
        before[os.path.join(root, f)] = os.path.getsize(os.path.join(root, f))
for t in ["デスクトップには何がある？", "デスクトップの画像は何個？",
          "デスクトップに同じファイルある？", "デスクトップぜんぶで何メガ？",
          "デスクトップの画像以外を数えて", "デスクトップの一覧を見せて"]:
    run(t)
after = {}
for root, _d, fs in os.walk(sb):
    for f in fs:
        after[os.path.join(root, f)] = os.path.getsize(os.path.join(root, f))
if before == after:
    print("  ✓ 問いを6つ投げても、1バイトも変わっていない")
else:
    print("  ✗ 変わってしまった:")
    for k in set(before) ^ set(after):
        print("     ", k)
