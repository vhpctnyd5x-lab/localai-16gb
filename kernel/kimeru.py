# -*- coding: utf-8 -*-
"""kimeru ── 文章を書かせずに、次の1トークンの確率で決める（2026-09-18）。

  Jev（TypeSafe AI・元 OpenAI の Diogo Almeida・9/15 公開）の「System One モデル」の考え方:
    答えの形（N択・段階・はい/いいえ）を先に決めておき、文章を書かせず 確率だけ返す。
  向こうは専用に学習したモデル（API のみ・重みは非公開）。こちらは手元の頭脳の
  **次の1トークンの確率**（llama-server /completion の n_probs）で同じ形を作る。

  効き目: 「道具: 言い方」を 30トークン書かせる（2〜3秒）→ 1トークン。
          確率が取れるので「自信が無ければ雑談」と線が引ける。形式崩れ（道具: 用件名: 言い方）が無い。
  ★ 校正はされていない（Jev の RLCD に当たる学習は無い）。線（閾値）は物差しで測って決める。
  ★ 頼み文の頭は 雑談と同じ（system＋会話）にして、頭脳が前の分を使い回せるようにする。
    決める質問は **最後に** 足す（前へ足すと全部読み直しになる）。

  選択肢の記号は 数字 1桁（0〜9）。Qwen は数字を 1桁ずつ 1トークンにするので、
  どの記号も「次の1トークン」で読める（英字の大小や仮名は 1トークンとは限らない）。
"""
from __future__ import annotations
import json as _json
import time
import urllib.request

import teachers as _T

N_PROBS = 40          # 上位いくつの確率を貰うか（記号 10個ぶんが入れば足りる）
N_PROBS_NAMAE = 1500  # 名前で選ぶ時。許された字の確率が小さくても（頭脳が答えを書きたがっている時）比べられるように 深く貰う


def _katachi(system: str, user: str, oshiri: str = "", timeout: int = 20) -> str:
    """system＋user を、モデルが読む一続きの形にする（/apply-template・思考なし）。oshiri は答えの書き出し"""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": user})
    return _T._katachi(msgs, False, timeout) + (oshiri or "")


def _gyou_kara(rows) -> dict:
    """1トークンぶんの上位確率（版で名前が違う: top_logprobs[{token,logprob}] ／ top_probs[{token,prob}] ／ probs[{tok_str,prob}]）→ {字: p}"""
    import math
    out = {}
    for row in rows or []:
        tok = row.get("token", row.get("tok_str", ""))
        p = float(row["prob"]) if "prob" in row else math.exp(float(row.get("logprob", -99)))
        out[tok] = out.get(tok, 0.0) + p
    return out


def tsugi(prompt: str, timeout: int = 180, n_predict: int = 1) -> dict:
    """次の n_predict トークンの上位確率を貰う。
    戻り値 {"確率": 1つ目の {字: p}, "確率列": [位置ごとの {字: p}], "先頭": 出た文字列, "ms", "tokens": 読んだ数, "cached": 使い回した数}"""
    _T._tomeru_ka()
    t0 = time.monotonic()
    payload = {"prompt": prompt, "n_predict": n_predict, "n_probs": N_PROBS, "temperature": 0.0,
               "cache_prompt": True, "stream": False}
    req = urllib.request.Request(_T.LOCAL_URL.rstrip("/") + "/completion",
                                 data=_json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        d = _json.loads(f.read().decode("utf-8"))
    retsu = [_gyou_kara(c.get("top_logprobs") or c.get("top_probs") or c.get("probs"))
             for c in (d.get("completion_probabilities") or [])]
    return {"確率": retsu[0] if retsu else {}, "確率列": retsu, "先頭": d.get("content", ""),
            "ms": int((time.monotonic() - t0) * 1000),
            "tokens": (d.get("timings") or {}).get("prompt_n"), "cached": d.get("tokens_cached")}


def _kasa(kakuritsu: dict, kigou: list) -> tuple:
    """{字: p} から 記号ごとの確率を集める → (記号ごとの割合, 記号に乗った確率の合計)"""
    kasa = {k: 0.0 for k in kigou}
    for tok, p in kakuritsu.items():
        t = tok.strip().strip("*「」()（）.．:：-")
        if t in kasa:
            kasa[t] += p
    total = sum(kasa.values())
    return {k: (v / total if total > 0 else 0.0) for k, v in kasa.items()}, total


def bangou(system: str, user: str, toi: str, timeout: int = 180) -> dict:
    """「群-番」（例 8-3）を 1回で決める。1トークン目 = 群（0 = 道具なし）、3トークン目 = 群の中の番。
    戻り値 {"群": int|None, "番": int|None, "p1", "p2", "かさ1", "かさ2", "出た", "ms", "tokens", "cached"}"""
    prompt = _katachi(system, user + "\n\n【決める】" + toi, timeout=min(20, timeout))
    r = tsugi(prompt, timeout=timeout, n_predict=4)
    retsu = r["確率列"]
    out = {"群": None, "番": None, "p1": 0.0, "p2": None, "かさ1": 0.0, "かさ2": None, "出た": r["先頭"],
           "ms": r["ms"], "tokens": r["tokens"], "cached": r["cached"]}
    if not retsu:
        return out
    wari, kasa = _kasa(retsu[0], [str(i) for i in range(10)])
    g = max(wari, key=wari.get) if kasa > 0 else None
    out.update(p1=round(wari.get(g, 0.0), 3) if g else 0.0, かさ1=round(kasa, 3))
    if g is None or g == "0":
        return out
    out["群"] = int(g)
    # 「8-3」の 3。出た文字列から「-」の次の数字の位置を探す（"8-3" なら 3トークン目、"8 - 3" のような崩れも拾う）
    for i in range(1, len(retsu)):
        wari2, kasa2 = _kasa(retsu[i], [str(k) for k in range(10)])
        if kasa2 >= 0.3:
            b = max(wari2, key=wari2.get)
            out.update(番=int(b), p2=round(wari2[b], 3), かさ2=round(kasa2, 3))
            break
    return out


def erabu(system: str, user: str, kigou: list, oshiri: str = "", timeout: int = 180) -> dict:
    """記号の列（例 ["0","1",...,"9"]）のどれかを 1トークンで選ぶ。

    戻り値 {"選んだ": 記号 or None, "p": 記号の中での割合, "かさ": 記号に乗った確率の合計（低いと頭脳は別の事を言いたがっている）,
            "全部": {記号: 割合}, "ms": ms}
    """
    prompt = _katachi(system, user, oshiri, timeout=min(20, timeout))
    r = tsugi(prompt, timeout=timeout)
    zenbu, total = _kasa(r["確率"], kigou)
    best = max(kigou, key=lambda k: zenbu[k]) if total > 0 else None
    return {"選んだ": best, "p": zenbu.get(best, 0.0) if best else 0.0, "かさ": total, "全部": zenbu,
            "ms": r["ms"], "先頭": r["先頭"], "tokens": r.get("tokens"), "cached": r.get("cached")}


def hai_iie(system: str, user: str, toi: str, timeout: int = 180) -> dict:
    """はい/いいえ を確率で。user の後ろに toi を足し「1 なら はい、0 なら いいえ」で 1トークン。戻り値に "はい" = p(はい)"""
    u = user + "\n\n【決める】" + toi + " はいなら 1、いいえなら 0。数字を1つだけ書く。"
    r = erabu(system, u, ["0", "1"], timeout=timeout)
    r["はい"] = r["全部"].get("1", 0.0)
    return r


def n_taku(system: str, user: str, toi: str, sentaku: list, nashi: str = "", timeout: int = 180) -> dict:
    """N択（N≦9）。sentaku は選択肢の名前の列。nashi を渡すと 0 = 「どれでもない（nashi の説明）」になる。

    戻り値 erabu() の結果に "名" = 選んだ選択肢の名前（0 なら None）を足したもの
    """
    assert 1 <= len(sentaku) <= 9, "選択肢は 9 まで（数字 1桁で答えさせる）"
    gyou = ["%d %s" % (i + 1, na) for i, na in enumerate(sentaku)]
    if nashi:
        gyou.append("0 " + nashi)
    u = user + "\n\n【決める】" + toi + "\n" + "\n".join(gyou) + "\n数字を1つだけ書く。"
    kigou = [str(i + 1) for i in range(len(sentaku))] + (["0"] if nashi else [])
    r = erabu(system, u, kigou, timeout=timeout)
    sel = r["選んだ"]
    r["名"] = sentaku[int(sel) - 1] if sel and sel != "0" else None
    return r


# ══════════════════════════════════════════════════════════════════
# 名前で選ぶ（文法で縛る）── 番号の引き当ては小さな頭脳には難しい（実測 9/24）。用件の **名前** なら意味で選べる。
#   llama.cpp の文法（GBNF）で「一覧の名前のどれか」しか書けなくし、確率は 生の上位確率から
#   「許された字の中での割合」を 1トークンずつ掛けて出す（先頭の字が同じ用件があるので、分かれるまで辿る）。
# ══════════════════════════════════════════════════════════════════
_TOK = {}          # 名前 → トークンの列（/tokenize・1回だけ）


def _tokens(name: str) -> list:
    if name not in _TOK:
        req = urllib.request.Request(_T.LOCAL_URL.rstrip("/") + "/tokenize",
                                     data=_json.dumps({"content": name, "with_pieces": True}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as f:
            _TOK[name] = [t["piece"] for t in _json.loads(f.read().decode("utf-8"))["tokens"]]
    return _TOK[name]


def _bunpou(names: list) -> str:
    """文法: 一覧の名前のどれか 1つ。★ 先頭の空白を許す形（" "? ）も試したが、空白 1字を先に出してから
    不自然な区切りで名前を書き 悪くなった（17/36）。「用件:」の書き出しも 空白を呼ぶので使わない。"""
    return "root ::= " + " | ".join('"%s"' % n.replace('\\', '\\\\').replace('"', '\\"') for n in names)


def namae(system: str, user: str, toi: str, names: list, timeout: int = 180, oshiri: str = "") -> dict:
    """一覧の名前のどれかを書かせる（文法で縛る）。戻り値 {"名": 名前 or None, "p": その名前の割合, "かさ": 先頭で許された字に乗った確率,
    "出た": 出た文字列, "ms", "tokens", "cached"}。名前が一覧に無い形で出たら 名 = None

    確率の出し方（バイト列で辿る。字の区切りはモデル次第で変わり、途中で切れた UTF-8 の字も来るため）:
      位置ごとに「ここまでの文字列に続けて、まだ候補に残る名前の頭になる字」を許された字とし、
      その中で 実際に出た字の割合を掛ける。先頭の空白は無視する。
    """
    prompt = _katachi(system, user + "\n\n【決める】" + toi, oshiri, timeout=min(20, timeout))
    _T._tomeru_ka()
    t0 = time.monotonic()
    payload = {"prompt": prompt, "n_predict": max(len(_tokens(n)) for n in names) + 2, "n_probs": N_PROBS_NAMAE,
               "temperature": 0.0, "cache_prompt": True, "stream": False, "grammar": _bunpou(names)}
    req = urllib.request.Request(_T.LOCAL_URL.rstrip("/") + "/completion",
                                 data=_json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        d = _json.loads(f.read().decode("utf-8"))
    deta = (d.get("content") or "").strip()
    out = {"名": None, "p": 0.0, "かさ": 0.0, "出た": deta, "ms": int((time.monotonic() - t0) * 1000),
           "tokens": (d.get("timings") or {}).get("prompt_n"), "cached": d.get("tokens_cached")}
    na = deta if deta in names else next((n for n in sorted(names, key=len, reverse=True) if deta.startswith(n)), None)
    if na is None:
        return out
    out["名"] = na
    nb = {n: n.encode("utf-8") for n in names}
    cp = d.get("completion_probabilities") or []
    p, moji = 1.0, b""
    for i, c in enumerate(cp):
        tb = bytes(c.get("bytes") or [])
        rows = c.get("top_logprobs") or c.get("top_probs") or c.get("probs") or []
        kouho = [n for n in names if nb[n].startswith(moji.lstrip(b" "))]
        if len(kouho) <= 1:
            break
        def yurusu(b):
            s = (moji + b).lstrip(b" ")
            return any(nb[n].startswith(s) or s.startswith(nb[n]) for n in kouho)
        import math
        kasa = 0.0
        mine = 0.0
        for r in rows:
            b = bytes(r.get("bytes") or [])
            pr = float(r["prob"]) if "prob" in r else math.exp(float(r.get("logprob", -99)))
            if yurusu(b):
                kasa += pr
                if b == tb:
                    mine = pr
        if i == 0:
            out["かさ"] = round(kasa, 3)
        if tb != b" ":
            p *= (mine / kasa) if kasa > 0 else 0.5
        moji += tb
    out["p"] = round(p, 3)
    return out
