#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
speech.py -- 音のファイルから、しゃべった中身を文字にする

  audio.py が「どんな音か」（強弱・高さ・音色）、
  こちらが「何を言ったか」。

  【動きます】(実測)
      「こんにちは今日はいい天気ですねデスクトップの画像を数えてください」
      5.1 秒 ／ 確からしさ 89% ／ 手元だけ（音は外に出ない）
      英語も可: "Hello this is a test of speech recognition"

  【長く動かなかった本当の理由】
  日本語の部品が無いせいだと思っていたが、違った。部品は入っていた。
  黙っていた原因は、こちらのコードの2つ。

    ① recognitionTask が返す「作業の札」を捨てていた
       → 誰も持っていない＝かたづけられ、途中で止まる
    ② 返事を DispatchSemaphore で待っていた
       → Speech の返事はランループに乗って届く。
         メインスレッドを止めると、その道がふさがる。
         エラーも出ず、ただ黙る。いちばんたちが悪い壊れ方。
    直し方: 札を変数に持ち、RunLoop を回しながら待つ。

  【なぜ .app の形にしてあるか】
  ただの実行ファイルだと、macOS が
  「説明書きが無い」と言って必ず落とす（SIGABRT）。
  Info.plist に NSSpeechRecognitionUsageDescription を入れた
  .app の形にして、open 経由で動かす必要がある。
  （実行ファイルを直に叩くと、やはり落ちる。ここは実測で確かめた）
"""
import json, os, subprocess, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "tools", "聞き取り.app")


def ready():
    return os.path.isdir(APP)


def listen(path, lang="ja-JP", allow_net=False, timeout=150):
    """音のファイルを文字にする。

    allow_net=True にすると Apple のサーバーを使う（音が外に出る）。
    既定は手元だけ。
    """
    if not ready():
        raise Exception("聞き取りの道具がありません（tools/聞き取り.app）")
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise Exception(f"その音のファイルがありません: {path}")

    out = os.path.join(tempfile.gettempdir(),
                       f"kernel-kiki-{int(time.time()*1000)}.json")
    argv = ["open", "-a", APP, "--args", path, "--out", out, "--lang", lang]
    if allow_net:
        argv.append("--net")
    subprocess.run(argv, capture_output=True, timeout=30)

    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(out):
            break
        time.sleep(1.0)
    if not os.path.exists(out):
        raise Exception(f"{timeout} 秒待っても返事がありませんでした")
    try:
        with open(out, encoding="utf-8") as f:
            d = json.load(f)
    finally:
        try: os.remove(out)
        except OSError: pass
    if "エラー" in d:
        raise Exception(d["エラー"])
    return d


def describe(path, lang="ja-JP", allow_net=False):
    d = listen(path, lang, allow_net)
    out = [f"{os.path.basename(path)} の中身",
           "",
           d["文"] or "（何もしゃべっていないようです）",
           "",
           f"  確からしさ {d['確からしさ']:.0%}"
           f" ／ {'手元だけ' if d.get('手元だけ') else 'Apple のサーバー'}"
           f" ／ 区切り {len(d.get('区切り', []))} つ"]
    return "\n".join(out)


def status():
    if not ready():
        return "道具がありません"
    return ("道具はあります。はじめて動かすとき、音声認識の許可を聞かれます。\n"
            "  日本語を手元だけで聞き取るには、\n"
            "  システム設定 → キーボード → 音声入力 を入にして、"
            "言語に「日本語」を足してください")


if __name__ == "__main__":
    import sys
    if not sys.argv[1:]:
        print(status())
    else:
        net = "--net" in sys.argv
        for p in [a for a in sys.argv[1:] if not a.startswith("--")]:
            try:
                print(describe(p, allow_net=net))
            except Exception as e:
                print(f"  できませんでした：\n  {e}")
