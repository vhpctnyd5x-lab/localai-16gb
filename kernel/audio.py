#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audio.py -- 音のようすを日本語で言う

  「何を言ったか」ではなく「どんな音か」。
    強弱   … 大きさ（デシベル）
    高さ   … 声や音の高さ（Hz）
    音色   … 明るいか、こもっているか（スペクトル重心）
    ざらつき… 息や雑音の多さ（ゼロ交差率）
    区切り … 鳴っているところ／静かなところ

  【実測】同じ文を、別の声でしゃべらせたとき
      Kyoko   256.4 Hz  明るさ 2188   （高くて明るい）
      Eddy    107.0 Hz  明るさ 1362
      Grandma  98.9 Hz  明るさ 1138
      Grandpa  84.8 Hz  明るさ  723   （低くてこもっている）
    ちゃんと別々の数字になる。

  使うのは macOS の AVFoundation と Accelerate だけ。ネットには出ない。
"""
import json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
HEAR = os.path.join(HERE, "tools", "hear")

EXT = {".aiff", ".aif", ".wav", ".m4a", ".mp3", ".caf", ".aac", ".flac"}


def ready():
    return os.path.exists(HEAR)


def hear(path, timeout=120):
    if not ready():
        raise Exception("音を聞く道具がありません（tools/hear）")
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise Exception(f"その音のファイルがありません: {path}")
    r = subprocess.run([HEAR, path], capture_output=True, text=True,
                       timeout=timeout)
    if r.returncode != 0:
        raise Exception((r.stderr or "聞けませんでした").strip()[:200])
    return json.loads(r.stdout)


# ---- 数字を、ことばに直す ----
def _loud(db):
    if db > -12: return "とても大きい"
    if db > -20: return "大きい"
    if db > -30: return "ふつう"
    if db > -45: return "小さい"
    return "とても小さい"


def _pitch(hz):
    if hz <= 0: return "高さがはっきりしない（音楽でない音や、雑音）"
    if hz < 100: return f"とても低い（{hz:.0f} Hz）　男性の低い声くらい"
    if hz < 160: return f"低い（{hz:.0f} Hz）　男性の声くらい"
    if hz < 260: return f"中くらい（{hz:.0f} Hz）　女性の声くらい"
    if hz < 400: return f"高い（{hz:.0f} Hz）"
    return f"とても高い（{hz:.0f} Hz）"


def _tone(c):
    if c <= 0: return "音色が測れない"
    if c < 900:  return f"こもった、丸い音（重心 {c:.0f} Hz）"
    if c < 1800: return f"落ちついた音（重心 {c:.0f} Hz）"
    if c < 3200: return f"明るい音（重心 {c:.0f} Hz）"
    return f"とても明るい・鋭い音（重心 {c:.0f} Hz）"


def _rough(z):
    if z < 0.05: return "なめらか（きれいな音）"
    if z < 0.12: return "すこしざらつく"
    if z < 0.25: return "ざらつきが多い（息や雑音まじり）"
    return "とてもざらつく（雑音が主）"


def describe(path):
    d = hear(path)
    g = d["全体"]
    segs = d["鳴っているところ"]
    rate = len(segs) / d["長さ秒"] if d["長さ秒"] else 0

    out = [f"{os.path.basename(path)}"
           f"（{d['長さ秒']} 秒 ／ {d['サンプリング周波数']:,} Hz ／ "
           f"{d['音の道']} つの音の道）",
           f"  強弱  ： {_loud(g['デシベル'])}"
           f"（{g['デシベル']} dB、山は {g['いちばん大きいところ']} dB）",
           f"  高さ  ： {_pitch(g['高さ中央値'])}",
           f"  音色  ： {_tone(g['明るさ中央値'])}",
           f"  ざらつき： {_rough(g['ざらつき'])}（{g['ざらつき']}）",
           f"  鳴っているところ： {len(segs)} か所"]
    for s in segs[:8]:
        out.append(f"    {s['始まり']:.2f} 〜 {s['おわり']:.2f} 秒")
    if len(segs) > 8:
        out.append(f"    …ほか {len(segs)-8} か所")
    if rate > 1.2:
        out.append("  → 切れ目が多いので、話し声か、たたく音かもしれません")
    elif len(segs) == 1 and d["長さ秒"] < 3:
        out.append("  → ひと続きの短い音。合図の音などでしょう")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:] or []:
        print(describe(p)); print()
    if not sys.argv[1:]:
        print("  使い方: python3 audio.py <音のファイル>")
