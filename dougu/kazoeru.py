#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kazoeru.py -- 「何通り」「組合せ」のような **数え上げ** を、頭脳に数えさせず Python に数えさせる。

  ★ なぜ要るか（2026-09-11〜12 実測）
    30B-A3B は 7段の「場合分け」が 4/32。考える上限を4倍にしても 1/3・1問20分。
    Q4 でも 2/32、GPU の 550B でも 2,500 トークンでは途中で切れる。
    **数え上げは LLM の得意分野ではない。** Opus も中で表を書いて数える。
    道具の輪（dougu.py）に「けいさん」を置いても、頭脳は自分から使わず 1 例だけ答えた（実測 ×・409秒）。
    → 頭脳の仕事を **「数える」ではなく「数えるプログラムを書く」** に変える。1回・短く・深さ0。

  ★ 別の道で検算する
    同じプログラムをもう一度走らせても同じ間違いをする。**書き方を変えた2本目**を書かせ、
    答えが一致したときだけ「確かめた」と言う。食い違えば 深さ2 で3本目。それでも割れたら「自信がない」。

  ★ 安全
    走らせるのは coderun の使い捨ての部屋（sandbox-exec）。ネット・ファイルに出られない。
    さらに書けるのは **数だけ出すプログラム**。import は math/itertools だけ許す。
"""
from __future__ import annotations
import re, time, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# 「数え上げ」の合図。ここに当たったときだけ、この道に入る
_AIZU = re.compile(r"何通り|なんとおり|通りあり|通りです|組み?合わ?せ.{0,6}(数|いくつ|何)|場合の数|並べ方は|選び方は|分け方は")

_YURUSU_IMPORT = ("math", "itertools", "functools", "collections", "fractions")
_KIKEN = re.compile(r"\b(import\s+(?!(?:math|itertools|functools|collections|fractions)\b)|open\s*\(|subprocess|os\.|sys\.|eval\s*\(|exec\s*\(|__import__|socket|urllib|requests)")

SYSTEM = ("あなたは算数の係。次の問題を **数える Python プログラム** にして書いてください。"
          "考えを書かず、```python と ``` で囲んだプログラムだけを書くこと。"
          "総当たりでよい（範囲は問題の数から決める）。最後に print(答え) で **整数を1つだけ** 出すこと。"
          "使ってよいのは標準の math と itertools だけ。入力は受け取らない。")

_FENCE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)


def aizu(text: str) -> bool:
    """この問いは数え上げか"""
    return bool(_AIZU.search(text or ""))


def _torisdasu(out: str) -> str | None:
    m = _FENCE.findall(out or "")
    if m:
        return m[-1].strip()
    # フェンスが無ければ、print( を含む行の塊を拾う
    if "print(" in (out or ""):
        return out.strip()
    return None


def _anzen(src: str) -> str | None:
    if not src or len(src) > 4000:
        return "長すぎる"
    if _KIKEN.search(src):
        return "許していない書きかた（ファイル・ネット・外のプログラム）"
    if "print(" not in src:
        return "print が無い"
    return None


def _hashiru(src: str) -> tuple[int | None, str]:
    import coderun
    r = coderun.run(src, lang="python", timeout=20, force=False)
    out = (r.get("出力") or "").strip()
    err = (r.get("エラー") or "").strip()
    if err and not out:
        return None, err[:300]
    nums = re.findall(r"-?\d+", out.splitlines()[-1] if out else "")
    if not nums:
        return None, "整数が出ていない: %r" % out[:80]
    return int(nums[-1]), out[:200]


def _kaku(toi: str, fukasa: int, betsu: bool, timeout: int) -> tuple[str | None, str]:
    """頭脳にプログラムを書かせる。betsu=True なら「別の書き方で」"""
    import teachers as T
    prompt = toi if not betsu else (toi + "\n\n（さっきとは **別の書き方** で。ループの組み方を変えること。）")
    r = T.ask_one("local:main", prompt, system=SYSTEM, timeout=timeout, fukasa=fukasa)
    if r.get("error"):
        return None, "頭脳のエラー: %s" % r["error"]
    src = _torisdasu(r.get("text") or "")
    if not src:
        return None, "プログラムが取れなかった"
    ng = _anzen(src)
    if ng:
        return None, "危ない: " + ng
    return src, ""


def toku(toi: str, iu=None, timeout: int = 120) -> dict:
    """数え上げを解く。戻り: {"答え": int|None, "確かめ": str, "経過": [..], "ミリ秒": int}"""
    t0 = time.time()
    keika = []
    say = iu or (lambda s: None)
    kotae = []
    for ban, (fukasa, betsu) in enumerate(((0, False), (0, True), (2, False)), 1):
        say("  数え上げ: %d本目のプログラムを書かせる（深さ%d）" % (ban, fukasa))
        src, ng = _kaku(toi, fukasa, betsu, timeout)
        if not src:
            keika.append("%d本目: %s" % (ban, ng)); say("    " + ng); continue
        v, memo = _hashiru(src)
        keika.append("%d本目: %s → %s" % (ban, src.replace("\n", " / ")[:160], v if v is not None else memo))
        say("    走らせた → %s" % (v if v is not None else memo[:60]))
        if v is not None:
            kotae.append(v)
        # 2本が一致したら確定
        if len(kotae) >= 2 and kotae[-1] == kotae[-2]:
            return {"答え": kotae[-1], "確かめ": "別の書き方の2本が一致", "経過": keika,
                    "ミリ秒": int((time.time() - t0) * 1000)}
        if len(kotae) == 3:
            break
    ms = int((time.time() - t0) * 1000)
    if len(kotae) >= 2:
        from collections import Counter
        v, n = Counter(kotae).most_common(1)[0]
        if n >= 2:
            return {"答え": v, "確かめ": "3本中%d本が一致" % n, "経過": keika, "ミリ秒": ms}
        return {"答え": None, "確かめ": "3本とも食い違った（%s）。自信がない" % kotae, "経過": keika, "ミリ秒": ms}
    if len(kotae) == 1:
        return {"答え": kotae[0], "確かめ": "1本だけ走った（確かめられていない）", "経過": keika, "ミリ秒": ms}
    return {"答え": None, "確かめ": "プログラムが走らなかった", "経過": keika, "ミリ秒": ms}


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "5円切手、9円切手、12円切手を0枚以上使って合計162円にする枚数の組合せは何通り？"
    r = toku(q, iu=print)
    print(r)
