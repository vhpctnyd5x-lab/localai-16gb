#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_kaki.py -- 物差し: 手元のモデルの「書き出し」（tg）の速さを、起動の指定ごとに測る。

  ★ なぜ（2026-09-16）
    読み込みは hakaru_yomi で 2.3倍にした。雑談・道具の答えで人が待つのは 書き出し（5〜6 t/s）。
    2026-09-10 の「-t 12 が最速」は KV q8_0・Metal あり の時の数字。土台が変わったので測り直す。

  ★ 測り方
    画面は使わない。モデルを 8090 で自分で立て、同じ問いで 200 トークン書かせるのを 3回 → t/s の中央値。
    投機（ngram）は文の繰り返しに効くので、問いは アプリの雑談に近いもの（説明文）にする。
"""
from __future__ import annotations
import json, os, statistics, sys, time, urllib.request
import hakaru_yomi as Y

TOI = "日本の四季（春・夏・秋・冬）について、それぞれの季節の特徴と過ごし方を 2文ずつで説明してください。"
SYSTEM = "あなたは親切な相棒。日本語で簡潔に答える。"
KIHON = ["-dev", "none", "--cache-reuse", "16"]


DRAFT = os.path.expanduser("~/LocalAI_mirror/models/Qwen3-0.6B-Q8_0.gguf")   # 下書き役（同じ語彙の小さい Qwen3）


def opts(t="12", tb=None, spec="ngram-simple", kv=None, fa="off", draft=None, nmax=None):
    a = ["-t", t, "-ngl", "0", "-ub", "256"] + KIHON
    if tb: a += ["-tb", tb]
    if kv: a += ["-ctk", kv, "-ctv", kv]
    if fa: a += ["-fa", fa]
    if draft: a += ["-md", draft, "--spec-type", "draft-simple", "-ngld", "0"]
    elif spec: a += ["--spec-type", spec]
    if nmax: a += ["--spec-draft-n-max", str(nmax)]
    return a


SHITEI = [
    ("a 今のまま（-t 12・ngram-simple・KV f16）", opts()),
    ("b -t 6",                                 opts(t="6")),
    ("c -t 8",                                 opts(t="8")),
    ("d -t 6 で読み込みだけ 12(-tb 12)",        opts(t="6", tb="12")),
    ("e 投機なし",                             opts(spec=None)),
    ("f 投機 ngram-cache",                     opts(spec="ngram-cache")),
    ("g -fa off",                              opts(fa="off")),
    ("h KV q8_0（前の形）",                     opts(kv="q8_0")),
    # ★ 2026-09-17: 下書き役のモデル（Qwen3-0.6B Q8_0・0.6GB）に先を書かせ、本体は答え合わせだけ（speculative decoding）。
    #   ngram は「文の繰り返し」にしか効かないが、下書き役は新しい文にも効く。RAM は +0.7GB。
    ("i 下書き役 Qwen3-0.6B",                  opts(draft=DRAFT)),
    ("j 下書き役 0.6B・先読み 8",               opts(draft=DRAFT, nmax=8)),
    ("k 下書き役 0.6B・先読み 4",               opts(draft=DRAFT, nmax=4)),
]


# ★ --nagai: 文脈を深く（約3000トークンの前置き）してから書かせる。
#   2026-09-04 の実測（RESULTS.md 38-A）では Flash Attention を切ると 深さ4096 で +49%、浅い文脈では逆に損だった。
#   用途（雑談は深い・操作の輪は浅い）で答えが変わるので、両方を測る。
NAGAI = [False]
_MAEOKI = ("以下は参考の資料です。読んだうえで、あとの問いに答えてください。\n\n" +
           "".join("第%d章 山の村の一年。春には雪どけの水が谷を下り、田に水が張られる。村の人びとは朝早くから畑に出て、"
                   "種をまき、苗を植える。夏は日が長く、子どもたちは川で泳ぎ、夜は虫の声を聞きながら眠る。"
                   "秋には稲が黄金色に実り、村じゅうで刈り入れをする。祭りの太鼓が山にひびき、収穫を祝う。"
                   "冬は雪が深く、家々は静かになる。囲炉裏のまわりで昔話を語り、春を待つ。\n" % i for i in range(1, 31)))


def kiku():
    toi = (_MAEOKI + "\n問い: " + TOI) if NAGAI[0] else TOI
    body = {"model": "local", "temperature": 0, "max_tokens": 200, "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": toi}]}
    req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % Y.PORT,
                                 data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read().decode("utf-8"))
    tm = d.get("timings") or {}
    return tm, ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def hakaru(midashi, o, srvlog):
    print("── %s" % midashi); print("   指定: %s" % " ".join(o))
    p, koto = Y.tateru(o, srvlog)
    if not p:
        print("   ×  %s\n" % koto); Y.kesu(); return None
    try:
        kiku()                                   # 最初の1回は捨てる
        tps, n = [], 0
        for _ in range(3):
            tm, kotae = kiku()
            tps.append(float(tm.get("predicted_per_second") or 0)); n = tm.get("predicted_n", 0)
        med = statistics.median(tps)
        print("   立ち上げ: %s ／ 書き出し: %s t/s → 中央 %.2f t/s（%d トークン） ／ 読み込み %.1f t/s（文脈 %d）"
              % (koto, " / ".join("%.2f" % x for x in tps), med, n, float(tm.get("prompt_per_second") or 0), int(tm.get("prompt_n") or 0) + int(tm.get("cache_n") or 0)))
        print("   答えの頭: %s\n" % kotae.replace("\n", " ")[:60])
        # ★ 温度0なら投機で出力は変わらないはず。変わったら速くても採らない（9/10 の下書き役は変わっていた）
        return {"名": midashi, "tg": med, "n": n, "出力": kotae}
    except Exception as e:
        print("   ×  つまずいた: %s: %s\n" % (type(e).__name__, str(e)[:120])); return None
    finally:
        Y.kesu(p)


def main():
    if Y._ikiteru():
        print("llama-server がもう動いています（1本だけの決まり）"); return 2
    args = sys.argv[1:]
    if "--nagai" in args:
        NAGAI[0] = True; args.remove("--nagai")
    erabu = [x for x in SHITEI if not args or any(x[0].startswith(a) for a in args)]
    print("===== 書き出しの速さ %s%s =====\n" % (time.strftime("%m/%d %H:%M"), "（深い文脈・前置き約%d字）" % len(_MAEOKI) if NAGAI[0] else "（浅い文脈）"))
    kekka = []
    with open(os.path.join(Y.KEKKA, "kaki_srv.log"), "ab") as srvlog:
        for midashi, o in erabu:
            r = hakaru(midashi, o, srvlog)
            if r: kekka.append(r)
    print("===== まとめ（書き出し t/s が高いほど速い）=====")
    moto = next((r["出力"] for r in kekka if r["名"].startswith("a ")), None)
    for r in sorted(kekka, key=lambda r: -r["tg"]):
        onaji = "" if moto is None or r["名"].startswith("a ") else ("  出力 同じ" if r["出力"] == moto else "  ★出力 ちがう（採らない）")
        print("  %-42s %6.2f t/s%s" % (r["名"][:42], r["tg"], onaji))
    with open(os.path.join(Y.KEKKA, "kaki_%s.json" % time.strftime("%m%d_%H%M")), "w", encoding="utf-8") as f:
        json.dump(kekka, f, ensure_ascii=False, indent=1)
    print("===== おわり %s =====" % time.strftime("%H:%M"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
