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
    s = FUKASA[fukasa]
    t0 = time.monotonic()
    res = {"text": "", "考えた字数": 0, "回数": 0, "ms": 0, "error": None,
           "深さ": fukasa, "深さの名": s["名"]}

    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})

    def hitokuchi(m, nokori):
        katachi = _katachi(m, s["思考"], min(20, max(5, int(nokori))))
        kangae = ""
        if s["思考"]:
            # ★ <think> は こちらから開ける。開けないと「思考するかどうか」を
            #   モデルの気分に任せることになり、深さが効かない回が出る。
            katachi += "<think>\n"
            r = _tsuzuki(katachi, s["考える上限"], max(10, int(nokori)),
                         stop=["</think>"])
            kangae = r.get("content") or ""
            if (r.get("stop_type") or "") != "word":
                kangae += SHIMEKIRI
            katachi += kangae + "\n</think>\n\n"
        r2 = _tsuzuki(katachi, kotae_cap, max(10, int(nokori)))
        return (r2.get("content") or ""), len(kangae)

    try:
        out, k = hitokuchi(msgs, timeout)
        res["回数"], res["考えた字数"] = 1, k
        if s["見直し"] and out.strip():
            nokori = timeout - (time.monotonic() - t0)
            if nokori > 8:
                m2 = msgs + [{"role": "assistant", "content": out},
                             {"role": "user", "content": MINAOSHI}]
                try:
                    out2, k2 = hitokuchi(m2, nokori)
                    if out2.strip():
                        out, res["回数"] = out2, 2
                        res["考えた字数"] += k2
                except Exception:
                    pass          # 見直しに失敗しても 下書きは返す
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
