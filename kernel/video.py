#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video.py -- 動画に何が写っているかを言う

  やり方は、あなたの言ったとおり「画像認識を、続けてやる」。
  ただし、全部のコマを見ると CPU が焼ける。

      30分の動画 × 30コマ/秒 = 54,000 コマ
      1コマ 0.1 秒でも 90 分かかる

  そこで2つ工夫する。

    ① 間引く … 何秒かに1コマだけ見る（既定 2 秒に1コマ、上限 40 コマ）
    ② 変わったところだけ … 前のコマと同じような絵なら、見ないで飛ばす

  コマの取り出しは avconvert（macOS に最初から入っている）を使う。
  無ければ QuickTime を AppleScript で呼ぶ。ffmpeg は要らない。

  音も一緒に見る（audio.py）。動画の中身は、絵と音の両方でできている。
"""
import glob, json, os, shutil, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}

EVERY = 2.0        # 何秒に1コマ見るか
MAX_FRAMES = 40    # 上限。これ以上は見ない（CPU よけ）


FRAMES = os.path.join(HERE, "tools", "frames")


def ready():
    return os.path.exists(FRAMES)


def frames(path, every=EVERY, limit=MAX_FRAMES, width=640, timeout=300):
    """コマを間引いて取り出す。

    はじめは avconvert と qlmanage を組み合わせていたが、
    時刻を指定したコマが取れず、いつも動画1本ぶんの
    代表サムネイル1枚しか返ってこなかった（6秒の動画で1コマ）。
    AVAssetImageGenerator を直に使うと、狙った秒のコマが取れる。

    戻り値: ([(秒, 絵のパス)], 作業部屋, 長さ秒)
    """
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise Exception(f"その動画がありません: {path}")
    if not ready():
        raise Exception("コマを取り出す道具がありません（tools/frames）")
    room = tempfile.mkdtemp(prefix="kernel-video-")
    r = subprocess.run([FRAMES, path, room, "--every", str(every),
                        "--max", str(limit), "--width", str(width)],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        shutil.rmtree(room, ignore_errors=True)
        raise Exception((r.stderr or "コマを取れませんでした").strip()[:200])
    d = json.loads(r.stdout)
    return [(k["秒"], k["絵"]) for k in d["コマ"]], room, d["長さ秒"]


def describe(path, every=EVERY, limit=MAX_FRAMES, quiet=True):
    """動画のようすを、日本語で"""
    import vision
    got, room, dur = frames(path, every, limit)
    try:
        if not got:
            return (f"{os.path.basename(path)} からコマを取り出せませんでした。\n"
                    "  QuickTime で開ける形式か確かめてください")
        out = [f"{os.path.basename(path)}"
               f"（{dur:.1f} 秒 ／ {len(got)} コマだけ見ました"
               f"／ {every:.0f} 秒に1コマ）"]
        seen, last = {}, None
        for at, img in got:
            try:
                d = vision.look(img, top=4)
            except Exception:
                continue
            names = [l["日本語"] for l in d.get("写っているもの", [])[:3]]
            key = "/".join(names)
            for a in d.get("どうぶつ", []):
                names.insert(0, a["日本語"])
            for nm in names:
                seen[nm] = seen.get(nm, 0) + 1
            # 前のコマと同じ顔ぶれなら、行を増やさない（読みにくくなる）
            if key != last:
                out.append(f"  {at:6.1f} 秒： {' / '.join(names) or '（不明）'}")
                last = key
        if seen:
            top = sorted(seen.items(), key=lambda x: -x[1])[:6]
            out.append("  よく写っていたもの： "
                       + "、".join(f"{k}（{v}コマ）" for k, v in top))
        # 音も見る
        try:
            import audio
            snd = os.path.join(room, "oto.m4a")
            r = subprocess.run(["avconvert", "--source", path, "--output", snd,
                                "--preset", "PresetAppleM4A", "--replace"],
                               capture_output=True, timeout=180)
            if r.returncode == 0 and os.path.exists(snd):
                out.append("")
                out.append("  ── 音 ──")
                out.append("  " + audio.describe(snd).split("\n", 1)[1]
                           .replace("\n", "\n  "))
        except Exception:
            pass
        return "\n".join(out)
    finally:
        shutil.rmtree(room, ignore_errors=True)


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(describe(p))
    if not sys.argv[1:]:
        print("  使い方: python3 video.py <動画のパス>")
        print("  取り出せるか:", ready())
