#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_page.py -- 「テトリスを作って」に応えられるようにする

  ────────────────────────────────────────────────
  なぜ作ったか（気づいたことフォルダから）
  ────────────────────────────────────────────────
    02:22:24 $ HTML形式で       → 「了解です。HTMLファイルを作成しますね」
    02:22:52 $ テトリスという   → 「テトリスですね、了解です」
    02:22:59 $ ゲームを作って   → 「ゲームを作ることはできません」

  返事だけして、何も作っていなかった。しかも最後は断っている。
  カーネルは HTML を書き出す部品を持っているのに、
  「中身を考える」係がいなかったのが原因。

  ────────────────────────────────────────────────
  分担
  ────────────────────────────────────────────────
    中身を書く … 先生（Groq / NVIDIA）。文章を作るのは向こうが得意
    確かめる   … カーネル。形・危なさ・大きさを自分で見る
    書き出す   … カーネル。どこに置くか、上書きしないかは自分で決める

  先生の言うことは信用しない。必ずこちらで確かめてから置く。
  外へつなぐ記述（よそのURL・盗み見）が混ざっていたら、その時点で捨てる。
"""
import html as _html
import os, re, time

# 1枚に許す大きさ。これを超えるものは、たいてい壊れているか繰り返している
MAX_BYTES = 300_000

# 外へ出ていく記述。1つでもあれば置かない。
#   ・手元だけで動くのが、このカーネルの決めごと
#   ・知らないところへ通信するページを、勝手に机の上に置かない
_OUTBOUND = re.compile(
    r"""(?ix)
    src\s*=\s*["']?https?://      |
    href\s*=\s*["']?https?://     |
    @import\s+url\(\s*["']?https?:// |
    \bfetch\s*\(                  |
    XMLHttpRequest                |
    WebSocket                     |
    navigator\.sendBeacon         |
    import\s*\(\s*["']https?://   |
    \bdocument\.cookie            |
    localStorage\.(?:setItem|getItem)\s*\(\s*["'](?:token|password)
    """)

# 作ってほしいと言われている言い方
_MAKE = re.compile(
    r"(作って|作成して|つくって|создать|作れる|書いて|用意して|"
    r"組んで|生成して|こしらえて)")
# ページとして作るのが自然なもの
def _game_words():
    """自分で組めるゲームの呼び名。gameparts の札から取る。
    ここを二重に書くと、片方だけ増やしたときにずれる"""
    try:
        import gameparts
        return list(gameparts.NAMES)
    except Exception:
        return []


_PAGEY = re.compile(
    r"(ゲーム|げーむ|HTML|html|ページ|ホームページ|サイト|画面|"
    r"アプリ|ツール|表|グラフ|時計|電卓|メモ帳|カレンダー|"
    r"テトリス|オセロ|将棋|囲碁|パズル|クイズ|すごろく|迷路|"
    r"スライド|名簿|一覧表|チェック|"
    + "|".join(re.escape(w) for w in _game_words() or ["__none__"]) + ")")


# 本物のフォルダを指す言葉。これが入っていたら「作り話のページ」ではない
def _honmono(text):
    """カーネルに聞いて、本物の場所やパスを指しているか調べる

    ここは一度ひどく間違えた。
       「デスクトップの一覧をHTMLで作って」
    が、この関数で True になり、先生に丸投げされ、先生は
    「デスクトップPC の商品カタログ」を でっち上げた（DELL XPS 149,800円…
    すべて実在しない）。本物のフォルダを一覧にする部品が、
    カーネルの中にちゃんとあるのに、そこへ届かなかった。

    カーネルは、この文から {動作:HTML, 場所:Desktop} を
    ちゃんと引けている。場所やパスが引けたなら、
    それは「実物の話」なので、ページ作りに回してはいけない。
    """
    try:
        import kernel
        slots = kernel.draw_cards(text)
    except Exception:
        return False
    return bool(slots.get("場所") or slots.get("パス") or slots.get("行き先"))


def wants_page(text):
    """「◯◯を作って」で、ページとして作るのが自然か"""
    if not (_MAKE.search(text) and _PAGEY.search(text)):
        return False
    if _honmono(text):
        return False          # 実物の話。作り話にしてはいけない
    return True


SYSTEM = (
    "あなたは、1枚で完結する HTML ページを書く職人です。\n"
    "決めごと:\n"
    "・出力は HTML だけ。説明文も、```などの囲みも、一切つけない\n"
    "・<!doctype html> から </html> まで、1枚で完結させる\n"
    "・CSS も JavaScript も、そのページの中に直接書く\n"
    "・外部のURL、CDN、画像リンク、通信は一切使わない（手元だけで動くこと）\n"
    "・日本語で表示する\n"
    "・遊べる／使えるところまで、ちゃんと動くものにする\n"
    "・画面が暗い配色でも明るい配色でも、文字が読めるようにする\n"
)


def _strip_fence(t):
    """```html ... ``` の囲みが付いてきたら外す"""
    t = t.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t)
    return t.strip()


def check(code):
    """置いてよいか、こちらで確かめる。だめなら理由を返す

    【並び順を直した経緯】
    はじめは「短すぎ」を先に見ていた。そのせいで、
    短くて危ない物（fetch や document.cookie を1行だけ書いた物）が
    「中身がほとんど空です」で弾かれ、
    危ないと気づいて弾いたのか、短くて弾いたのか区別がつかなかった。
    通ってはいたが、理由が嘘だった。
    危ないかどうかを、いちばん先に見る。
    """
    if not code:
        return "中身がありません"
    m = _OUTBOUND.search(code)
    if m:
        return f"外へつなぐ記述が混ざっています（{m.group(0)[:30]}）"
    if len(code.encode("utf-8")) > MAX_BYTES:
        return f"大きすぎます（{len(code.encode('utf-8')):,} バイト）"
    if len(code) < 80:
        return "中身がほとんど空です"
    low = code.lower()
    if "<html" not in low and "<!doctype" not in low:
        return "HTML の形になっていません"
    return None


# 題として使わない言い回し。ここを削ると読める名前になる
_TRIM = re.compile(
    r"(を|の)?(作って|作成して|つくって|書いて|用意して|組んで|生成して|"
    r"こしらえて|ください|下さい|ほしい|欲しい)\s*$")


def _title_of(request, code):
    """ファイルの名前を決める。

    前は言われた文をそのまま30文字で切っていたので、
    「落ちてくるブロックを、そろったら消すゲームを作っ.html」
    のような、途中で切れた名前になっていた
    """
    m = re.search(r"<title>(.*?)</title>", code, re.I | re.S)
    t = m.group(1).strip() if (m and m.group(1).strip()) else request
    t = re.sub(r"[\\/:*?\"<>|\n]", "", t).strip()
    for _ in range(3):
        t2 = _TRIM.sub("", t).strip("、。 　")
        if t2 == t:
            break
        t = t2
    if len(t) > 24:
        # 長いときは、読点で切れるところまで
        cut = t[:24]
        if "、" in cut:
            cut = cut[:cut.rindex("、")]
        t = cut
    return t or "ページ"


def _uniq(path):
    """上書きしない。同じ名前があれば番号を付ける"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    for i in range(2, 200):
        p = f"{stem} {i}{ext}"
        if not os.path.exists(p):
            return p
    raise Exception("名前が決まりません")


def ask_teacher(request, teachers, timeout=90, use_nvidia=True):
    """先生に中身を書いてもらう。前から順に試す。

    戻り値: (コード, 誰が書いたか) ／ だめなら例外
    """
    prompt = (f"つぎのものを、1枚で完結する HTML ページとして書いてください。\n\n"
              f"　{request}\n\n"
              f"HTML だけを返してください。")
    errs = []

    # 先生が全員 手元(local:)なら、NVIDIA には出ない。
    #   ここを見ていなかったので、/model local:main に替えても
    #   **鍵があるかぎり必ず NVIDIA に先に出ていた**（2026-09-06 に気づいた）。
    #   「完全に手元で閉じる」と言うためには、ここで止める必要がある。
    if teachers and all(str(t).startswith("local:") for t in teachers):
        use_nvidia = False

    # 手元の先生は 20 t/s 級。3,000 字級の HTML は 90 秒では書き切れない。
    # 実測 32.8 秒／1,162 字なので、3,000 字なら 85 秒。余裕を見て 240 秒。
    if teachers and any(str(t).startswith("local:") for t in teachers):
        timeout = max(timeout, 240)

    # ① NVIDIA（鍵があれば。無ければ静かに飛ばす）
    if use_nvidia:
        try:
            import nvidia
            if nvidia.key():                      # ダイアログが出ないときだけ
                code = _strip_fence(nvidia.ask(prompt, model="code",
                                               system=SYSTEM, timeout=timeout,
                                               max_tokens=8000))
                bad = check(code)
                if not bad:
                    return code, "NVIDIA(code)"
                errs.append(f"NVIDIA: {bad}")
        except Exception as e:
            errs.append(f"NVIDIA: {e}")

    # ② いつもの先生
    try:
        import teachers as T
    except Exception as e:
        raise Exception(f"先生を呼べません（{e}）")
    for who in (teachers or T.available()):
        try:
            r = T.ask_one(who, prompt, SYSTEM, timeout=timeout)
        except Exception as e:
            errs.append(f"{who}: {e}")
            continue
        if r.get("error"):
            errs.append(f"{who}: {r['error']}")
            continue
        code = _strip_fence(r.get("text") or "")
        bad = check(code)
        if bad:
            errs.append(f"{who}: {bad}")
            continue
        return code, who
    raise Exception("どの先生も、置ける形のものを返しませんでした\n    "
                    + "\n    ".join(errs[:4]))


def make_self(request, where=None):
    """先生に頼らず、カーネルが自分で組み立てる。

    ファイル操作を「さがす→しぼる→かぞえる」と組むのと同じやり方で、
    ゲームも「ばんめん→おちもの→まわす→そろい消し」と組む。
    組める部品が見つからなければ None を返す（そのとき先生に回る）
    """
    import gameparts
    names, how = gameparts.pick(request)
    if not names:
        return None
    title = _title_of(request, "")
    code, order = gameparts.assemble(names, title=title)
    bad = check(code)
    if bad:                       # 自分で作った物も、同じように確かめる
        raise Exception(f"自分で組んだが、置けない形だった: {bad}")
    where = where or os.path.join(os.path.expanduser("~"), "Desktop")
    os.makedirs(where, exist_ok=True)
    path = _uniq(os.path.join(where, f"{_title_of(request, code)}.html"))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(code)
    os.replace(tmp, path)
    return {"パス": path, "誰": "カーネル（自分で組み立て）",
            "バイト": len(code.encode("utf-8")),
            "手順": order, "選び方": how,
            "題": _title_of(request, code)}


def make(request, where=None, teachers=None, timeout=90, self_first=True):
    """作って、確かめて、置く。

    ① まず自分で組めるか試す（部品の組み合わせ）
    ② 組めなければ先生に書いてもらう
    戻り値: {"パス", "誰", "バイト", "ミリ秒", "題"}
    """
    t0 = time.time()
    if self_first:
        try:
            r = make_self(request, where)
            if r:
                r["ミリ秒"] = round((time.time() - t0) * 1000)
                return r
        except Exception:
            pass                  # 自分で無理なら、黙って先生に回る
    code, who = ask_teacher(request, teachers, timeout)
    where = where or os.path.join(os.path.expanduser("~"), "Desktop")
    os.makedirs(where, exist_ok=True)
    title = _title_of(request, code)
    path = _uniq(os.path.join(where, f"{title}.html"))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(code)
    os.replace(tmp, path)
    return {"パス": path, "誰": who, "バイト": len(code.encode("utf-8")),
            "ミリ秒": round((time.time() - t0) * 1000), "題": title}


if __name__ == "__main__":
    import sys
    req = " ".join(sys.argv[1:]) or "テトリス"
    print(f"「{req}」を作ります…")
    r = make(req)
    print(f"  できました: {r['パス']}")
    print(f"  書いた人  : {r['誰']} ／ {r['バイト']:,} バイト ／ {r['ミリ秒']} ミリ秒")
