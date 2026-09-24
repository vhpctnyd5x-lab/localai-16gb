#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
settings.py -- 設定と、スラッシュコマンド

  「/」で始まる行は、相棒への話しかけではなく、道具への指示として扱う。
  Claude Code などでおなじみの並びに、できるだけ合わせてある。

  設定は settings.json に置く。手で開いて書き換えてもよい。
"""
import re as _re
import os, json, shutil, datetime, unicodedata


def _w(text, n):
    """全角を2文字ぶんとして数え、幅 n に揃える（表がガタガタにならない）"""
    text = str(text)
    w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)
    return text + " " * max(0, n - w)

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "settings.json")

# 既定値。ここに無いキーは /set で作れない（打ち間違いを弾くため）
DEFAULTS = {
    "モード":       "本番",      # 本番 が既定。練習は試験用に残してあるだけ
    "詳しく":       False,       # 手順を全部見せるか
    "確認":         False,       # 動かす前に一言たずねるか（既定は聞かない）
    "辞書":         True,        # 語義の質問を手元の辞書で答えるか
    "先生":         ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"],
    "先生を使う":   True,        # False なら完全に手元だけで動く
    "先生と直接":   False,       # True なら、打った言葉が そのまま先生に行く
    "覚える":       True,        # 会話を memory.db に残すか
    "会話の長さ":   8,           # 何往復ぶんを毎回の材料にするか
    "考える様子":   True,        # 組み立ての途中経過を見せるか
    "育てる":       True,        # 使いながらカードを増やすか
    "じっくり":     False,       # はじめから長く考えるか（測ったら、人数より時間が効いた）
    "考える深さ":   -1,          # -1=おまかせ / 0さっと 1ふつう 2じっくり 3とことん
    "読むだけ":     False,       # true なら、ものを動かす部品を一切使わない
}

_HELP = {
    "モード":     "本番 = 本物のフォルダ（既定）/ 練習 = sandbox。練習は試験用",
    "詳しく":     "true にすると、返事に先生の名前と時間も出す",
    "確認":       "既定は false（下見が通ったらそのまま実行）。true にすると毎回たずねる",
    "辞書":       "false にすると、語義も先生に聞きに行く",
    "先生":       "相談する外部モデル。前から順に試す",
    "先生を使う": "false なら外に一切つながない（完全オフライン）",
    "先生と直接": "true にすると、カーネルを通さず 先生とそのまま話す（/sensei ずっと と同じ）",
    "覚える":     "false なら会話を記録に残さない",
    "会話の長さ": "文脈として渡す直近のやりとりの数",
    "考える様子": "false にすると、組み立ての途中経過を出さない",
    "育てる":     "true なら、うまくいった表引きをカードとして覚えていく",
    "じっくり":   "true なら最初から6倍長く考える。false でも、行き詰まれば自動で長考する",
    "考える深さ": ("手元のモデルの 考える量。-1=おまかせ(既定) 0=さっと 1=ふつう 2=じっくり 3=とことん。"
                  "★ 深くしても RAM は増えない（増えるのは時間だけ）。"
                  "実測 120問: 深さ0 で 55%（1段100% / 2段37.5% / 3段27.5%）"),
    "読むだけ":   "true なら、数える・見せるだけ。移動も削除も一切しない",
}


def load():
    d = dict(DEFAULTS)
    if os.path.exists(PATH):
        try:
            d.update(json.load(open(PATH, encoding="utf-8")))
        except Exception:
            pass
    return d


# 本番モードは保存しない。一度切り替えたきり、次の起動でも本物のフォルダを
# 触り続けてしまうため。起動のたびに必ず練習から始まる
#
# 「先生と直接」も同じ理由で保存しない。入れっぱなしで忘れると、
# **ファイルを触る命令が どれも通らなくなる**（全部 先生に流れてしまう）。
# 見たいときに入れて、次に開いたときは ふつうに戻っている、が安全。
NEVER_SAVE = {"モード", "先生と直接"}


def save(d):
    keep = {k: v for k, v in d.items()
            if k in DEFAULTS and k not in NEVER_SAVE}
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(keep, f, ensure_ascii=False, indent=2)


def _parse(key, raw):
    """文字列を、そのキーにふさわしい型に直す"""
    cur = DEFAULTS[key]
    if isinstance(cur, bool):
        if raw.lower() in ("true", "on", "はい", "1", "yes"):  return True
        if raw.lower() in ("false", "off", "いいえ", "0", "no"): return False
        raise ValueError("true か false で答えてください")
    if isinstance(cur, int):
        return int(raw)
    if isinstance(cur, list):
        return [x.strip() for x in raw.split(",") if x.strip()]
    return raw


# ============================================================
# コマンド一覧（/help で出るもの）
# ============================================================
COMMANDS = [
    ("/help",          "このいちらん"),
    ("/settings",      "いまの設定を全部見る"),
    ("/set <名前> <値>", "設定をひとつ変える  例: /set 詳しく true"),
    ("/model",         "相談する先生（外部モデル）を見る・変える"),
    ("/sensei <質問>", "先生に じかに聞く。 ずっと で話しっぱなし / くらべる で見比べ"),
    ("/dougu <質問>",  "先生に道具を使わせて答えさせる（調べる・見る・計算する）"),
    ("/persona",       "名前・口調・説明を見る・変える"),
    ("/mode",          "練習 ⇄ 本番 を切り替える"),
    ("/diff <A> <B>",  "2つのファイルの、どの行が変わったかを見る"),
    ("/see [語]",      "画面をよむ。語を書くと、その文字がどこにあるかを言う"),
    ("/nv <質問>",     "NVIDIA の API に聞く"),
    ("/深さ [0-3]",    "考える深さ。0さっと 1ふつう 2じっくり 3とことん"),
    ("/verbose",       "詳しく表示を on/off"),
    ("/memory",        "覚えていることを見る"),
    ("/forget",        "覚えていることを消す（会話の記録も）"),
    ("/history",       "したことの記録（動かしたファイル）を見る"),
    ("/undo",          "直前に動かしたものを元に戻す"),
    ("/note",          "覚えた手順（ノート）を見る"),
    ("/cards",         "カードを引いてみる  例: /cards 机の上の写真"),
    ("/dict <語>",     "手元の辞書を引く（外に出ない）"),
    ("/wiki <語>",     "Wikipedia を引く（外に出る）"),
    ("/shiryo <語>",   "資料を調べる（手元→集めた記事→Wikipedia→NVIDIA の順）"),
    ("/chrome",        "Chrome の様子を見る  tabs / now / text"),
    ("/walk <語>",     "辞書を辿って広げる  例: /walk 動物"),
    ("/grown",         "使いながら覚えたカードを見る"),
    ("/bg",            "裏で辞書を辿り続ける係  start / stop / status"),
    ("/candidates",    "裏の係が見つけた札の候補を見る・採る"),
    ("/parts",         "ファイルを扱う部品のいちらん"),
    ("/machine",       "パソコン操作のいちらん（時刻・電池・音量など）"),
    ("/stats",         "手元にあるものの大きさ・数"),
    ("/doctor",        "ちゃんと動く状態か点検する"),
    ("/reset",         "練習用フォルダを作り直す"),
    ("/clear",         "画面と、今の会話の流れを消す"),
    ("/quit",          "おわる"),
]


# コマンドの名前として使える形。/help /set /bg など、英数字だけ
_CMDLIKE = _re.compile(r"^/[A-Za-z][A-Za-z0-9_-]{0,20}$")

# ★ 日本語のコマンド名は、上の形（英数字だけ）に当たらないので通らない。
#   広げると「/写真」のようなフォルダ名まで拾いかねないので、
#   **知っているものだけ**を名指しで通す。
_NIHONGO_CMD = {"/深さ", "/道具", "/設定", "/点検"}


def is_command(text):
    """スラッシュコマンドかどうか。

    ファイルのパスをコマンドと取り違えないこと。
    「/Users/…/はりつけ/cat_s.jpg には何が写ってる？」を投げたら
    「/users/<user>/library/application は知らないコマンドです」と
    返ってきた。/ で始まるものを全部コマンド扱いしていたのが原因。

    ・空白より前が、コマンドらしい形（英数字だけ・スラッシュは1つ）
    ・実在するパスでない
    この2つを両方みたす時だけ、コマンドとみなす
    """
    text = (text or "").strip()
    if not text.startswith("/") or text.startswith("//"):
        return False
    head = text.split()[0]
    if os.path.exists(head) or os.path.exists(os.path.expanduser(head)):
        return False
    if head in _NIHONGO_CMD:
        return True
    return bool(_CMDLIKE.match(head))


def run(text, ctx):
    """スラッシュコマンドを実行する。

    ctx は main.py が渡す入れ物：
      {"設定":dict, "記憶":Memory, "会話":list, "kernel":module}
    戻り値 "quit" なら終了、"clear" なら会話を流す、それ以外は None
    """
    parts = text.strip().split()
    cmd, args = parts[0].lower(), parts[1:]
    S = ctx["設定"]

    def p(*a): print(*a)

    # ---------------- 基本 ----------------
    if cmd in ("/help", "/h", "/?"):
        p("\n  使えるコマンド")
        p("  " + "─" * 52)
        for c, d in COMMANDS:
            p(f"  {_w(c,20)}{d}")
        p("\n  「/」で始まらない行は、ふつうの話しかけとして扱います。")
        return

    if cmd == "/settings":
        p("\n  いまの設定  （ファイル: settings.json）")
        p("  " + "─" * 52)
        for k in DEFAULTS:
            v = S.get(k, DEFAULTS[k])
            v = ", ".join(v) if isinstance(v, list) else v
            mark = " " if S.get(k) == DEFAULTS[k] else "*"
            p(f"  {mark}{_w(k,14)}{v}")
            p(f"                {_HELP.get(k,'')}")
        p("\n  * が付いているものは、既定から変えてあるものです。")
        p("  変えるとき:  /set 詳しく true")
        return

    if cmd in ("/nvidia",):
        cmd = "/nv"
    if cmd in ("/設定",):
        cmd = "/settings"
    if cmd in ("/点検",):
        cmd = "/doctor"

    if cmd in ("/深さ", "/fukasa", "/effort"):
        # ★ 「考える深さ」を、打ちやすい形で出し入れする。
        #   設定の /set 考える深さ 2 と同じことをしている。
        try:
            from teachers import FUKASA
        except Exception:
            FUKASA = {0: {"名": "さっと"}, 1: {"名": "ふつう"},
                      2: {"名": "じっくり"}, 3: {"名": "とことん"}}
        ima = int(S.get("考える深さ", -1))
        if not args:
            p("\n  考える深さ ── 手元のモデルに どれだけ考えさせるか")
            p("  ★ 深くしても メモリは増えません。増えるのは時間だけです。")
            p("")
            p("  %s -1  おまかせ（問いを見て 0 か 2 を自分で決める）"
              % ("→" if ima == -1 else "  "))
            for n in sorted(FUKASA):
                shirushi = "→" if n == ima else "  "
                p("  %s %2d  %s" % (shirushi, n, FUKASA[n]["名"]))
            p("")
            p("  実測（120問・2ビットのまま・GPUで測定）:")
            p("    深さ0 さっと   … 66.7%（1段 100% / 2段 52.5% / 3段 47.5%）")
            p("    深さ2 じっくり … 98.3%（1段 100% / 2段 100%  / 3段 95.0%）")
            p("    おまかせ       … 98.3% を **75%の時間** で")
            p("  ★ ビットを2倍(Q4_K_M)にしても点は上がらなかった。効くのは深さだけ。")
            p("")
            p("  変えるとき:  /深さ 2")
            return
        try:
            n = int(args[0])
        except ValueError:
            p("  0 から 3 の数で言ってください。")
            return
        if n != -1 and n not in FUKASA:
            p("  -1（おまかせ）から 3 の間で言ってください。")
            return
        S["考える深さ"] = n
        save(S); _apply(S, ctx)
        p("  考える深さを %d（%s）にしました。"
          % (n, "おまかせ" if n == -1 else FUKASA[n]["名"]))
        if n >= 2:
            p("  ★ 深いぶん 返事は遅くなります。急ぐときは /深さ 0 に戻してください。")
        return

    if cmd == "/set":
        if len(args) < 2:
            p("  使い方: /set <名前> <値>    名前は /settings で見られます")
            return
        key, raw = args[0], " ".join(args[1:])
        if key not in DEFAULTS:
            p(f"  「{key}」という設定はありません。/settings で確かめてください。")
            return
        try:
            S[key] = _parse(key, raw)
        except ValueError as e:
            p(f"  {e}")
            return
        save(S)
        _apply(S, ctx)
        p(f"  {key} を {S[key]} にしました。")
        return

    if cmd == "/model":
        if args:
            S["先生"] = [x.strip() for x in " ".join(args).replace(",", " ").split()]
            save(S); p(f"  先生を {S['先生']} にしました。")
            return
        p("\n  いま相談する先生（前から順に試します）")
        for i, m in enumerate(S["先生"], 1):
            p(f"    {i}. {m}")
        try:
            from teachers import available
            p("\n  使える先生")
            for m in available():
                p(f"    - {m}")
        except Exception:
            pass
        p("\n  変えるとき:  /model groq:openai/gpt-oss-20b")
        return

    # ---------------- 先生に道具を使わせる ----------------
    if cmd in ("/dougu", "/道具"):
        import sensei, dougu
        toi = " ".join(args).strip()
        if not toi:
            p("\n  先生に道具を使わせて答えさせます。")
            p("  使える道具: " + " / ".join(dougu.DOUGU))
            p("\n  例:  /dougu かたつむりは何文字ですか")
            p("       /dougu 空き容量はどれくらい残っていますか")
            p("       /dougu デスクトップに何がありますか")
            p("\n  ★ 跡が残る道具は 一つも入れていません（読むだけ＋使い捨て部屋のコード）")
            return
        if not sensei.youi(S.get("先生") or [], p):
            p("  聞ける先生が居ません。"); return
        p("\n  道具を使って調べます…")
        r = dougu.mawasu(toi, S, iu=p)
        p("")
        if r.get("error") and not r.get("答え"):
            p("  だめでした: %s" % r["error"]); return
        p("  ── 道具を %d 回使いました ／ %.1f 秒" % (r["回数"], r["ミリ秒"] / 1000.0))
        p(sensei._oru(r["答え"]))
        return

    # ---------------- 先生と じかに話す ----------------
    if cmd == "/sensei":
        import sensei
        rireki = ctx.setdefault("先生の話", [])
        sub = args[0] if args else ""

        def _temoto_wo_youi(tachi, iu):
            # 判定は sensei.youi に1箇所だけ置いてある（二重に持たない）
            return sensei.youi(tachi, iu)
            ok, shirase = sv.moderu_youi(hoshii[0])
            if not ok:
                iu("  手元のモデルが用意できません: %s" % shirase)
                return [t for t in tachi if not str(t).startswith("local:")]
            if shirase:
                iu("  " + shirase)
            return list(tachi)

        if sub in ("ずっと", "on"):
            S["先生と直接"] = True; save(S)
            p("\n  ここからは、打った言葉が そのまま先生に行きます。")
            p("  （カーネルのカードも部品もノートも 通りません）")
            p("  もどすとき:  /sensei やめる")
            return
        if sub in ("やめる", "off"):
            S["先生と直接"] = False; save(S)
            p("\n  ふつうに戻しました。"); return
        if sub in ("わすれる", "clear"):
            rireki.clear(); p("\n  先生との話の流れを 忘れました。"); return

        if sub in ("しらべて", "調べて", "rag"):
            toi = " ".join(args[1:]).strip()
            if not toi:
                p("\n  例:  /sensei しらべて 都道府県で名前に「山」が入るものは？"); return
            if not _temoto_wo_youi(S.get("先生") or [], p):
                p("  聞ける先生が居ません。"); return
            p("\n  思い出させず、調べてから答えます…")
            r = sensei.shirabete(toi, S, iu=p)
            if r.get("error"):
                p("  だめでした: %s" % r["error"]); return
            p("")
            p("  ── %s ／ 出典: %s ／ %.1f 秒"
              % (r["誰"], r["出典"], r["ミリ秒"] / 1000.0))
            p(sensei._oru(r["答え"]))
            return

        if sub in ("くらべる", "vs"):
            toi = " ".join(args[1:]).strip()
            if not toi:
                p("\n  例:  /sensei くらべる 円周率を10桁"); return
            tachi = ["local:main", "groq:openai/gpt-oss-120b"]
            tachi = _temoto_wo_youi(tachi, p)
            if not tachi:
                p("  くらべる相手が居ません。"); return
            p("\n  同じ問いを %d人に投げます（%s）…" % (len(tachi), toi[:40]))
            for r in sensei.kuraberu(toi, tachi):
                p("")
                if r["error"]:
                    p("  ── %s\n  答えませんでした: %s" % (r["誰"], r["error"]))
                else:
                    p("  ── %s ／ %.1f 秒 ／ %d 字（%s 字/秒）"
                      % (r["誰"], r["ミリ秒"]/1000.0, len(r["答え"]), r["字/秒"]))
                    p(sensei._oru(r["答え"]))
            return

        toi = " ".join(args).strip()
        if not toi:
            ima = S.get("先生", [])
            p("\n  いまの先生: %s" % (", ".join(ima) if ima else "決まっていません"))
            p("  直接はなす: %s" % ("はい" if S.get("先生と直接") else "いいえ"))
            p("  流れ: %d 往復ぶん覚えています" % (len(rireki)//2))
            p("\n  使いかた")
            p("    /sensei 富士山の高さは？        いま設定の先生に じかに聞く")
            p("    /sensei しらべて <質問>          **調べてから**答える（嘘が出ない）")
            p("    /sensei くらべる <質問>          手元 と Groq を並べて見る")
            p("    /sensei ずっと                   打った言葉が そのまま先生に行く")
            p("    /sensei やめる / わすれる")
            p("\n  じっくり考えさせたいときは  /model local:main+think")
            return

        if not _temoto_wo_youi(S.get("先生") or [], p):
            p("  聞ける先生が居ません。"); return
        r = sensei.kiku(toi, S, rireki)
        if not r["error"]:
            rireki.append({"who": "user", "文": toi})
            rireki.append({"who": "bot",  "文": r["答え"]})
            del rireki[:-40]
        p("")
        p(sensei.miseru(r))
        return

    if cmd == "/persona":
        import json as _j
        pp = os.path.join(HERE, "persona.json")
        d = _j.load(open(pp, encoding="utf-8"))
        if len(args) >= 2 and args[0] in d:
            d[args[0]] = " ".join(args[1:])
            _j.dump(d, open(pp, "w", encoding="utf-8"),
                    ensure_ascii=False, indent=2)
            p(f"  {args[0]} を書き換えました。次に起動したときから効きます。")
            return
        p("\n  いまの人格  （ファイル: persona.json）")
        p("  " + "─" * 52)
        for k, v in d.items():
            p(f"  {k}:")
            p(f"    {v}")
        p("\n  変えるとき:  /persona 口調 ていねいに、3文まで")
        return

    if cmd == "/mode":
        want = args[0] if args else ("本番" if S["モード"] == "練習" else "練習")
        if want not in ("練習", "本番"):
            p("  /mode 練習   か   /mode 本番"); return
        S["モード"] = want; save(S); _apply(S, ctx)
        if want == "本番":
            p("  ■ 本番モード。本物のフォルダを触ります。")
            p("     ものを動かす手順は、必ず仮想で確かめてから実行します（関所つき）。")
            if S.get("確認"):
                p("     設定「確認」が true なので、動かす前に毎回たずねます。")
            p("     （この切り替えは保存しません。次に起動したときは本番に戻ります）")
        else:
            p("  ■ 練習モード（試験用）。sandbox の中だけで動きます。")
        return

    if cmd == "/verbose":
        S["詳しく"] = not S["詳しく"] if not args else _parse("詳しく", args[0])
        save(S); p(f"  詳しく表示を {'on' if S['詳しく'] else 'off'} にしました。")
        return

    # ---------------- 記憶・記録 ----------------
    if cmd in ("/memory", "/mem"):
        m = ctx.get("記憶")
        if m is None:
            p("  記憶がありません。"); return
        f = m.facts()
        p(f"\n  覚えていること（{len(f)} 件）")
        p("  " + "─" * 52)
        for k, v in f.items():
            p(f"  {k}: {v}")
        if not f:
            p("  （まだ何も）")
        return

    if cmd == "/forget":
        m = ctx.get("記憶")
        if not args or args[0] != "ぜんぶ":
            p("  本当に全部消すなら:  /forget ぜんぶ")
            return
        if m is not None:
            m.wipe()
        ctx["会話"].clear()
        p("  覚えていたことを全部消しました。")
        return

    if cmd == "/history":
        j = os.path.join(HERE, "journal.jsonl")
        if not os.path.exists(j):
            p("  まだ何も動かしていません。"); return
        recs = [json.loads(l) for l in open(j, encoding="utf-8") if l.strip()]
        n = int(args[0]) if args and args[0].isdigit() else 10
        p(f"\n  したこと（新しい順に {min(n,len(recs))} 件）")
        p("  " + "─" * 52)
        for r in list(reversed(recs))[:n]:
            mark = "（取り消し済）" if r.get("undone") else ""
            p(f"  {r['時刻']}  {r.get('note','')}  {r['件数']} 個 {mark}")
            for it in r["items"][:5]:
                p(f"      {it['名前']}:  {os.path.dirname(it['from'])}"
                  f"  →  {os.path.dirname(it['to'])}")
            if r["件数"] > 5:
                p(f"      … ほか {r['件数']-5} 個")
        return

    if cmd == "/undo":
        from safety import undo_last
        # いま本番なら本物の記録だけ、練習中なら練習用だけを戻す。
        # 混ぜていたので、本物の操作のあとに bench.py を流すと
        # 本物の取り消しに届かなくなっていた
        p(undo_last(os.path.join(HERE, "journal.jsonl"),
                    note=("本物" if S["モード"] == "本番" else "練習用")))
        return

    if cmd == "/note":
        n = os.path.join(HERE, "notebook_real.json" if S["モード"] == "本番"
                         else "notebook.json")
        if not os.path.exists(n):
            p("  まだ何も覚えていません。"); return
        nb = json.load(open(n, encoding="utf-8"))
        p(f"\n  覚えた手順（{len(nb)} 通り・{os.path.basename(n)}）")
        p("  " + "─" * 52)
        for shape, v in sorted(nb.items(), key=lambda x: -x[1]["回数"]):
            p(f"  {shape}")
            p(f"      {' → '.join(v['手順'])}   （{v['回数']} 回使った）")
        return

    # ---------------- のぞき込む ----------------
    if cmd == "/cards":
        if not args:
            p("  使い方: /cards 机の上の去年の写真"); return
        k = ctx["kernel"]
        p("")
        s = k.draw_cards(" ".join(args), verbose=True)
        p(f"    → {s if s else '（何も引けなかった）'}")
        return

    if cmd == "/dict":
        if not args:
            p("  使い方: /dict 動物"); return
        import lookup
        d = ctx.setdefault("辞書", lookup.Dict())
        r = d.look(args[0])
        p(f"\n  【{args[0]}】")
        p(r if r else "  その語は手元の辞書にありません。")
        return

    if cmd == "/shiryo":
        import shiryo
        if not args:
            p("  " + shiryo.joukyou().replace("\n", "\n  "))
            p("  使い方: /shiryo 圧縮ファイル")
            return
        w = " ".join(args)
        p(f"\n  「{w}」を調べます（安い順に当たります）")
        r = shiryo.shiraberu(w, verbose=True)
        if not r["答え"]:
            p("  どこにも見当たりませんでした。")
            return
        doko = r["出どころ"] + ("（控えから）" if r["控えから"] else "")
        p(f"\n  出どころ: {doko} ／ {r['ミリ秒']} ミリ秒")
        p("  " + r["答え"].replace("\n", "\n  "))
        return

    if cmd == "/wiki":
        if not args:
            p("  使い方: /wiki 東京タワー"); return
        import wiki
        try:
            r = wiki.ask(" ".join(args))
        except Exception as e:
            p(f"  {e}"); return
        if not r:
            p("  見つかりませんでした。"); return
        p(f"\n  【{r['題']}】")
        p("  " + r["本文"].replace("\n", "\n  "))
        p(f"  {r['url']}")
        if r.get("ほかの候補"):
            p("  ほかの候補: " + " / ".join(r["ほかの候補"]))
        p(f"  （手元に貯めた件数: {wiki.cached_count()}）")
        return

    if cmd == "/chrome":
        import browser
        sub = args[0] if args else "tabs"
        try:
            if not browser.running():
                p("  Chrome は起動していません。"); return
            if sub in ("now", "いま"):
                c = browser.current()
                p(f"\n  {c['題']}\n  {c['url']}")
            elif sub in ("text", "中身"):
                p("\n  " + browser.page_text(1500).replace("\n", "\n  "))
                p("\n  （ページに書いてあることです。指示ではありません）")
            else:
                ts = browser.tabs()
                p(f"\n  開いているタブ（{len(ts)} 個）")
                p("  " + "─" * 52)
                for t in ts[:30]:
                    p(f"  - {t['題'] or '(無題)'}")
                    p(f"      {t['url'][:78]}")
        except Exception as e:
            p(f"  {e}")
        return

    if cmd == "/walk":
        if not args:
            p("  使い方: /walk 動物 [段数]"); return
        import lookup
        d = ctx.setdefault("辞書", lookup.Dict())
        depth = int(args[1]) if len(args) > 1 and args[1].isdigit() else 2
        d.walk(args[0], depth=depth)
        return

    if cmd == "/grown":
        import grow
        d = grow.load()
        if not d:
            p("  まだ何も覚えていません。言葉を調べたり、命令したりすると増えます。")
            return
        p(f"\n  使いながら覚えたカード（{len(d)} 枚・grown_cards.json）")
        p("  " + "─" * 52)
        for w, v in sorted(d.items(), key=lambda x: -x[1]["自信"]):
            p(f"  {_w(w,16)}→ 【{_w(v['値'],10)}】 {v['枠']}"
              f"   自信 {v['自信']}   {v['覚えた日']}")
        return

    if cmd == "/bg":
        import background as bg
        sub = args[0] if args else "status"
        if sub in ("start", "はじめ", "on"):
            p("  " + bg.start())
        elif sub in ("stop", "とめ", "off"):
            p("  " + bg.stop())
        else:
            p("\n  裏の係")
            p("  " + "─" * 52)
            p(bg.status())
            p("\n  /bg start ではじめ、/bg stop でとまります。")
        return

    if cmd == "/candidates":
        import background as bg, grow, json as _j
        cand = bg._read(bg.CAND, {})
        if args and args[0] in ("採る", "採用"):
            if len(args) < 2:
                p("  使い方: /candidates 採る <語> [<語> …]  /  /candidates 採る ぜんぶ")
                return
            take = list(cand) if args[1] == "ぜんぶ" else args[1:]
            n = 0
            for w in take:
                v = cand.get(w)
                if not v:
                    p(f"  「{w}」は候補にありません"); continue
                if grow.remember(w, v["枠"], v["値"], 1.0, "本人が採った"):
                    cand.pop(w, None); n += 1
            bg._write(bg.CAND, cand)
            p(f"  {n} 枚を札にしました。")
            return
        if args and args[0] in ("捨てる", "消す"):
            if len(args) > 1 and args[1] == "ぜんぶ":
                bg._write(bg.CAND, {}); p("  候補を全部捨てました。"); return
            for w in args[1:]:
                cand.pop(w, None)
            bg._write(bg.CAND, cand); p("  捨てました。"); return
        if not cand:
            p("  候補はまだありません。/bg start で裏の係を動かすと貯まります。")
            return
        n = int(args[0]) if args and args[0].isdigit() else 20
        p(f"\n  札の候補（{len(cand)} 件のうち {min(n,len(cand))} 件）")
        p("  " + "─" * 52)
        for w, v in list(cand.items())[:n]:
            p(f"  {_w(w,16)}→ 【{_w(v['値'],8)}】 根拠「{v['根拠']}」")
            p(f"    {' '*16}{v['説明']}")
        p("\n  採るとき  :  /candidates 採る 撮影 写真集")
        p("  捨てるとき:  /candidates 捨てる ぜんぶ")
        p("  ※ 勝手に札にはしません。まとめて採ると質が落ちます。")
        return

    if cmd == "/parts":
        k = ctx["kernel"]
        p(f"\n  使える部品（{len(k.PARTS)} 個）")
        p("  " + "─" * 52)
        for name, desc in sorted(k.parts_desc().items()):
            mark = "★" if name in k.DESTRUCTIVE else " "
            p(f"  {mark} {_w(name,16)}{desc}")
        p("\n  ★ が付いているものは、ものを動かします。")
        p("     聞かれているだけのときは、これらは最初から外されます。")
        return

    if cmd == "/machine":
        import machine
        rows = machine.describe()
        p(f"\n  パソコンの操作（{len(rows)} 個）")
        p("  " + "─" * 52)
        for name, doc, risky in rows:
            p(f"  {'★' if risky else ' '} {_w(name,20)}{doc}")
        p("\n  ★ は実際に何かを変えるもの。実行の前にたずねます。")
        p("  例:  いま何時？ / 電池は？ / 音量を30にして / メモを開いて / スクショ撮って")
        return

    if cmd == "/stats":
        p("\n  手元にあるもの")
        p("  " + "─" * 52)
        rows = [
            ("辞書（語の説明）",   os.path.join(HERE, "dict", "pages.jsonl")),
            ("辞書から数えた表",   os.path.join(HERE, "dict_cards.json")),
            ("抜いてきた表",       os.path.join(HERE, "jp_cards.json.bin")),
            ("覚えた手順",         os.path.join(HERE, "notebook.json")),
            ("辿ったつながり",     os.path.join(HERE, "bg_web.json")),
            ("したことの記録",     os.path.join(HERE, "journal.jsonl")),
        ]
        for label, path in rows:
            if os.path.exists(path):
                mb = os.path.getsize(path) / 1e6
                p(f"  {_w(label,20)}{mb:>8.1f} MB")
            else:
                p(f"  {_w(label,20)}{_w('（無し）',8)}")
        k = ctx["kernel"]
        p(f"  {_w('種火のカード',20)}{len(k.SEED):>8} 枚")
        p(f"  {_w('部品',20)}{len(k.PARTS):>8} 個")
        return

    if cmd == "/doctor":
        _doctor(ctx)
        return

    if cmd == "/reset":
        ctx["kernel"].make_demo()
        if args and args[0] in ("ぜんぶ", "全部"):
            for f in ("notebook.json", "policy.json"):
                q = os.path.join(HERE, f)
                if os.path.exists(q):
                    os.remove(q)
            p("  練習用フォルダと、覚えた手順の両方を作り直しました。")
        else:
            p("  練習用フォルダを作り直しました。"
              "（覚えた手順はそのまま。消すなら /reset ぜんぶ）")
        return

    if cmd == "/clear":
        ctx["会話"].clear()
        print("\033[2J\033[H", end="")
        p("  会話の流れを消しました。（覚えていることは残っています）")
        return

    if cmd == "/diff":
        if len(args) < 2:
            p("  使い方: /diff <前のファイル> <後のファイル>")
            return
        import difflook
        a2 = os.path.expanduser(args[0]); b2 = os.path.expanduser(args[1])
        rows = difflook.files(a2, b2)
        plus = sum(1 for m, _t in rows if m == "+")
        minus = sum(1 for m, _t in rows if m == "-")
        p(f"\n  {os.path.basename(a2)} → {os.path.basename(b2)}"
          f"   ＋{plus} 行 ／ −{minus} 行")
        p("  " + difflook.render(rows, 120).replace("\n", "\n  "))
        return

    if cmd == "/see":
        try:
            import eyes
        except Exception as e:
            p(f"  画面を見る道具がありません（{e}）"); return
        try:
            if args:
                w = " ".join(args)
                hits = eyes.find(w)
                if not hits:
                    p(f"  「{w}」は画面にありません"); return
                p(f"\n  「{w}」が {len(hits)} か所")
                for h in hits[:10]:
                    c = h["まんなか"]
                    p(f"    ({c['x']:>5},{c['y']:>5})  {h['文'][:50]}")
            else:
                d = eyes.look()
                p(f"\n  {len(d['文字'])} 個の文字が読めました"
                  f"（倍率 {d['倍率']}）\n")
                p("  " + d["全文"][:2000].replace("\n", "\n  "))
        except Exception as e:
            p(f"  できませんでした： {e}")
        return

    if cmd == "/nv":
        try:
            import nvidia
        except Exception as e:
            p(f"  NVIDIA を呼べません（{e}）"); return
        if not args:
            p(f"\n  呼び方: {nvidia.how() or '（使えません）'}")
            p(f"  モデル: {', '.join(nvidia.ALIASES)}")
            p("  ~/.nvidia.env に NVIDIA_API_KEY=… の1行を書くと、"
              "承認ダイアログ無しで使えます")
            return
        model = "fast"
        if args[0] in nvidia.ALIASES:
            model, args = args[0], args[1:]
        try:
            p("  " + nvidia.ask(" ".join(args), model=model)
              .replace("\n", "\n  "))
        except Exception as e:
            p(f"  できませんでした： {e}")
        return

    if cmd in ("/quit", "/exit", "/q"):
        return "quit"

    p(f"  「{cmd}」は知らないコマンドです。/help で一覧が見られます。")


def _apply(S, ctx):
    """設定を、実際に動いている側へ反映する"""
    ctx["kernel"].ROOT = "real" if S["モード"] == "本番" else None
    ctx["kernel"].THINK_HARD = bool(S.get("じっくり"))
    ctx["kernel"].ASK_BEFORE = bool(S.get("確認"))
    ctx["kernel"].READ_ONLY = bool(S.get("読むだけ"))
    # ★ 考える深さ は teachers 側の既定として渡す（環境変数で伝える）。
    #   先生名に +e2 を付けたときは そちらが勝つ。
    try:
        fukasa = int(S.get("考える深さ", -1))
    except (TypeError, ValueError):
        fukasa = 0
    os.environ["KERNEL_LOCAL_EFFORT"] = str(max(-1, min(3, fukasa)))
    # ★ 2026-09-12 に見つけた穴。chat.py の雑談は teachers.DEFAULT_PANEL（= Groq の雲の上のモデル）に
    #   聞いていて、設定の「先生: local:main」を **見ていなかった**。手元の頭脳が雑談に使われていなかった。
    #   → 設定の先生を teachers の既定にする。空なら手元だけ。
    try:
        import teachers as _T
        sensei = [str(t) for t in (S.get("先生") or []) if str(t).strip()]
        _T.DEFAULT_PANEL[:] = sensei or ["local:main"]
    except Exception:
        pass


def _doctor(ctx):
    """ちゃんと動く状態かを、ひとつずつ確かめる"""
    S = ctx["設定"]
    ok, ng = "  ✓", "  ✗"
    print("\n  点検")
    print("  " + "─" * 52)

    # 1) 手元だけで動く部分
    try:
        s = ctx["kernel"].draw_cards("机の上の去年の写真を数えて")
        good = s.get("場所") == "Desktop" and s.get("種類") == "画像"
        print(f"{ok if good else ng} {_w('カードを引く',22)}{s}")
    except Exception as e:
        print(f"{ng} {_w('カードを引く',22)}{e}")

    # 2) 辞書
    try:
        import lookup
        d = ctx.setdefault("辞書", lookup.Dict())
        r = d.look("動物")
        print(f"{ok if r else ng} 手元の辞書            {len(d.idx):,} 語")
    except Exception as e:
        print(f"{ng} {_w('手元の辞書',22)}{e}")

    # 3) 練習用フォルダ（本体ディスクに移したので、kernel に場所を聞く）
    sb = ctx["kernel"].SANDBOX
    n = sum(len(f) for _r, _d, f in os.walk(sb)) if os.path.isdir(sb) else 0
    print(f"{ok if n else ng} {_w('練習用フォルダ',22)}{n} 個のファイル")

    # 4) 本番で触るフォルダ
    try:
        from safety import Guard
        g = Guard()
        d = g.resolve("Desktop")
        print(f"{ok} {_w('本番の行き先',22)}{d}")
    except Exception as e:
        print(f"{ng} {_w('本番の行き先',22)}{e}")

    # 5) 外の先生（つながらなくても本体は動く）
    if not S.get("先生を使う", True):
        print(f"  － {_w('外の先生',22)}使わない設定です")
    else:
        try:
            from teachers import ask_panel
            rs = ask_panel("こんにちは", "ひとことで返して", S["先生"][:1])
            hit = next((r for r in rs if r.get("text") and not r.get("error")), None)
            if hit:
                print(f"{ok} {_w('外の先生',22)}{hit['teacher']}  {hit['ms']}ms")
            else:
                why = rs[0].get("error", "?") if rs else "返事なし"
                print(f"{ng} {_w('外の先生',22)}{str(why)[:60]}")
        except Exception as e:
            print(f"{ng} {_w('外の先生',22)}{str(e)[:60]}")

    # 6) 取り消せるか
    j = os.path.join(HERE, "journal.jsonl")
    if os.path.exists(j):
        recs = [json.loads(l) for l in open(j, encoding="utf-8") if l.strip()]
        live = [r for r in recs if r["items"] and not r.get("undone")]
        print(f"{ok} {_w('取り消せる操作',22)}{len(live)} 件")
    else:
        print(f"  － {_w('取り消せる操作',22)}まだ何もしていません")

    print("\n  ✗ が無ければ、そのまま使えます。")
