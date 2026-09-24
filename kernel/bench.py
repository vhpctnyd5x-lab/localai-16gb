#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bench.py -- 性能を測る

  「賢くなった気がする」では直すところを間違える。
  ・ちゃんと答えられた割合
  ・かかった時間（はじめて / 2回目）
  ・ノートが当たった割合
  を、まとめて出す。
"""
import os, sys, io, time, json, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kernel

# 入力 → 期待する答えの一部（含まれていれば正解とみなす）
CASES = [
    ("デスクトップの写真を数えて",              "5 個"),
    ("机の上の画像はいくつ？",                  "5 個"),
    ("デスクトップの動画は何個？",              "1 個"),
    ("デスクトップのPDFを数えて",               "1 個"),
    ("デスクトップには何がある？",              "旅行1.jpg"),
    ("ダウンロードのPDFを数えて",               "3 個"),
    ("デスクトップの去年の写真を数えて",        "4 個"),
    ("デスクトップの書類を数えて",              "2 個"),
    ("デスクトップの一覧を見せて",              "会議.pdf"),
    ("ダウンロードには何がある？",              "請求書.pdf"),
    ("デスクトップのテキストを数えて",          "1 個"),
    ("机の上の去年の画像はいくつ",              "4 個"),
    ("デスクトップの音楽を数えて",              "0 個"),
    ("ダウンロードの画像を数えて",              "1 個"),
    # --- ここから、実際のやりとりで出てきた言い方 ---
    ("机の上の去年のスナップ、片付けといて",     "個を"),
    ("デスクトップに散らかってる写真を集めて",   "個を"),
    ("さっき撮ったやつを見せて",                 "jpg"),
    ("デスクトップの一番大きいファイルは？",     "mp4"),
    ("ダウンロードで一番古いのは何？",           "古い.pdf"),
    ("デスクトップに同じファイルある？",         "組"),
    ("デスクトップぜんぶで何メガ？",             "MB"),
    ("デスクトップの画像は何個？",              "5 個"),
    ("先月のダウンロードを数えて",               "個"),
    ("デスクトップのjpgだけ見せて",              "旅行1.jpg"),
    ("デスクトップの画像以外を数えて",           "3 個"),
    # --- ここから、文法（述語と助詞）で読むもの ---
    ("ダウンロードから書類をデスクトップに移して", "3 個を"),
    ("デスクトップの写真を寄せといてくれる？",   "個を"),
    ("デスクトップのテキストをしまっとく",       "個を"),
    ("デスクトップの画像を並べてもらえる？",     "旅行1.jpg"),
    ("デスクトップの画像を数えといて",           "5 個"),
    ("机の上の去年の写真をまとめてほしい",       "個を"),
    ("デスクトップの動画を数えてください",       "1 個"),
    ("デスクトップのPDFを見せてよ",              "会議.pdf"),
]


import chat


def once(text):
    """1回動かして (答え, ミリ秒, 記録) を返す

    聞かれているのか命令なのかは、本番と同じ振り分けで決める。
    ここを全部「聞かれている」にしていたので、
    「片付けといて」まで一覧が返って、不正解に数えていた
    """
    # 動かす命令は練習用フォルダを書き換えるので、毎回まっさらに戻す。
    # 戻していなかったため、前の命令が動かした結果を次が見てしまい、
    # 2回目以降の正解率が下がっていた（ノートのせいに見えていた）
    with contextlib.redirect_stdout(io.StringIO()):
        kernel.make_demo()
    slots = kernel.draw_cards(text)
    kind = chat.classify(text, slots)
    ro = (kind != "命令")
    buf = io.StringIO()
    t0 = time.time()
    with contextlib.redirect_stdout(buf):
        try:
            ans = kernel.handle(text, readonly=ro, quiet=True)
        except Exception as e:
            ans = f"失敗: {e}"
    ms = (time.time() - t0) * 1000
    return (ans or ""), ms, buf.getvalue()


def note_uses():
    """ノートが当たった回数。

    前はノートの「回数」の合計を前後で引き算していた。
    だが手順を組み立て直すたびに 回数 が 1 に戻る作りだったので、
    合計が下がることがあり、当たった回数がマイナスになっていた
    （実測で -23/33 が出た）。
    いまは kernel がその場で数えているので、それを読む。
    """
    try:
        return kernel.note_hit_total()
    except AttributeError:
        return 0


def run(label, reset_note):
    if reset_note:
        for f in ("notebook.json", "policy.json"):
            p = os.path.join(HERE, f)
            if os.path.exists(p):
                os.remove(p)
    before = note_uses()
    ok = 0
    total = 0.0
    rows = []
    for text, want in CASES:
        ans, ms, _log = once(text)
        good = want in (ans or "")
        ok += good; total += ms
        rows.append((text, want, ans, ms, good, False))
    hit = note_uses() - before
    n = len(CASES)
    print(f"\n■ {label}")
    print(f"  正解      : {ok}/{n}  （{ok/n*100:.0f}%）")
    print(f"  ノート当たり: {hit}/{n}  （{hit/n*100:.0f}%）")
    print(f"  合計時間  : {total:.0f} ミリ秒  （1件あたり {total/n:.1f}）")
    for text, want, ans, ms, good, _h in rows:
        if not good:
            print(f"    ✗ {text}")
            print(f"        ほしい「{want}」／ 出た「{str(ans)[:60]}」")
    return ok, n, total, hit


if __name__ == "__main__":
    # KERNEL_THINK=1 で「じっくり（何人かで考える）」を測る
    if os.environ.get("KERNEL_THINK") == "1":
        kernel.THINK_HARD = True
        print("※ じっくりモード（何人かで考えて多数決）で測ります")
    a = run("1回目（ノート空っぽ）", reset_note=True)
    b = run("2回目（ノートが溜まった状態）", reset_note=False)
    c = run("3回目", reset_note=False)
    print("\n■ まとめ")
    print(f"  正解    : {a[0]}/{a[1]} → {b[0]}/{b[1]} → {c[0]}/{c[1]}")
    print(f"  合計時間: {a[2]:.0f} → {b[2]:.0f} → {c[2]:.0f} ミリ秒")
    print(f"  ノート  : {a[3]} → {b[3]} → {c[3]} 件が当たった")
