#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sensei.py -- 先生（モデル）と、じかに話す

  ふだんの kernel は「困ったときだけ」先生に相談する。
  ここはその逆で、**カーネルの仕組み（カード・部品・ノート）を一切通さず、
  先生とそのまま話す**ための口。先生そのものの力を見たいときに使う。

  決めごと:
    ・話の流れは ここだけで持つ。kernel の会話や記憶には混ぜない
      （混ぜると「カーネルが答えたのか、先生が答えたのか」が分からなくなる）
    ・先生の指定は 設定の「先生」を そのまま使う
    ・答えは 一切 手を入れずに返す。**良いも悪いも そのまま見せる**
    ・Python 標準ライブラリのみ

  ★ やりとりの並べかた
    毎回ちがう問いを **いちばん最後** に置く。
    llama.cpp のサーバは「前と同じ頭の部分」を覚えていて読み直さないので、
    これだけで手元の先生が 数倍速くなる（実測・2026-09-06）。
"""
import time

# 直近の何往復ぶんを 先生に渡すか。多いほど話は通じるが、そのぶん遅くなる
OUFUKU = 6

SYS = ("あなたは日本語で答える助手です。分からないことは分からないと言ってください。"
       "知らないことを もっともらしく作らないこと。")


def _tsunagu(rireki, toi):
    """やりとりを1本の文にする。**問いは必ず最後**（頭を変えないため）"""
    if not rireki:
        return toi
    p = ["これまでのやりとり:"]
    for r in rireki[-OUFUKU * 2:]:
        p.append("%s: %s" % ("あなた" if r["who"] == "user" else "先生", r["文"]))
    p.append("")
    p.append(toi)
    return "\n".join(p)


def kiku(toi, cfg, rireki=None, timeout=240, sensei=None, system=None):
    """先生ひとりに、じかに聞く。例外は投げない。

    戻り値: {"答え", "誰", "ミリ秒", "字/秒", "error"}
    """
    import teachers
    panel = [sensei] if sensei else [t for t in (cfg.get("先生") or []) if t]
    if not panel:
        return {"答え": "", "誰": None, "ミリ秒": 0, "字/秒": 0,
                "error": "先生が決まっていません（/model で決めてください）"}

    kudari = _tsunagu(rireki or [], toi)
    saigo = None
    for who in panel:                      # 前から順に試す
        r = teachers.ask_one(who, kudari, system=(system or SYS), timeout=timeout)
        saigo = r
        if not r.get("error") and (r.get("text") or "").strip():
            ms = max(r["ms"], 1)
            return {"答え": r["text"], "誰": r["teacher"], "ミリ秒": ms,
                    "字/秒": round(len(r["text"]) / (ms / 1000.0), 1),
                    "error": None}
    return {"答え": "", "誰": (saigo or {}).get("teacher"),
            "ミリ秒": (saigo or {}).get("ms", 0), "字/秒": 0,
            "error": (saigo or {}).get("error") or "答えが返りませんでした"}


def kuraberu(toi, tachi, timeout=240):
    """同じ問いを 何人かに同時に聞いて、並べて返す。

    **実力を見るには 比べるのが一番早い。**
    1人の答えだけ見ても、それが良いのか悪いのか分からない。
    """
    import teachers
    rs = teachers.ask_panel(toi, system=SYS, teachers=list(tachi),
                            timeout=timeout)
    # ask_panel は速く返った順。名前の順に並べ直して、毎回同じ見た目にする
    junban = {t: i for i, t in enumerate(tachi)}
    rs.sort(key=lambda r: junban.get(r["teacher"], 99))
    out = []
    for r in rs:
        ms = max(r.get("ms") or 1, 1)
        out.append({"誰": r["teacher"], "答え": r.get("text") or "",
                    "ミリ秒": ms,
                    "字/秒": round(len(r.get("text") or "") / (ms / 1000.0), 1),
                    "error": r.get("error")})
    return out


# ------------------------------------------------------------ 見せかた

def _oru(s, haba=76):
    """長い行を折る。端末でも画面でも読めるように"""
    out = []
    for gyou in (s or "").split("\n"):
        while len(gyou) > haba:
            out.append(gyou[:haba]); gyou = gyou[haba:]
        out.append(gyou)
    return "\n".join(out)


def miseru(r, kaigyou=True):
    """kiku の結果を、そのまま読める形にする"""
    if r.get("error"):
        return "  先生が答えませんでした: %s" % r["error"]
    atama = "  ── %s ／ %.1f 秒 ／ %d 字（%s 字/秒）" % (
        r["誰"], r["ミリ秒"] / 1000.0, len(r["答え"]), r["字/秒"])
    return (atama + "\n" if kaigyou else "") + _oru(r["答え"])


def youi(tachi, iu=None):
    """手元のモデルを頼むなら、それが載っているか先に確かめる。

    ★ ここを見ていないと「local:main に聞きました」と書きながら
      **実際には 80B に聞いた答え**を出す。
      16GB なので手元のモデルは同時に1つしか載らず、入れ替えは
      server.py が持っている。画面から使っているときだけ server が
      居るので、居るときだけ頼む（端末から使うときは そのまま通す）。

    戻り値: 実際に聞ける先生のいちらん（用意できなかった手元は外す）
    """
    import sys as _s
    sv = _s.modules.get("server")
    hoshii = [t for t in tachi if str(t).startswith("local:")]
    if not (sv and hoshii and hasattr(sv, "moderu_youi")):
        return list(tachi)
    ok, shirase = sv.moderu_youi(hoshii[0])
    if not ok:
        if iu:
            iu("  手元のモデルが用意できません: %s" % shirase)
        return [t for t in tachi if not str(t).startswith("local:")]
    if shirase and iu:
        iu("  " + shirase)
    return list(tachi)


def chokusetsu(text, ctx):
    """「先生と直接」のときの入口。画面版(server.py)と端末版(main.py)の両方から呼ぶ。

    やりとりは ctx["先生の話"] にだけ積む。kernel の会話・記憶には混ぜない。
    """
    rireki = ctx.setdefault("先生の話", [])
    tachi = youi(ctx["設定"].get("先生") or [], print)
    if not tachi:
        print("  聞ける先生が居ません。"); return None
    r = kiku(text, ctx["設定"], rireki, sensei=tachi[0])
    if not r.get("error"):
        rireki.append({"who": "user", "文": text})
        rireki.append({"who": "bot", "文": r["答え"]})
        del rireki[:-40]
    print(miseru(r))
    return r


# ---------------------------------------------------------------- 調べてから答える

SHIRABE_SYS = (
    "あなたは、渡された資料だけを根拠に答える係です。"
    "資料に書いていないことは、絶対に書かないこと。"
    "資料から読み取れないときは「資料には書かれていません」とだけ答えること。"
    "推測で補わないこと。知っているつもりのことを書かないこと。")


def shirabete(toi, cfg, timeout=240, iu=None):
    """**思い出させず、調べさせる。**

    ★ なぜ要るか（2026-09-06 の実測）
      「日本の都道府県で名前に『山』が入るもの」を、手元の 30B も 80B も外した。
      作り話（「山県」「山田県」）まで出た。原因は量子化でも枝刈りでもなく、
      **Qwen が日本語の事実知識に弱い**こと（NIILC で Qwen2.5-7B は 84位/120。
      日本語特化の 7〜13B が 72B の Qwen を上回る）。
      日本語に強いモデルは どれも密で、この機械では 3〜6 t/s まで落ちる。
      **賢さと速さは、いま手に入るモデルでは両立しない。**

      だが この種の問いは 思い出す問題ではなく **調べる問題** だった。
      カーネルには既に wiki.py がある。**モデルに覚えさせるのをやめる**のが、
      いちばん確実で いちばん速い。嘘は「知らないことを書く」ときにしか出ない。

    手順:
      ① 何を調べるかだけ、先生に一言で決めてもらう（短いので速い）
      ② Wikipedia から本文を取る
      ③ **その本文だけを根拠に**答えさせる。無ければ「書かれていません」

    戻り値: {"答え","出典","誰","ミリ秒","error"}
    """
    import time as _t
    t0 = _t.monotonic()
    try:
        import wiki
    except Exception as e:
        return {"答え": "", "出典": None, "誰": None, "ミリ秒": 0,
                "error": "調べる道具が読めません: %s" % e}

    # ① 調べる言葉を決める
    r1 = kiku("次の質問に答えるために Wikipedia で開くべき記事の名前を、"
              "1つだけ、記事名だけを、余計な字を付けずに書いてください。\n\n"
              "質問: " + toi, cfg, timeout=min(timeout, 120),
              system="記事名だけを1つ書く係です。説明を書かないこと。")
    if r1.get("error"):
        return {"答え": "", "出典": None, "誰": r1.get("誰"),
                "ミリ秒": int((_t.monotonic() - t0) * 1000),
                "error": "調べる言葉を決められませんでした: %s" % r1["error"]}
    go = (r1["答え"] or "").strip().splitlines()[0]
    go = go.strip("「」『』\"' 　。、:：").strip()[:40]
    if iu:
        iu("  調べる言葉: %s" % go)

    # ② 本文を取る。
    #   ★ **先生が決めた言葉だけに頼らないこと。**
    #     「山」の県を聞いたとき、先生は調べる言葉に「山県」（自分の作り話）を
    #     選び、その 153字 のスタブ記事を読んで「書かれていません」と答えた。
    #     嘘は止まったが 正解には届かない。知識が壊れているモデルに
    #     「何を調べるか」を任せきると、壊れたところへ調べに行く。
    #   → 質問文そのものでも探し、**短いスタブは捨て、上位を何本かまとめて**渡す。
    #   ★ **まず 質問文の中の語を そのまま記事名として引く。**
    #     先生が作る検索語は当てにならない。実測（2026-09-06）:
    #       「山梨県の県庁所在地は？」→ 先生の語「山梨県本庁所在地」→ 裁判所の記事
    #       「レーウェンフックは何を発明した？」→「レーウェンフックの発明」→ 微生物学
    #     どちらも **「山梨県」「レーウェンフック」を一度も試していない**。
    #     漢字・カタカナのかたまりは たいてい そのまま記事名になる。長い順に試す。
    import re as _re
    katamari = _re.findall(r"[一-龥ヶ々]{2,}|[ァ-ヴー]{3,}|[A-Za-z][A-Za-z0-9\-]{2,}", toi)
    katamari = sorted(set(katamari), key=len, reverse=True)[:5]
    tori = list(katamari)
    try:
        tori += [x["題"] for x in (wiki.search(go, n=3) or [])]
        tori += [x["題"] for x in (wiki.search(toi[:80], n=4) or [])]
    except Exception as e:
        return {"答え": "", "出典": None, "誰": r1.get("誰"),
                "ミリ秒": int((_t.monotonic() - t0) * 1000),
                "error": "調べに行けませんでした（ネット）: %s" % e}
    kouho, mita = [], set()
    for t in list(tori) + [go]:
        if t and t not in mita:
            mita.add(t); kouho.append(t)

    #   資料は多いほど良い、ではない。3本 3,600字 を渡したとき 読むだけで
    #   90〜100秒かかった（本家の読解は 28 t/s しか出ない）。**当たった1本**が要る。
    atsume, deta, ryou = [], [], 0
    for t in kouho:
        if len(atsume) >= 2 or ryou >= 4000:
            break
        try:
            a = wiki.article(t, chars=4000)
        except Exception:
            a = None
        # スタブ（数行だけの記事）は根拠にならない。捨てる
        if a and len((a.get("本文") or "")) >= 400:
            atsume.append(a); deta.append(a["題"]); ryou += len(a["本文"])
    if not atsume:
        return {"答え": "", "出典": None, "誰": r1.get("誰"),
                "ミリ秒": int((_t.monotonic() - t0) * 1000),
                "error": "使える記事が見つかりませんでした（探した語: %s）" % go}
    honbun = {"題": " / ".join(deta),
              "本文": "\n\n".join("■ %s\n%s" % (a["題"], a["本文"]) for a in atsume)}
    if iu:
        iu("  資料: %s（合計%d字）" % (honbun["題"], len(honbun["本文"])))

    # ③ 資料だけを根拠に答えさせる
    r2 = kiku("【資料】\n" + honbun["本文"] + "\n\n"
              "上の資料だけを根拠に、次の質問に答えてください。\n"
              "資料に無いことは書かないこと。\n\n質問: " + toi,
              cfg, timeout=timeout, system=SHIRABE_SYS)
    ms = int((_t.monotonic() - t0) * 1000)
    if r2.get("error"):
        return {"答え": "", "出典": honbun["題"], "誰": r2.get("誰"),
                "ミリ秒": ms, "error": r2["error"]}
    return {"答え": r2["答え"], "出典": honbun["題"], "誰": r2["誰"],
            "ミリ秒": ms, "error": None}
