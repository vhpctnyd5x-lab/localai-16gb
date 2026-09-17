#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""機械の用件の物差し（kikai.py で足した分＋前からある分の退行）。

  python3 hakaru_kikai.py            … 言い方→用件の当たり（46文）＋ 読の部品を実際に動かす（許可の要らないもの）＋ 跡の門
  python3 hakaru_kikai.py --honban   … カレンダー・リマインダー・メモ・メール・ミュージック・Finder も実際に読む（初回は macOS が許可を聞く）
"""
import json, os, sys, time
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel") if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import machine
HERE = os.path.dirname(os.path.abspath(__file__))

IIKATA = [
    ("今日の予定は？", "予定"), ("明日の予定を教えて", "予定"), ("リマインダーを見せて", "リマインダー一覧"), ("薬を飲むをリマインダーに入れて", "リマインダーに入れる"),
    ("「牛乳を買う」とメモして", "メモを書く"), ("買い物のメモを探して", "メモを探す"), ("ポチというファイルを探して", "ファイルを探す"), ("「請求書」を探して", "ファイルを探す"),
    ("いま流れてる曲は？", "いまの曲"), ("音楽を止めて", "音楽"), ("次の曲にして", "音楽"), ("5分後に知らせて", "タイマー"), ("10分たったら「休憩」と教えて", "タイマー"),
    ("天気は？", "天気"), ("大阪の天気を教えて", "天気"), ("未読メールは？", "未読メール"), ("大きいファイルはどれ？", "大きいファイル"), ("何が容量を食ってる？", "大きいファイル"),
    ("重いアプリは？", "重いアプリ"), ("メモリを食ってるアプリは？", "重いアプリ"), ("バックアップはいつ？", "バックアップ"), ("Finderで選んでいるファイルは？", "選んでいるファイル"),
    ("IPアドレスは？", "IPアドレス"), ("画面をロックして", "画面ロック"), ("画面を明るくして", "明るさ"), ("画面収録の設定を開いて", "設定を開く"), ("Bluetoothの設定を開いて", "設定を開く"),
    ("辞書で「憂鬱」を引いて", "辞書"), ("ミュートして", "消音"), ("音を戻して", "消音"), ("再起動して", "再起動"), ("電源を切って", "電源を切る"),
    ("「こんにちは」と読み上げて", "読み上げる"), ("おはようと読み上げて", "読み上げる"), ("「休憩」と知らせて", "知らせる"),
    # 前からある用件（奪っていないこと）
    ("メモを開いて", "アプリをひらく"), ("画面を暗くして", "見た目をかえる"), ("音量を30にして", "音量をかえる"), ("スクリーンショットを撮って", "スクリーンショット"),
    ("ゴミ箱はいくつ？", "ゴミ箱"), ("電池は？", "電池"), ("空き容量は？", "空き容量"), ("メモリは？", "メモリ"), ("ネットつながってる？", "ネット"), ("いま何時？", "いま何時"),
    ("3日後は何曜日", "こよみ"), ("猫をネットで調べて", "ネットで調べる"), ("Safariを開いて", "アプリをひらく"),
]
UGOKASU = ["ポチというファイルを探して", "大きいファイルはどれ？", "重いアプリは？", "IPアドレスは？", "バックアップはいつ？", "3日後は何曜日", "天気は？"]
HONBAN = ["今日の予定は？", "リマインダーを見せて", "買い物のメモを探して", "未読メールは？", "いま流れてる曲は？", "Finderで選んでいるファイルは？"]


def main():
    honban = "--honban" in sys.argv
    ok = n = 0
    print("===== 言い方 → 用件 =====")
    for toi, kitai in IIKATA:
        h = machine.match(toi); got = h[0] if h else None; n += 1; good = got == kitai; ok += good
        if not good:
            print("  × %-24s → %s（期待 %s）" % (toi, got, kitai))
    print("  当たり %d/%d" % (ok, len(IIKATA)))
    print("===== 読の部品を動かす =====")
    for toi in UGOKASU + (HONBAN if honban else []):
        h = machine.match(toi); n += 1
        try:
            t0 = time.monotonic(); out = machine.run(*h); sec = time.monotonic() - t0
            good = bool(out) and "Traceback" not in out; ok += good
            print("  %s %-22s %4.1f秒  %s" % ("○" if good else "×", toi, sec, str(out).replace("\n", " ⏎ ")[:90]))
        except Exception as e:
            print("  × %-22s %s: %s" % (toi, type(e).__name__, str(e)[:80]))
    print("===== 跡の門（実行せずに止まること） =====")
    for toi in ("再起動して", "電源を切って", "「牛乳を買う」とメモして"):
        h = machine.match(toi)
        a = machine.run(h[0], h[1], confirm=None)          # 確認を渡さない → やらない
        b = machine.run(h[0], h[1], confirm=lambda name: False)   # 断る → やめました
        good = ("実行しません" in a) and (b == "やめました"); n += 1; ok += good
        print("  %s %-16s 確認なし→%s ／ 断る→%s" % ("○" if good else "×", toi, a.replace("\n", " ")[:30], b))
    print("機械: %d/%d（この1回の数字・%s）" % (ok, n, time.strftime("%Y-%m-%d")))
    os.makedirs(os.path.join(HERE, "kekka"), exist_ok=True)
    json.dump({"日付": time.strftime("%Y-%m-%d"), "正答": ok, "問数": n, "本番": honban}, open(os.path.join(HERE, "kekka", "kikai_%s.json" % time.strftime("%Y%m%d")), "w", encoding="utf-8"), ensure_ascii=False)
    return 0 if ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
