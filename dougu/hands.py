#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hands.py -- 押す・打つ・スクロールする（＋アプリを前に出す）

  eyes.py が「見る」係、こちらが「動かす」係。
  2つを合わせると、「◯◯と書いてあるところを押して」ができる。

  【許可がいる】
    アクセシビリティ … マウスとキーボードを動かすため
    画面収録         … 画面を見るため
  どちらも
    システム設定 → プライバシーとセキュリティ
  で出す。許可が無いときは、黙って空振りせず、はっきり断る。

  【安全のための決めごと】
  ・押す場所は必ず画面の中。外は押さない
  ・「見つからなかったら押さない」。近そうなものを当てずっぽうで押さない
  ・打ち込む文字に、鍵やパスワードは混ぜない（呼ぶ側の責任だが、ここでも長さを見る）
"""
import json, os, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
POINT = os.path.join(HERE, "tools", "point")

MAX_TYPE = 2000        # 一度に打ち込める文字数の上限。暴走よけ


def ready():
    return os.path.exists(POINT)


def _run(*args, timeout=30):
    if not ready():
        raise Exception("動かす道具がありません（tools/point）")
    r = subprocess.run([POINT] + [str(a) for a in args],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise Exception((r.stderr or "うまくいきませんでした").strip())
    try:
        return json.loads(r.stdout or "{}")
    except Exception:
        return {"ok": True}


def screen():
    return _run("screen")


def where():
    return _run("where")


def _inside(x, y):
    s = screen()
    return 0 <= x < s["幅"] and 0 <= y < s["高さ"]


def move(x, y):
    if not _inside(x, y):
        raise Exception(f"画面の外です（{x},{y}）")
    return _run("move", int(x), int(y))


def click(x, y, right=False, double=False):
    if not _inside(x, y):
        raise Exception(f"画面の外です（{x},{y}）")
    a = ["click", int(x), int(y)]
    if right: a.append("--right")
    if double: a.append("--double")
    return _run(*a)


def drag(x1, y1, x2, y2):
    if not (_inside(x1, y1) and _inside(x2, y2)):
        raise Exception("画面の外です")
    return _run("drag", int(x1), int(y1), int(x2), int(y2))


def scroll(amount, x=None, y=None):
    a = ["scroll", int(amount)]
    if x is not None and y is not None:
        a += ["--x", int(x), "--y", int(y)]
    return _run(*a)


def type_text(t):
    t = str(t)
    if len(t) > MAX_TYPE:
        raise Exception(f"一度に打つには長すぎます（{len(t)} 文字）")
    return _run("type", t, timeout=max(30, len(t) // 8))


def key(name, cmd=False, shift=False, opt=False, ctrl=False):
    a = ["key", name]
    if cmd: a.append("--cmd")
    if shift: a.append("--shift")
    if opt: a.append("--opt")
    if ctrl: a.append("--ctrl")
    return _run(*a)


# 日本語のアプリ名 → AppleScript が知っている名前（"tell application" は英語名でしか通らない）
_NAMAE = {"電卓": "Calculator", "計算機": "Calculator", "テキストエディット": "TextEdit", "メモ": "Notes", "メモ帳": "Notes",
          "ファインダー": "Finder", "サファリ": "Safari", "クローム": "Google Chrome", "Chrome": "Google Chrome",
          "プレビュー": "Preview", "カレンダー": "Calendar", "リマインダー": "Reminders", "連絡先": "Contacts",
          "写真": "Photos", "メール": "Mail", "ミュージック": "Music", "マップ": "Maps", "地図": "Maps",
          "システム設定": "System Settings", "ターミナル": "Terminal", "辞書": "Dictionary", "時計": "Clock", "天気": "Weather"}


def front(app):
    """アプリを前に出す"""
    app = str(app).strip()
    app = _NAMAE.get(app, app)
    if (not app or len(app) > 120
            or any(ord(ch) < 0x20 for ch in app)):
        raise ValueError("アプリ名が不正です")
    # osascript はシェル経由ではないが、AppleScript の文字列へそのまま
    # 埋め込むと、引用符を含む名前がスクリプト構文へ混ざる。アプリ名は
    # データとして扱い、AppleScript の文字列リテラル用にエスケープする。
    apple_app = app.replace("\\", "\\\\").replace('"', '\\"')
    r = subprocess.run(["osascript", "-e",
                        f'tell application "{apple_app}" to activate'],
                       capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        raise Exception((r.stderr or "").strip()[:160] or f"{app} を前に出せません")
    time.sleep(0.5)
    return {"ok": True, "アプリ": app}


def apps():
    """いま動いているアプリの名前"""
    r = subprocess.run(["osascript", "-e",
        'tell application "System Events" to get name of every process '
        'whose background only is false'],
        capture_output=True, text=True, timeout=15)
    return [x.strip() for x in (r.stdout or "").split(",") if x.strip()]


def mae_no_app():
    """いま前に出ているアプリの名前。分からなければ None

    文字を打ち込む前に、どこへ入るのかを見るために要る。
    見ずに打っていたので、前がターミナルでも、パスワード欄でも、
    書きかけのメールでも、同じように打ち込んでいた
    """
    try:
        r = subprocess.run(["osascript", "-e",
            'tell application "System Events" to get name of first process '
            'whose frontmost is true'],
            capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip() or None
    except Exception:
        return None


# 文字を打ち込んではいけない相手。
#   ターミナル系 … 打った文字がそのまま命令になる
#   鍵を扱うもの … 打った先が記録に残る
_UTANAI = ("Terminal", "iTerm", "iTerm2", "Warp", "Alacritty", "kitty",
           "Ghostty", "Console", "Keychain Access", "キーチェーンアクセス",
           "1Password", "Bitwarden", "System Settings", "システム設定",
           "System Preferences", "Screen Sharing", "Xcode")


def utte_ii(app):
    """そのアプリに打ち込んでよいか。(よいか, 理由)"""
    if not app:
        return False, "どのアプリが前に出ているのか分かりません"
    for ng in _UTANAI:
        if ng.lower() in app.lower():
            return False, f"前に出ているのが {app} です"
    return True, None


# ------------------------------------------------------------------
# 見て、押す
# ------------------------------------------------------------------
def click_text(label, window=None, nth=0, double=False, fast=False,
               dry=False):
    """画面から その文字を探して、そこを押す。

    見つからなければ押さない。当てずっぽうはしない。
    dry=True なら、押さずに「どこを押すか」だけ返す（仮想）
    """
    import eyes
    if window:
        front(window)
    seen = eyes.look(fast=fast)
    hits = eyes.find(label, seen=seen)
    if not hits:
        near = sorted(seen["文字"], key=lambda x: -x["確からしさ"])[:6]
        raise Exception(
            f"「{label}」は画面にありません。\n"
            "    近くにあった文字: "
            + "、".join(h["文"][:16] for h in near))
    if nth >= len(hits):
        raise Exception(f"{nth+1} 個めはありません（{len(hits)} 個みつかりました）")
    h = hits[nth]
    c = h["まんなか"]
    if dry:
        return {"押す予定": h["文"], "x": c["x"], "y": c["y"],
                "みつかった数": len(hits), "確からしさ": h["確からしさ"]}
    click(c["x"], c["y"], double=double)
    return {"押した": h["文"], "x": c["x"], "y": c["y"],
            "みつかった数": len(hits), "確からしさ": h["確からしさ"]}


if __name__ == "__main__":
    import sys
    if not sys.argv[1:]:
        print("  画面:", screen())
        print("  いまの位置:", where())
        print("  動いているアプリ:", "、".join(apps()[:12]))
    else:
        print(click_text(" ".join(sys.argv[1:]), dry=True))
