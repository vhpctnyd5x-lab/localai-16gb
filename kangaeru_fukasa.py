#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kangaeru_fukasa.py -- ローカル LLM に「考える深さ」を付ける（依存なしの1ファイル）

  Reasoning-effort dial for a local llama.cpp server.
  Raises answer quality WITHOUT using a single extra byte of RAM.

──────────────────────────────────────────────────────────────────
 なぜこれが要るのか
──────────────────────────────────────────────────────────────────
  「もっと考えさせたい」は、ふつう **大きいモデルに載せ替える** ことで叶える。
  ところが 16GB の機械では、いま載せている 8.6GB より大きいものは もう入らない。

  考える量は **RAM を食わない。食うのは時間だけ。**
  だから深さは、文脈を伸ばすのではなく **手数** で稼ぐ。

      深さ0 さっと   … 思考しない                          1回
      深さ1 ふつう   … 思考 256 トークンまで                1回
      深さ2 じっくり … 思考 1024 トークンまで               1回
      深さ3 とことん … じっくりで下書き → 自分で見直す      2回

  ★ どの深さでも 1回の呼び出しは 1スロットぶんの文脈に収まる。
    深さ3が長いのは「1回が長い」からではなく「2回やる」から。
    **だから深さを上げても RAM は 1バイトも増えない。**

──────────────────────────────────────────────────────────────────
 思考の上限を、どうやって効かせているか
──────────────────────────────────────────────────────────────────
  /v1/chat/completions では「思考だけに上限」をかけられない。
  max_tokens で切ると **考えている途中で終わって答えが1文字も出ない。**

  → /apply-template で頼み文の形だけ作らせ、/completion を 2段に分ける:
       ① …assistant\\n<think>\\n から "</think>" が出るまで（上限つき）
       ② ①の続きに </think> をこちらで閉じて、答えだけ書かせる

  ★ 落とし穴: **黙って閉じると答えが暴走する。**
    考えの途中でいきなり </think> が来ると、モデルは「まだ考えている最中」の
    つもりで長々と書き続ける（1800 トークン以上書いた例を実測）。
    閉じる前に **一言だけ断りを入れる**こと。下の SHIMEKIRI がそれ。

──────────────────────────────────────────────────────────────────
 使いかた
──────────────────────────────────────────────────────────────────
    import kangaeru_fukasa as KF
    r = KF.kiku("12個を3人で分けて余りは？", fukasa=2)
    print(r["text"], r["考えた字数"], r["回数"])

    # 深さを選ばせたくないときは おまかせ（問いを見てこちらが決める）
    r = KF.kiku("りんごを3個ずつ4人に配ると 何個いりますか。", fukasa=KF.OMAKASE)
    print(r["深さの名"])          # → じっくり

  llama-server 側:
    llama-server -m モデル.gguf -ngl 0 -c 8192 -np 2 -cb --host 127.0.0.1 --port 8080
"""
import json as _json
import os
import time
import urllib.error
import urllib.request

URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:8080")

FUKASA = {
    0: {"名": "さっと",   "思考": False, "考える上限":    0, "見直し": False},
    1: {"名": "ふつう",   "思考": True,  "考える上限":  256, "見直し": False},
    2: {"名": "じっくり", "思考": True,  "考える上限": 1024, "見直し": False},
    3: {"名": "とことん", "思考": True,  "考える上限": 1024, "見直し": True},
}

# 考える時間が尽きたときに、思考の末尾へ足す一言。
# ★ これが無いと 答えが暴走する（上の説明を読むこと）。
SHIMEKIRI = "\n（ここまで。考える時間が尽きたので、いまの見立てで答えを出す）"

# ══════════════════════════════════════════════════════════════════
#  おまかせ ── 問いを見て 深さを自動で決める
# ══════════════════════════════════════════════════════════════════
#  深さを毎回 人が選ぶのは面倒なので、問いの形から見当をつける。
#
#  ★ この見立てで **絶対に外してはいけない向き** がある。
#      取りこぼし（考えるべき問いを 深さ0 で答える）→ **答えを間違える**
#      無駄（簡単な問いを 深さ2 で考える）        → 時間を損するだけ
#    だから **取りこぼし 0 を守り、その中で無駄を減らす**。逆をやらないこと。
#
#  ★ 実測（125件。深さ0 で解けたか / 深さ2 で初めて解けたか を実際に測って
#    札を付けたもの）で調整した:
#        前（語が1つでも当たる or 42字以上）… 取りこぼし 0 / 無駄 46%
#        後（下の形）                      … 取りこぼし 0 / 無駄 28%
#    50字を 60字に伸ばすと 取りこぼしが 0→7件 出た。**50が崖の手前**。
#
#  ★ 正直に書いておくべきこと:
#    (1) その125件は **算数の問いばかり**。ふつうの会話で当たるかは未測定。
#    (2) 下の「弱い語」の枝は、その125件では **一度も効いていない**
#        （強い語と長さだけで同じ数字になる）。効くと示せてはいない。
#        材料の外での保険として置いてあるだけ。証明済みとして扱わないこと。
_TSUYOI = ("平均", "何曜日", "何番目", "日後", "いくつありますか", "それぞれ",
           "全部で", "合わせて", "差は", "比べ", "くらべ", "順番", "並べ",
           "なぜ", "理由", "どうやって", "手順")
# 1つでは足りない語。「おつりは?」は一息で出る。3つ揃うと手順くさい
_YOWAI = ("%", "パーセント", "おつり", "時速", "のこり", "残り", "持っていま",
          "ずつ", "そこから", "引いて", "合計")
_NAGASA = 50

OMAKASE = -1          # kiku(fukasa=OMAKASE) で おまかせになる


def miru(toi: str) -> int:
    """問いを見て 深さ(0 か 2)を決める。"""
    toi = (toi or "").strip()
    if any(g in toi for g in _TSUYOI):
        return 2
    if sum(1 for g in _YOWAI if g in toi) >= 3:
        return 2
    return 2 if len(toi) >= _NAGASA else 0


# 「とことん」で 下書きを見直させるときの言いつけ。
# ★ 答えの **形** は変えさせない。JSON を返す係なら JSON のまま返させる。
MINAOSHI = (
    "上は あなた自身の下書きです。\n"
    "もう一度 落ち着いて確かめてください。計算・数え・日付・条件の見落としを"
    "とくに疑うこと。\n"
    "直すところが無ければ 下書きをそのまま出してください。\n"
    "**最終的な答えだけ**を、下書きと同じ形で出してください。"
    "「見直しました」などの前置きは書かないこと。"
)


def _post(path, payload, timeout):
    req = urllib.request.Request(
        URL.rstrip("/") + path,
        data=_json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return _json.loads(f.read().decode("utf-8"))


def _katachi(msgs, think, timeout):
    """会話を、モデルが読む一続きの文字列に直してもらう。

    ★ 自前で <|im_start|> を組み立てないこと。テンプレートが変わったとき
      静かにずれる。LoRA を焼いてあるなら、形が1バイト違うだけで効かなくなる。
    """
    payload = {"messages": msgs}
    if not think:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return _post("/apply-template", payload, timeout)["prompt"]


def _tsuzuki(prompt, n_predict, timeout, stop=None, temp=0.0):
    payload = {"prompt": prompt, "n_predict": n_predict, "temperature": temp,
               "cache_prompt": True, "stream": False}
    if stop:
        payload["stop"] = stop
    return _post("/completion", payload, timeout)


def kiku(prompt, system=None, fukasa=0, timeout=300, kotae_cap=700):
    """1件たずねる。戻りは dict。

    {"text": 答え, "考えた字数": int, "回数": int, "ms": int, "error": str|None}
    """
    if fukasa == OMAKASE:          # おまかせ: 問いを見て こちらで決める
        fukasa = miru(prompt)
    # ★ 知らない深さは **例外ではなく いつもの形** で返す。
    #   ここだけ KeyError が素通りすると、呼ぶ側の作りが揃わない。
    if fukasa not in FUKASA:
        return {"text": "", "考えた字数": 0, "回数": 0, "ms": 0,
                "深さ": fukasa, "深さの名": "?",
                "error": "深さは %s のどれか。もらったのは %r"
                         % (sorted(FUKASA) + [OMAKASE], fukasa)}
    s = FUKASA[fukasa]
    t0 = time.monotonic()
    # ★ 締切は **最初に1回だけ** 決める。
    #   前は「考える」と「答える」に同じ nokori を渡していたので、
    #   timeout=300 が「全体300秒」を意味していなかった（深さ3なら最悪4倍）。
    shimekiri = t0 + timeout

    def nokori_byou():
        """残り秒。**尽きていたら そこで止める。**
        ★ 前は下限10秒を敷いていたので、timeout=6 でも 10秒待っていた。
          下限は「尽きたら止める」に置きかえる。約束した時間は守る。"""
        n = shimekiri - time.monotonic()
        if n <= 0:
            raise TimeoutError("決めた時間（%d秒）を使い切った" % timeout)
        return n

    res = {"text": "", "考えた字数": 0, "回数": 0, "ms": 0, "error": None,
           "深さ": fukasa, "深さの名": s["名"],
           "見直した": False, "見直しのしくじり": None}

    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})

    def hitokuchi(m):
        """1回ぶん（考える → 答える）。残り時間は **その都度** 計り直す。"""
        katachi = _katachi(m, s["思考"], min(20, max(1, int(nokori_byou()))))
        kangae = ""
        if s["思考"]:
            # ★ <think> は こちらから開ける。開けないと「思考するかどうか」を
            #   モデルの気分に任せることになり、深さが効かない回が出る。
            katachi += "<think>\n"
            r = _tsuzuki(katachi, s["考える上限"], max(1, int(nokori_byou())),
                         stop=["</think>"])
            kangae = r.get("content") or ""
            if (r.get("stop_type") or "") != "word":
                kangae += SHIMEKIRI
            katachi += kangae + "\n</think>\n\n"
        r2 = _tsuzuki(katachi, kotae_cap, max(1, int(nokori_byou())))
        return (r2.get("content") or ""), len(kangae)

    try:
        out, k = hitokuchi(msgs)
        res["回数"], res["考えた字数"] = 1, k
        if s["見直し"] and out.strip():
            if nokori_byou() > 8:
                m2 = msgs + [{"role": "assistant", "content": out},
                             {"role": "user", "content": MINAOSHI}]
                try:
                    out2, k2 = hitokuchi(m2)
                    if out2.strip():
                        out, res["回数"] = out2, 2
                        res["考えた字数"] += k2
                        res["見直した"] = True
                    else:
                        res["見直しのしくじり"] = "見直しが空だった"
                except Exception as e:
                    # ★ 黙って捨てない。深さ3のつもりが 深さ2 で終わっていた、
                    #   というのが 集計から見えなくなる。
                    res["見直しのしくじり"] = "%s: %s" % (type(e).__name__, e)
            else:
                res["見直しのしくじり"] = "残り時間が足りず 見直しをしなかった"
        res["text"] = out.strip()
    except urllib.error.URLError as e:
        res["error"] = "llama-server（%s）につながりません: %s" % (URL, e)
    except Exception as e:
        res["error"] = "%s: %s" % (type(e).__name__, e)
    res["ms"] = int((time.monotonic() - t0) * 1000)
    if not res["error"] and not res["text"]:
        res["error"] = "空応答"
    return res


if __name__ == "__main__":
    import sys
    toi = " ".join(sys.argv[1:]) or "12個のりんごを3人で分けて、余りは箱に戻します。余りは何個？"
    for f in sorted(FUKASA):
        r = kiku(toi, fukasa=f)
        print("深さ%d %-8s %6.1f秒 考え%5d字 %d回 :: %s"
              % (f, FUKASA[f]["名"], r["ms"] / 1000, r["考えた字数"], r["回数"],
                 (r["text"] or r["error"] or "")[:100].replace("\n", " ")))
