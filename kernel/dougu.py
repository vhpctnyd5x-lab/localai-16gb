#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dougu.py -- 先生に **道具を選ばせて**、結果を見せて、また選ばせる（道具の輪）

  ────────────────────────────────────────────────
  なぜ作ったか
  ────────────────────────────────────────────────
  カーネルは道具を すでに ひととおり持っている（machine / coderun / wiki / kernel）。
  足りないのは **道具を選ぶ輪** だった。
      いま  : あなた → カーネルの記号的な探索 → 部品を並べる → 実行
      ここ  : あなた → 先生が道具を選ぶ → 実行 → 結果を見せる → また選ぶ → 答え
  「Claude Code のようにパソコンを触らせたい」への答えがこれ。

  ────────────────────────────────────────────────
  安全（ここが本体。道具より先に決めること）
  ────────────────────────────────────────────────
  v1 に入れるのは **跡が残らないもの だけ**。
    ・読むだけの道具（時刻・電池・空き容量・フォルダの中身・辞書・Wikipedia）
    ・コードは coderun の **使い捨ての部屋**の中だけ（外に出られない）
  入れないもの:
    ・ファイルを作る/動かす/消す   … kernel 側の 仮想→関所→記録→取り消し を通すべき
    ・アプリ操作・打ち込む・押す    … machine.py の危険度でいう「跡」
  **先生が選べる道具に「跡」を1つも置かない**のが、この輪の安全の全部。
  先生が間違えても、壊れるものが無い。

  ★ 頼み文の並び順
    毎回同じもの（道具のいちらん・書き方・例）を **先** に、
    毎回ちがうもの（これまでの経過・質問）を **最後** に置く。
    llama.cpp は前と同じ頭を読み直さないので、これだけで数倍速くなる
    （2026-09-06 実測: 同じ長さの頼み文で 75.6秒 → 3.3秒）。

  Python 標準ライブラリのみ。
"""
import json
import os
import time

MAX_WA = 6          # 何回まで道具を使ってよいか
MAX_BYOU = 240      # 全体の持ち時間


# ---------------------------------------------------------------- 道具

def _shiraberu(a):
    """Wikipedia を引く"""
    import wiki
    w = (a.get("語") or a.get("word") or "").strip()
    if not w:
        return "語が空です"
    r = wiki.ask(w, chars=1200)
    if isinstance(r, dict):
        return "【%s】\n%s" % (r.get("題", w), r.get("本文") or r.get("説明") or "")
    return str(r or "見つかりませんでした")


def _kotoba(a):
    """手元の辞書（外に出ない）"""
    w = (a.get("語") or "").strip()
    if not w:
        return "語が空です"
    try:
        import jisho
        return str(jisho.hiku(w))
    except Exception:
        import wiki
        return _shiraberu({"語": w})


def _folder(a):
    """フォルダの中身を見る（読むだけ。触らない）"""
    import kernel as _k
    basho = (a.get("場所") or "Desktop").strip()
    try:
        d = _k.place_dir(basho)
    except Exception as e:
        return "その場所は見られません: %s" % e
    if not os.path.isdir(d):
        return "%s がありません" % d
    na = sorted(os.listdir(d))
    na = [x for x in na if not x.startswith(".")]
    atama = na[:60]
    s = "%s に %d 個\n" % (basho, len(na)) + "\n".join("  " + x for x in atama)
    if len(na) > len(atama):
        s += "\n  …ほか %d 個" % (len(na) - len(atama))
    return s


def _pc(a):
    """パソコンの様子（読むだけ）"""
    import machine as _m
    nani = (a.get("何") or a.get("項目") or a.get("what") or "").strip()
    hyou = {"いま何時": _m.m_time, "時刻": _m.m_time, "時間": _m.m_time,
            "時": _m.m_time, "現在時刻": _m.m_time, "日付": _m.m_time,
            "電池": _m.m_battery, "バッテリー": _m.m_battery,
            "空き容量": _m.m_disk, "ディスク": _m.m_disk, "容量": _m.m_disk,
            "メモリ": _m.m_memory_use, "音量": _m.m_volume,
            "ネット": _m.m_wifi, "WiFi": _m.m_wifi, "wifi": _m.m_wifi,
            "開いているアプリ": _m.m_apps, "アプリ": _m.m_apps}
    f = hyou.get(nani)
    if not f:
        # ★ ここで「案内」だけ返すと、**先生はそれを答えだと思って作り話をする。**
        #   実際に起きた（2026-09-06）: {"何":"時"} が表に無く案内を返したら、
        #   先生は「10:30」と答えた。本当は 18:53 だった。
        #   道具が答えなかったことは、**答えなかったと はっきり言う。**
        return ("【この道具は答えていません】「%s」は見られません。"
                "見られるのは: %s ／ この結果から答えを作らないこと。"
                % (nani, " / ".join(sorted(set(hyou)))))
    try:
        return str(f({}))
    except Exception as e:
        return "見られませんでした: %s" % e


def _code(a):
    """使い捨ての部屋で Python を走らせる。部屋の外には出られない"""
    import coderun
    src = a.get("コード") or a.get("code") or ""
    if not src.strip():
        return "コードが空です"
    r = coderun.run(src, lang="python", timeout=15)
    out = (r.get("出力") or "").strip()
    err = (r.get("エラー") or "").strip()
    s = out if out else "（何も出力されませんでした）"
    if err:
        s += "\n── エラー ──\n" + err[:600]
    return s[:2000]


DOUGU = {
    "しらべる":       (_shiraberu, '{"語":"富士山"}', "Wikipedia を引く（外に出る）"),
    "ことばの意味":   (_kotoba,    '{"語":"都道府県"}', "辞書を引く"),
    "フォルダを見る": (_folder,    '{"場所":"Desktop"}',
                      "中身を並べる。見るだけで触らない（Desktop/Downloads/Documents）"),
    "パソコンの様子": (_pc,        '{"何":"空き容量"}',
                      "いま何時／電池／空き容量／メモリ／音量／ネット／開いているアプリ"),
    "けいさん":       (_code,      '{"コード":"print(sum(range(1,11)))"}',
                      "Python を使い捨ての部屋で走らせて出力を見る。計算や文字数えに使う"),
}


# ---------------------------------------------------------------- 頼み文

def _atama():
    """毎回おなじ部分。**必ず先頭に置く**（読み直させないため）"""
    p = ["あなたはパソコンの助手です。道具を使って質問に答えます。",
         "", "【使える道具】"]
    for n, (_f, rei, setsu) in DOUGU.items():
        p.append('  %s … %s' % (n, setsu))
        p.append('      例: {"道具":"%s","引数":%s}' % (n, rei))
    p += ["",
          "【答えかた】JSON をひとつだけ書く。説明もコードフェンスも書かない。",
          '  道具を使うとき : {"道具":"…","引数":{…}}',
          '  答えが出たとき : {"答え":"…"}',
          "",
          "【守ること】",
          "  ・分かっているつもりで答えない。**確かめてから答える**",
          "  ・道具の結果に無いことは書かない。無ければ「分かりません」と答える",
          "  ・道具が【この道具は答えていません】と言ったら、**それは答えではない**。",
          "    別の引数で言い直すか、分かりませんと答えること。数字を作らないこと。",
          "  ・同じ道具を同じ引数で二度使わない",
          "  ・答えが出たら すぐ {\"答え\":…} を返す",
          ""]
    return "\n".join(p)


def _shippo(toi, keika):
    """毎回ちがう部分。**必ず最後に置く**"""
    p = []
    if keika:
        p.append("【これまで】")
        for i, (d, hiki, res) in enumerate(keika, 1):
            p.append("  %d. %s %s" % (i, d, json.dumps(hiki, ensure_ascii=False)))
            p.append("     → " + (res or "")[:700].replace("\n", "\n       "))
        p.append("")
    p.append("【質問】" + toi)
    return "\n".join(p)


# ---------------------------------------------------------------- 輪

def mawasu(toi, cfg, iu=None, max_wa=MAX_WA, timeout=90):
    """道具の輪を回す。戻り値: {"答え","経過","回数","ミリ秒","error"}"""
    import sensei
    import teachers
    t0 = time.monotonic()
    keika = []
    # ★ 同じ道具を同じ引数で繰り返す癖がある。**言葉で禁じても守らない。**
    #   実測（2026-09-06）: 「デスクトップに何がありますか」で
    #   「フォルダを見る{場所:Desktop}」を **6回** 繰り返した（35秒）。
    #   頼み文に「二度使わない」と書いてあっても、である。
    #   → 仕組みで止める。同じ手は二度走らせず、走らせたことにもしない。
    tsukatta = set()
    kurikaeshi = 0
    for wa in range(1, max_wa + 1):
        if time.monotonic() - t0 > MAX_BYOU:
            return {"答え": "", "経過": keika, "回数": wa - 1,
                    "ミリ秒": int((time.monotonic() - t0) * 1000),
                    "error": "時間切れ"}
        r = sensei.kiku(_atama() + _shippo(toi, keika), cfg, timeout=timeout,
                        system="JSON をひとつだけ返す係です。説明を書かないこと。")
        if r.get("error"):
            return {"答え": "", "経過": keika, "回数": wa - 1,
                    "ミリ秒": int((time.monotonic() - t0) * 1000),
                    "error": r["error"]}
        j = teachers.extract_json(r["答え"])
        if not isinstance(j, dict):
            j = {"答え": r["答え"]}          # JSON にできないなら、そのまま答えとみなす
        if "答え" in j and not j.get("道具"):
            return {"答え": str(j["答え"]), "経過": keika, "回数": wa - 1,
                    "ミリ秒": int((time.monotonic() - t0) * 1000), "error": None}
        na = str(j.get("道具") or "").strip()
        hiki = j.get("引数") if isinstance(j.get("引数"), dict) else {}
        if na not in DOUGU:
            keika.append((na or "（道具名なし）", hiki,
                          "そんな道具はありません。使えるのは: "
                          + " / ".join(DOUGU)))
            continue
        kagi = na + "|" + json.dumps(hiki, ensure_ascii=False, sort_keys=True)
        if kagi in tsukatta:
            kurikaeshi += 1
            if iu:
                iu("  %d回目: %s（同じ手なので走らせません）" % (wa, na))
            if kurikaeshi >= 2:
                break                 # 二度言っても直らない。打ち切って答えさせる
            keika.append((na, hiki,
                          "※ その手は もう使いました。結果は上に出ています。"
                          "答えが出ているなら {\"答え\":…} を返してください。"
                          "足りないなら **別の道具か 別の引数** を使ってください。"))
            continue
        tsukatta.add(kagi)
        if iu:
            iu("  %d回目: %s %s" % (wa, na, json.dumps(hiki, ensure_ascii=False)[:60]))
        try:
            res = DOUGU[na][0](hiki)
        except Exception as e:
            res = "道具が失敗しました: %s: %s" % (type(e).__name__, e)
        keika.append((na, hiki, str(res)))
    # 打ち切り。分かった範囲で答えさせる。
    # ★ **道具の結果を 捨てないこと。**
    #   まとめの1回が失敗しても、調べた中身は既に手元にある。
    #   実際に起きた（2026-09-06）: モデルが JSON を書いている途中で切れ、
    #   llama-server の解析器が転んで HTTP 500 を返した
    #     W common_chat_peg_parse: unparsed peg-native output: {"答え":"1
    #   そのとき「だめでした」とだけ言って、取れていたフォルダの中身を捨てていた。
    #   長い答えほど切れやすいので、**短く答えろ**と言っておく。
    r = sensei.kiku(_atama() + _shippo(toi, keika)
                    + "\n道具はもう使えません。分かった範囲で "
                      '{"答え":"…"} だけを、**200字以内で**返してください。'
                      "分からなければ そう答えてください。",
                    cfg, timeout=timeout,
                    system="JSON をひとつだけ返す係です。短く答えること。")
    j = teachers.extract_json(r.get("答え") or "") or {}
    kotae = str(j.get("答え") or r.get("答え") or "").strip()
    if not kotae and keika:
        # まとめに失敗した。せめて **最後に道具が返したもの** を そのまま見せる
        na, hiki, res = keika[-1]
        for k in reversed(keika):
            if not str(k[2]).startswith("※"):
                na, hiki, res = k
                break
        kotae = ("うまくまとめられませんでした。道具（%s）が返したものを"
                 "そのまま出します:\n%s" % (na, str(res)[:800]))
        return {"答え": kotae, "経過": keika, "回数": len(keika),
                "ミリ秒": int((time.monotonic() - t0) * 1000), "error": None}
    return {"答え": kotae, "経過": keika,
            "回数": len(keika), "ミリ秒": int((time.monotonic() - t0) * 1000),
            "error": r.get("error") if not kotae else None}
