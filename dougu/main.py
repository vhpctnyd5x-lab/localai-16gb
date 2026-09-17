#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py -- ひとつの入口

  入力を受け取り、命令なら実行し、雑談なら返事をする。
  「/」で始まる行は、道具への指示（設定・点検・取り消し）として扱う。

  使い方:
    python3 main.py                 対話する
    python3 main.py --real          本物のフォルダを対象にする（関所つき）
    python3 main.py "命令や雑談"      1回だけ
    python3 main.py --undo          直前の変更を取り消す

  会話の中では /help ですべてのコマンドが見られる。
"""
import sys, os, time, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import re
import kernel
import chat
import settings as S

# 「AしてBして」を分ける切れ目。はっきりした接続だけを使う。
# 「して、」だけで切ると「整理して、ありがとう」まで切れてしまう
_STEP = re.compile(r"(?:、|，|。|\s)*(?:そのあと|その後|それから|次に|つぎに|"
                   r"そして|あと|さらに)(?:、|，|\s)*|(?:してから|したあと|した後)")


def split_steps(text):
    """多段の命令を、順番の並びに分ける。分けられなければ1つのまま返す"""
    parts = [p.strip("　 、,。") for p in _STEP.split(text)]
    parts = [p for p in parts if len(p) >= 4]
    if len(parts) < 2:
        return [text]
    # それぞれが命令らしい（場所かパスが分かる）ときだけ、分けた形を採る
    ok = sum(1 for p in parts
             if {"場所", "パス"} & set(kernel.draw_cards(p)))
    return parts if ok >= 2 else [text]


# 「元に戻して」は雑談ではなく、取り消しの指示として受け取る。
# これが無いと「戻せます」と言うだけで戻せなかった
_UNDO = re.compile(r"(元に戻|もとに戻|取り消|取消|やっぱ(り)?(やめ|なし)|"
                   r"戻して|アンドゥ|undo)")

# 外付けSSD(exFAT)はSQLiteのロックに対応していないため、記憶だけ本体ディスクに置く
DATA = os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                    "kernel-ai")
os.makedirs(DATA, exist_ok=True)
MEMDB = os.path.join(DATA, "memory.db")


def _dict(ctx):
    if "辞書" not in ctx:
        import lookup
        ctx["辞書"] = lookup.Dict()
    return ctx["辞書"]


def _grow_around(words, ctx):
    """調べた語のまわりを、そのついでに覚える。

    ここが「使いながら強くなる」の中身。
    自信のあるものだけが残るので、たいてい0〜2枚しか増えない
    """
    try:
        import grow
        kernel.load_learned(); kernel.load_grown()
        got = grow.from_words(words, _dict(ctx).look, kernel.SEED)
    except Exception:
        return
    for w, slot, val, why in got:
        print(f"  ★ ついでに覚えました： 「{w}」→【{val}】（{slot}）"
              f"  説明に「{why}」とあったので")


def _say(ctx, who, text):
    """会話の流れに1件足す。

    ここに足しておかないと「何を動かしたの？」「もっと簡単に言って」
    のような、直前を指す言い方に答えられない。
    以前は辞書の答えも命令の結果も流れに入れていなかったので、
    毎回まっさらな状態から返事を作っていた。
    """
    h = ctx["会話"]
    h.append({"role": who, "text": text})
    n = ctx["設定"]["会話の長さ"] * 2
    if len(h) > n:
        del h[:len(h) - n]


def _dougu(text, ctx):
    """道具に振り分ける（数え上げ・Web・ターミナル・表/文章）。扱ったら True。
    ★ kernel の命令（カード）より **先** に見ること。通し試験（2026-09-12）で
      「ターミナルで … 一覧して」「….csv の合計を出して」が古い命令の仕組みに横取りされ、道具に届かなかった（3/5）。
      道具は合図の言葉（ターミナル・URL・何通り・csv…）が **明示されたとき** だけ入るので、ふつうの命令は今まで通り kernel に行く。"""
    cfg = ctx["設定"]
    mem = ctx["記憶"]
    iu = lambda m: print(m) if cfg.get("考える様子") else None
    try:
        import kazoeru, web, tanmatsu, shigoto, sousa
        if kazoeru.aizu(text):
            na, toku = "数え上げ", kazoeru.toku
        elif web.aizu(text):
            na, toku = "Web", web.kotaeru
        elif tanmatsu.aizu_tsuyoi(text) or (tanmatsu.aizu(text) and not chat.mono_no_hanashi(text)):
            na, toku = "ターミナル", tanmatsu.kotaeru
        elif sousa.aizu(text):
            na, toku = "操作", sousa.suru        # 画面を見て押す・打つ（毎手、承認を挟む）
        elif shigoto.aizu(text):
            na, toku = "仕事", shigoto.suru
        else:
            return False
    except Exception as e:
        print(f"  （道具の合図でつまずいた: {type(e).__name__}: {e}。ふつうに答えます）")
        return False
    if cfg["覚える"]: mem.add("user", text)
    _say(ctx, "user", text)
    try:
        r = toku(text, iu=iu)
        if na == "数え上げ":
            ans = f"答え：{r['答え']}（{r['確かめ']}）" if r["答え"] is not None else \
                  f"数えきれませんでした（{r['確かめ']}）。問題文をもう少しはっきり書いてもらえますか。"
        elif na == "仕事":
            if r["できた"]:
                ans = r["報告"] or "できました。"
                if r["成果物"]:
                    ans += "\n  できたもの:\n" + "\n".join("    " + p_ for p_ in r["成果物"])
                    # 小さな成果物（合計の数など）は開かなくても分かるように中身も見せる
                    naka = shigoto._naka(r["成果物"]).strip()
                    if 0 < len(naka) <= 300:
                        ans += "\n  中身: " + naka.replace("\n", " ⏎ ")
            else:
                ans = "できませんでした。" + (("理由: " + r["エラー"].splitlines()[-1][:120]) if r.get("エラー") else "")
        elif na == "操作":
            ans = r["報告"] + ("\n  手順:\n" + "\n".join("    %d. %s" % (i + 1, t) for i, t in enumerate(r["手"])) if r.get("手") else "")
        else:
            ans = r["答え"] or ("できませんでした: %s" % (r.get("error") or "")).strip()
    except Exception as e:
        ans = f"{na}の道具でつまずきました: {type(e).__name__}: {e}"
    print(f"\n  {ans}")
    _say(ctx, "assistant", ans)
    if cfg["覚える"]: mem.add("assistant", ans)
    return True


def _machine_ask(kiken_do: str, cfg: dict):
    """machine の用件を実行する前の「聞き方」を1つに決める（shounin に一本化）。

    ★ 2026-09-13 に見つけた穴（記録で実測）
      画面（カーネル.app）から「計算機を開いて」と頼むと、ここが machine の
      「アプリをひらく」に当たる。既定の `確認: False` で素通りし、
      **承認の札を1枚も出さずに** アプリが開いていた。
      そのうえ machine は _dougu() より前にあるので、
      札を出す側（sousa の操作の輪）にも回っていなかった。

    直し方: 聞くかどうかは ここで決め、聞き方は shounin に任せる。
      ・画面から使っているとき（shounin.TOIKAKE がある）は、外に出る操作も必ず札を出す。
        画面には「[y/N]」を打つ場所が無いので、input() は そもそも届かなかった。
      ・端末では これまで通り。`確認: False` なら「外」は聞かずに動く（後退させない）。
      ・「跡」（戻せない）は、どちらでも必ず聞く。
    """
    import shounin
    def _ask(n):
        if kiken_do != "跡" and shounin.TOIKAKE is None and not cfg.get("確認", True):
            return True
        shirushi = "【戻せません】" if kiken_do == "跡" else ""
        return shounin.kiku(f"{shirushi}{n} をします")
    return _ask


def route(text, ctx):
    """振り分け： 語義の質問か、命令か、雑談か"""
    cfg = ctx["設定"]
    mem = ctx["記憶"]
    t0 = time.time()

    # 「先生と直接」のときは、ここで終わり。
    # カーネルの仕組み（分ける・カード・部品・ノート）を一切通さない。
    # 命令の分割より **前** に置くこと。質問を勝手に切ってはいけない。
    if cfg.get("先生と直接"):
        import sensei
        sensei.chokusetsu(text, ctx)
        return

    steps = split_steps(text)
    if len(steps) > 1:
        print(f"\n  ■ {len(steps)} つの命令に分けました")
        for i, one in enumerate(steps, 1):
            print(f"     {i}. {one}")
        for i, one in enumerate(steps, 1):
            print(f"\n  ── {i} つめ ──")
            route(one, ctx)
        return

    # ファイル以外のパソコン操作（時刻・電池・音量・アプリ…）は、
    # 探索にかけず、用件の表から直接ひく
    try:
        import machine
        hit = machine.match(text)
    except Exception:
        hit = None

    # ── 横取りの歯止め ──────────────────────────────────────
    #
    # §7-① と同じ形の事故が、ここにも残っていた。
    # あちらは make_page が「デスクトップの一覧をHTMLで」を横取りしていて、
    # `_honmono()`（場所・パス・行き先 が引けたら実物の話）で直した。
    # machine には、その歯止めが無かった。実測した誤動作:
    #
    #   「デスクトップのメモを開いて」→ メモ.app が起動していた
    #     （ユーザーが開きたいのは Desktop の メモ.txt）
    #   「デスクトップの画像をネットで調べて」→ ネットの接続状況を答えていた
    #
    # 場所やパスが引けているなら、それは手元の実物の話。
    # ファイルを扱う kernel に回す。
    # ただし、場所を受け取ることに意味がある部品は、そのまま通す。
    _BASHO_OK = {"フォルダをひらく", "最近のダウンロード", "ゴミ箱", "空き容量", "こよみ"}
    try:
        import kikai as _kikai
        _BASHO_OK |= set(_kikai.OPS)      # 2026-09-17: 暦・計算・予定などは「2026」がフォルダ名でも ファイルの話ではない
    except Exception:
        pass
    if hit and hit[0] not in _BASHO_OK:
        try:
            import kernel as _k
            _d = _k.draw_cards(text)
            if _d.get("場所") or _d.get("パス"):
                print(f"  （「{hit[0]}」とも読めましたが、"
                      f"手元のファイルの話のようなので、そちらで見ます）")
                hit = None
        except Exception:
            pass

    if hit:
        name, mslots = hit
        _fn, risky = machine.OPS[name]
        _k = machine.kiken(name)
        import shounin as _shounin
        _ask = _machine_ask(_k, cfg)
        _shounin.hajimeru()        # 「全部」の効きめは この1件の間だけ
        try:
            ans = machine.run(name, mslots,
                              confirm=_ask if _k != "読" else None)
        except Exception as e:
            ans = f"できませんでした： {e}"
        finally:
            _shounin.owaru()
        # 中身の1行目が用件名そのものだと、見出しと二重になる
        #   【空き容量】
        #   空き容量          ← これ
        body = str(ans)
        if body.split("\n", 1)[0].strip() == name:
            body = body.split("\n", 1)[1] if "\n" in body else ""
        print(f"\n  【{name}】")
        print("  " + body.replace("\n", "\n  "))
        _say(ctx, "user", text)
        _say(ctx, "assistant", f"{name}: {ans}")
        if cfg["覚える"]: mem.add("assistant", f"{name}: {ans}")
        return

    # ────────────────────────────────────────────────────────
    # 「◯◯を作って」で、ページとして作るのが自然なもの。
    #
    # 前は「ゲームを作ることはできません」と断っていた。
    # HTML を書き出す部品は持っていたのに、中身を考える係がいなかった。
    #   中身を書く … 先生（文章を作るのは向こうが得意）
    #   確かめる   … カーネル（形・危なさ・大きさを自分で見る）
    #   書き出す   … カーネル（どこに置くか、上書きしないかを自分で決める）
    # ────────────────────────────────────────────────────────
    try:
        import make_page
        pagey = make_page.wants_page(text)
    except Exception:
        pagey = False
    if pagey:
        if not cfg.get("先生を使う", True):
            print("\n  中身を書いてもらう先生が切られています（/set 先生を使う true）")
            return "中身を書く先生がいません"
        print(f"\n  ■ ページとして作ります： 「{text}」")
        print("     まず自分の部品で組めるか試し、無理なら先生に頼みます")
        try:
            r = make_page.make(text, teachers=cfg.get("先生"))
        except Exception as e:
            print(f"  できませんでした： {e}")
            _say(ctx, "user", text)
            return f"作れませんでした: {e}"
        body = (f"{os.path.basename(r['パス'])} を作りました\n"
                f"  置き場所: {r['パス']}\n"
                f"  作った人: {r['誰']} ／ {r['バイト']:,} バイト "
                f"／ {r['ミリ秒']:,} ミリ秒")
        if r.get("手順"):
            body += ("\n  組み立て: " + " → ".join(r["手順"])
                     + f"\n  （{r.get('選び方','')}部品を選びました）")
        body += "\n  そのままブラウザで開けます"
        print("\n  " + body.replace("\n", "\n  "))
        _say(ctx, "user", text)
        _say(ctx, "assistant", body)
        if cfg["覚える"]: mem.add("assistant", body)
        return body

    if _UNDO.search(text) and len(text) <= 30:
        S.run("/undo", ctx)
        _say(ctx, "user", text)
        _say(ctx, "assistant", "直前の操作を取り消した")
        return

    # まず辞書を引いてみる。当たれば先生を呼ばずに済む
    r = None
    if cfg["辞書"]:
        try:
            import lookup
            r = lookup.answer(text, _dict(ctx))
        except Exception:
            r = None
    if r:
        if cfg["覚える"]: mem.add("user", text)
        body = f"【{r['語']}】\n{r['答え']}"
        if r["関連"]:
            body += f"\n  → 関連: {' / '.join(r['関連'])}"
        print("\n  " + body.replace("\n", "\n  "))
        print(f"  （手元の辞書から {(time.time()-t0)*1000:.1f} ミリ秒。"
              f"先生は呼んでいません）")
        if cfg.get("育てる", True) and r.get("関連"):
            _grow_around(r["関連"], ctx)
        _say(ctx, "user", text)
        _say(ctx, "assistant", body)
        if cfg["覚える"]: mem.add("assistant", f"{r['語']}: {r['答え'][:200]}")
        return

    # ★ 道具（数え上げ・Web・ターミナル・表/文章）は、命令の仕組みより先に見る
    if _dougu(text, ctx):
        return

    slots = kernel.draw_cards(text, verbose=False)
    kind = chat.classify(text, slots)

    if kind == "あいまい" and not chat.mono_no_hanashi(text):
        kind = "雑談"          # ものの話でも頼みごとでもない → 先生に聞くまでもなく雑談
    if kind == "あいまい":
        # ここだけ先生に聞く（軽い判定で決まらなかった時のみ）
        try:
            kind = chat.ask_teacher_classify(text) or "雑談" \
                if cfg["先生を使う"] else "雑談"
        except Exception:
            kind = "雑談"

    if kind in ("命令", "問い合わせ"):
        if cfg["覚える"]: mem.add("user", text)
        _say(ctx, "user", text)
        if kind == "問い合わせ":
            print("  （聞かれているだけなので、読むだけにします）")
        done = "（命令を実行）"
        try:
            done = kernel.handle(text, readonly=(kind == "問い合わせ"),
                                 quiet=not cfg["考える様子"]) or done
        except PermissionError as e:
            done = f"実行しませんでした： {e}"
            print(f"\n  {done}")
        except Exception as e:
            done = f"うまくいきませんでした： {e}"
            print(f"\n  {done}")
        _say(ctx, "assistant", done)
        if cfg["覚える"]: mem.add("assistant", done)
        return

    # 雑談
    if cfg["覚える"]: mem.add("user", text)
    _say(ctx, "user", text)
    if not cfg["先生を使う"]:
        print("\n  今は外の先生を使わない設定なので、雑談には答えられません。"
              "（/set 先生を使う true で戻せます）")
        return
    rep = chat.reply(text, list(ctx["会話"]), mem)
    if rep.get("error"):
        print(f"  返事を作れませんでした： {rep['error']}")
        return
    # ★ 2026-09-17: 頭脳が「道具: 言い方」と答えたら、その言い方を 決まった道（machine）に通す。承認の札も同じ
    if rep.get("道具"):
        name, mslots = rep["道具"]
        if name:
            print(f"\n  （頭脳が道具を選びました: {name}）")
            _k = machine.kiken(name)
            import shounin as _shounin
            _shounin.hajimeru()
            try:
                ans = machine.run(name, mslots, confirm=_machine_ask(_k, cfg) if _k != "読" else None)
            except Exception as e:
                ans = f"できませんでした： {e}"
            finally:
                _shounin.owaru()
            body = str(ans)
            print(f"\n  【{name}】")
            print("  " + body.replace("\n", "\n  "))
            _say(ctx, "assistant", f"{name}: {ans}")
            if cfg["覚える"]: mem.add("assistant", f"{name}: {ans}")
            return
        print(f"\n  （頭脳は道具を使おうとしましたが、言い方が読めませんでした: {mslots}）")
        rep["text"] = re.sub(r"^\s*道具\s*[:：].*$", "", rep["text"], flags=re.M).strip() or "すみません、その頼みは道具では受けられませんでした。"
    print(f"\n  {rep['text']}")
    if cfg["詳しく"]:
        print(f"  （{rep['teacher']} / {rep['ms']}ms / "
              f"振り分け {(time.time()-t0)*1000:.0f}ms）")
    _say(ctx, "assistant", rep["text"])
    if cfg["覚える"]: mem.add("assistant", rep["text"])


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("text", nargs="*")
    ap.add_argument("--real", action="store_true", help="本物のフォルダを対象にする")
    ap.add_argument("--undo", action="store_true", help="直前の変更を取り消す")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()

    # 危険度を書き忘れた部品がないか、動き出す前に見回る。
    # 書き忘れると「跡」扱いになって確認が要るので 止まりはしないが、
    # 黙って重い扱いにするより、はっきり言ったほうがよい
    try:
        import machine as _m
        _wasure = _m.kaki_wasure()
        if _wasure:
            print("※ 危険度を書いていない道具があります（安全側の『跡』で扱います）:")
            print("   " + "、".join(_wasure))
    except Exception:
        pass

    cfg = S.load()
    if a.verbose:
        cfg["詳しく"] = True
    if a.real:
        cfg["モード"] = "本番"

    ctx = {"設定": cfg, "記憶": None, "会話": [], "kernel": kernel}

    if a.help:
        S.run("/help", ctx); return
    if a.undo:
        S.run("/undo", ctx); return

    S._apply(cfg, ctx)
    if cfg["モード"] == "本番":
        print("■ 本物のフォルダを触ります。"
              "ものを動かす手順は、必ず下見してから実行します（関所つき）")
    else:
        print("■ 練習モード（試験用）。sandbox の中だけで動きます")

    ctx["記憶"] = chat.Memory(MEMDB)

    if a.text:
        t = " ".join(a.text)
        if S.is_command(t):
            S.run(t, ctx)
        else:
            route(t, ctx)
        return

    print("  /help でコマンド一覧 ・ /settings で設定 ・ /quit でおわり\n")
    while True:
        try:
            t = input("あなた> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not t:
            continue
        # 昔からの :quit / :mem も残しておく
        if t in (":quit", ":q"):  break
        if t == ":mem":           t = "/memory"
        if S.is_command(t):
            if S.run(t, ctx) == "quit":
                break
            continue
        try:
            route(t, ctx)
        except Exception as e:
            print(f"\n  こまりました： {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
