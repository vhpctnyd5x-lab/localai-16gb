#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""別の頭脳（例: Bonsai 2 27B）の速さと 3問の質を、同じ問いで測る。8080 に立っている前提（hashiru_bonsai.sh）。

  測るもの: 読み込み pp t/s・書き出し tg t/s（llama-server の timings。2回目の数字）、
            monosashi/mondai.jsonl から段ごとに 1問ずつ（--kagiri）を思考なしで解いて 正誤と秒。
  python3 hakaru_bonsai.py --nafuda Bonsai2-27B-PQ2_0 [--url http://127.0.0.1:8080] [--mondai ../monosashi/mondai_7dan.jsonl] [--kagiri 3]
"""
import argparse, json, os, re, sys, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
SYS = "あなたは日本語で短く正確に答える助手です。最終的な答えだけを書いてください。"


def post(url, path, payload, timeout=600):
    req = urllib.request.Request(url.rstrip("/") + path, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.loads(f.read().decode("utf-8"))


def katachi(url, user, think=False):
    payload = {"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": user}]}
    if not think:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return post(url, "/apply-template", payload)["prompt"]


def toku(url, toi, n=200, think=False):
    p = katachi(url, toi, think)
    if think:
        p += "<think>\n"
    t0 = time.monotonic()
    r = post(url, "/completion", {"prompt": p, "n_predict": n, "temperature": 0.0, "cache_prompt": False})
    tm = r.get("timings") or {}
    return r.get("content", ""), time.monotonic() - t0, tm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--nafuda", default="")
    ap.add_argument("--mondai", default=os.path.join(HERE, "..", "monosashi", "mondai.jsonl"))
    ap.add_argument("--kagiri", type=int, default=3)
    ap.add_argument("--think", action="store_true")
    a = ap.parse_args()
    out = {"日付": time.strftime("%Y-%m-%d %H:%M"), "名札": a.nafuda, "問": []}
    # 1) 速さ: 約300トークンの読み込み＋64トークンの書き出し。1回目は捨てる
    nagai = "次の文章を読んで、要点を3つ、それぞれ1行で書いてください。\n" + ("東京都は日本の首都であり、政治・経済・文化の中心である。人口は約1400万人で、23の特別区と多摩地域、島しょ部から成る。" * 6)
    for i in range(2):
        _, sec, tm = toku(a.url, nagai, n=64)
    out["pp"] = round(tm.get("prompt_per_second", 0), 1); out["tg"] = round(tm.get("predicted_per_second", 0), 1)
    out["読んだ"] = tm.get("prompt_n"); out["書いた"] = tm.get("predicted_n")
    print("速さ: 読み込み %.1f t/s（%s トークン）・書き出し %.1f t/s（%s トークン）" % (out["pp"], out["読んだ"], out["tg"], out["書いた"]))
    # 2) 質: 段ごとに 1問（段の低い順）
    rows = [json.loads(l) for l in open(a.mondai, encoding="utf-8") if l.strip()]
    erabi, mita = [], set()
    for r in rows:
        if r.get("段") not in mita:
            mita.add(r.get("段")); erabi.append(r)
    erabi = erabi[-a.kagiri:] if a.kagiri else erabi
    ok = 0
    for r in erabi:
        ans, sec, tm = toku(a.url, r["問"], n=400 if not a.think else 1500, think=a.think)
        kotae = re.sub(r"<think>.*?</think>", "", ans, flags=re.S).strip()
        good = str(r["答"]) in kotae.replace(",", "")
        ok += good
        print("  %s %s段 %-14s %5.1f秒 期待=%s 出た=%s" % ("○" if good else "×", r.get("段"), r.get("型"), sec, r["答"], kotae[:60].replace("\n", " ")))
        out["問"].append({"id": r["id"], "段": r.get("段"), "型": r.get("型"), "正": good, "秒": round(sec, 1), "出た": kotae[:300], "書いた": tm.get("predicted_n")})
    out["正答"] = ok; out["問数"] = len(erabi)
    print("質: %d/%d（この1回の数字）" % (ok, len(erabi)))
    os.makedirs(os.path.join(HERE, "kekka"), exist_ok=True)
    fn = os.path.join(HERE, "kekka", "bonsai_%s_%s.json" % (re.sub(r"[^\w.-]", "_", a.nafuda or "x"), time.strftime("%Y%m%d_%H%M")))
    json.dump(out, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→", os.path.relpath(fn, HERE))


if __name__ == "__main__":
    main()
