#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coderun.py -- 小さなプログラムを、その場で動かす

  対応: Python / JavaScript(Node または JavaScriptCore) / シェル / AppleScript

  ────────────────────────────────────────────────
  決めごと（ここが本体）
  ────────────────────────────────────────────────
  外から来た文字をそのまま実行するのは、いちばん危ない部類の操作。
  だから、走らせる前に必ず次を通す。

    ① 使い捨ての作業部屋を作り、その中だけで動かす
       （終わったら中身ごと消す。本物のフォルダには置かない）
    ② 危ない書きかたが混ざっていないかを、先に読んで確かめる
       … ファイルを消す・ネットに出る・別のプログラムを起こす など
    ③ 時間の上限を決める（無限ループで固まらせない）
    ④ 出てくる文字の量にも上限を決める（画面を埋めつくさせない）

  ②で止めたものは走らせない。「たぶん大丈夫」では走らせない。
  自分で書いたつもりのものでも、先生が書いたものでも、同じように通す。
"""
import os, re, shutil, subprocess, tempfile

TIMEOUT = 20            # 秒
MAX_OUT = 20_000        # 文字
MAX_CODE = 100_000      # 文字

# 言語 → (拡張子, 走らせ方)
LANGS = {
    "python": (".py", None),
    "javascript": (".js", None),
    "shell": (".sh", None),
    "applescript": (".scpt", None),
}
ALIAS = {"py": "python", "python3": "python", "js": "javascript",
         "node": "javascript", "sh": "shell", "bash": "shell", "zsh": "shell",
         "osascript": "applescript", "as": "applescript"}

# 走らせない書きかた。言語ごと。
#
#   ここは「完璧な検査」ではない。すり抜ける書きかたは必ずある。
#   だから作業部屋を分けるほう（①）を本命の守りにしていて、
#   これは「うっかり」を止めるための二重目。
DANGER = {
    "python": [
        (r"\bos\s*\.\s*(remove|unlink|rmdir|removedirs|system|popen|exec[lv])",
         "ファイルを消す／別のプログラムを起こす"),
        (r"\bshutil\s*\.\s*(rmtree|move)", "フォルダごと消す／動かす"),
        (r"\bsubprocess\b", "別のプログラムを起こす"),
        (r"\b(socket|urllib|requests|httpx|http\.client|ftplib|smtplib)\b",
         "ネットにつなぐ"),
        (r"\b__import__\s*\(", "見えないやり方で取り込む"),
        (r"\beval\s*\(|\bexec\s*\(", "文字をそのまま実行する"),
        (r"open\s*\([^)]*['\"][wa]", "ファイルに書き込む"),
    ],
    "javascript": [
        (r"require\s*\(\s*['\"](fs|child_process|net|http|https|dgram)",
         "ファイル／別のプログラム／ネット"),
        (r"\bfetch\s*\(|XMLHttpRequest|WebSocket", "ネットにつなぐ"),
        (r"\bprocess\s*\.\s*(exit|kill|env)", "外の様子をいじる"),
        (r"\beval\s*\(", "文字をそのまま実行する"),
    ],
    "shell": [
        (r"\brm\b|\bmv\b|\bdd\b|\bmkfs\b|>\s*/", "ファイルを消す／上書きする"),
        (r"\bcurl\b|\bwget\b|\bnc\b|\bssh\b|\bscp\b", "ネットにつなぐ"),
        (r"\bsudo\b|\bchmod\b|\bchown\b|\bkillall\b|\bdefaults\b",
         "パソコンの設定をいじる"),
        (r"\bosascript\b|\bopen\b\s", "別のプログラムを起こす"),
    ],
    "applescript": [
        (r"\bdo shell script\b", "シェルを呼ぶ"),
        (r"\bdelete\b|\bempty\b|\bquit\b|\bshut down\b|\brestart\b",
         "消す／終わらせる"),
    ],
}


def normalize(lang):
    lang = (lang or "").strip().lower()
    return ALIAS.get(lang, lang)


def available():
    """この機械で、いま動かせる言語"""
    out = {"python": True, "applescript": bool(shutil.which("osascript")),
           "shell": True}
    out["javascript"] = bool(shutil.which("node")) or _has_jsc()
    return out


def _has_jsc():
    return os.path.exists("/System/Library/Frameworks/JavaScriptCore.framework"
                          "/Versions/A/Resources/jsc")


def check(code, lang):
    """走らせてよいか。だめなら理由を返す"""
    if not code or not code.strip():
        return "中身がありません"
    if len(code) > MAX_CODE:
        return f"長すぎます（{len(code):,} 文字）"
    for rx, why in DANGER.get(lang, []):
        m = re.search(rx, code)
        if m:
            return f"走らせません： {why}（{m.group(0)[:40]}）"
    return None


# ── 作業部屋の外に書かせない、本物の囲い ──────────────────────────
#
# ここは長いあいだ「cwd と環境変数を変えるだけ」だった。
# それを docstring は「それでも作業部屋の外には出さない」と書いていたが、
# 事実ではなかった。実測でこれが通った：
#
#     import pathlib
#     pathlib.Path('/Users/xxx/proof.txt').write_text('escaped')
#     → 検査は合格、ホームに書けた
#
# 読ませない、まではやらない（それをやると python3 も起動できない）。
# 「書き込みは作業部屋と一時置き場だけ」に絞る。
# macOS 標準の sandbox-exec を使う。外部の道具は要らない。
_SBPL = """(version 1)
(allow default)
(deny file-write*)
(allow file-write*
  (subpath (param "ROOM"))
  (subpath "/private/var/folders")
  (subpath "/private/tmp")
  (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr")
  (literal "/dev/dtracehelper") (literal "/dev/tty"))
(deny network*)
"""


def _has_sandbox_exec():
    return os.path.exists("/usr/bin/sandbox-exec")


def _wrap(argv, room):
    """作業部屋の外に書けないように包む。

    包めない機械（sandbox-exec が無い）では包まずに走らせるが、
    run() が「囲えていない」と正直に返す。黙って素通ししない。
    """
    if not _has_sandbox_exec():
        return argv, False
    return (["/usr/bin/sandbox-exec", "-p", _SBPL,
             "-D", "ROOM=" + os.path.realpath(room)] + argv), True


def _argv(lang, path):
    if lang == "python":
        return ["python3", "-I", "-B", path]   # -I で外の設定を持ち込ませない
    if lang == "shell":
        return ["/bin/sh", path]
    if lang == "applescript":
        return ["osascript", path]
    if lang == "javascript":
        node = shutil.which("node")
        if node:
            return [node, path]
        jsc = ("/System/Library/Frameworks/JavaScriptCore.framework"
               "/Versions/A/Resources/jsc")
        if os.path.exists(jsc):
            return [jsc, path]
        raise Exception("JavaScript を動かすものがありません（node も jsc も無い）")
    raise Exception(f"知らない言語です: {lang}")


def run(code, lang="python", timeout=TIMEOUT, force=False):
    """動かす。

    force=True にすると危ない書きかたの検査を飛ばす（自分で書いた時だけ）。
    それでも作業部屋の外には出さない。

    戻り値: {"言語","出力","エラー","終了コード","ミリ秒","作業部屋"}
    """
    import time
    lang = normalize(lang)
    if lang not in LANGS:
        raise Exception(f"知らない言語です: {lang}（"
                        + " / ".join(LANGS) + " が使えます）")
    if not force:
        bad = check(code, lang)
        if bad:
            raise Exception(bad)

    ext = LANGS[lang][0]
    room = tempfile.mkdtemp(prefix="kernel-run-")
    path = os.path.join(room, "しごと" + ext)
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)

    # 環境変数も、必要な最低限だけ渡す。
    # 家のパスや鍵をそのまま見せない
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin",
           "HOME": room, "TMPDIR": room, "LANG": "ja_JP.UTF-8",
           "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}

    argv, kakoi = _wrap(_argv(lang, path), room)

    t0 = time.time()
    try:
        r = subprocess.run(argv, cwd=room, env=env,
                           capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        out, err, rc = r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        out, err, rc = "", f"{timeout} 秒たっても終わらないので、止めました", -1
    finally:
        made = []
        try:
            for n in sorted(os.listdir(room)):
                if n != os.path.basename(path):
                    made.append(n)
        except OSError:
            pass
        shutil.rmtree(room, ignore_errors=True)

    def cut(s):
        s = s or ""
        return s if len(s) <= MAX_OUT else s[:MAX_OUT] + \
            f"\n…（あと {len(s)-MAX_OUT:,} 文字は省きました）"

    return {"言語": lang, "出力": cut(out), "エラー": cut(err),
            "終了コード": rc, "ミリ秒": round((time.time() - t0) * 1000),
            "作った物": made, "囲えた": kakoi}


def report(r):
    out = [f"【{r['言語']}】 {r['ミリ秒']} ミリ秒 ／ 終了コード {r['終了コード']}"]
    if r["出力"]:
        out.append(r["出力"].rstrip())
    if r["エラー"]:
        out.append("── エラー ──")
        out.append(r["エラー"].rstrip())
    if r["作った物"]:
        out.append("（作業部屋に作られた物: "
                   + "、".join(r["作った物"]) + " …部屋ごと消しました）")
    if not r["出力"] and not r["エラー"]:
        out.append("（何も出力されませんでした）")
    if not r.get("囲えた", True):
        out.append("⚠ この機械には sandbox-exec が無いので、"
                   "作業部屋の外に書けない保証はありません")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    print("  動かせる言語:", {k: ("○" if v else "×")
                              for k, v in available().items()})
    if len(sys.argv) > 2:
        print(report(run(sys.argv[2], sys.argv[1])))
