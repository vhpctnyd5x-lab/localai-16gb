#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雑談の頼み文が 1ターンごとに どれだけ読み直されるか（chat._build_prompt の並び）。

  python3 hakaru_zatsudan.py                 … 今の並び（会話が先）
  python3 hakaru_zatsudan.py --narabi 関連が先  … 前の並び
6ターンの作り物の会話を、アプリと同じ組み立て（chat.SYS + _build_prompt）で 8080 の頭脳に読ませ、
timings.prompt_n（読み直したトークン）と prompt_ms を出す。頭脳は立っている前提（hashiru_*.sh と同じ）。
"""
import argparse, json, os, sys, time, urllib.request
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel") if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
ap = argparse.ArgumentParser(); ap.add_argument("--narabi", default=None); ap.add_argument("--port", type=int, default=8080)
a = ap.parse_args()
if a.narabi:
    os.environ["KERNEL_ZATSUDAN_NARABI"] = a.narabi
import chat

KAIWA = [("こんにちは。今日は天気がいいね", "そうですね、散歩日和です。"),
         ("昨日は映画を見たよ。SFのやつ", "どんな話でしたか？"),
         ("宇宙船で火星に行く話。長かった", "3時間くらいですか？"),
         ("2時間半。途中で寝そうになった", "それは長いですね。"),
         ("今度は何を見ようかな", "ドキュメンタリーはどうですか？"),
         ("いいね。おすすめある？", "自然ものが人気です。")]
MUKASHI = [("user", "私は犬を飼っている。名前はポチ"), ("user", "コーヒーは苦手で紅茶が好き"),
           ("assistant", "先週はラーメンの話をしましたね"), ("user", "誕生日は3月です")]


class _Kioku:
    def facts(self): return {"名前": "あきと", "住まい": "東京", "好き": "紅茶"}
    def recall(self, text, n=2, exclude_ids=None):   # 毎回ちがう2件（本物の recall も問いごとに変わる）
        k = sum(map(ord, text)) % len(MUKASHI)
        return [{"role": r, "text": t, "score": 0.5} for r, t in (MUKASHI[k], MUKASHI[(k + 1) % len(MUKASHI)])]


def kiku(prompt):
    body = {"model": "local", "temperature": 0, "max_tokens": 4, "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": chat.SYS}, {"role": "user", "content": prompt}]}
    req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % a.port, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return (json.loads(r.read().decode("utf-8")).get("timings") or {})


hist, mem, rows = [], _Kioku(), []
print("===== 雑談の読み直し（並び: %s） =====" % chat.NARABI)
for i, (u, asst) in enumerate(KAIWA, 1):
    p = chat._build_prompt(u, hist, mem)
    tm = kiku(p)
    rows.append({"ターン": i, "prompt_n": tm.get("prompt_n"), "cache_n": tm.get("cache_n"), "秒": round((tm.get("prompt_ms") or 0) / 1000, 2), "字数": len(p)})
    print("  %d: 読み直し %4s トークン（使い回し %4s）%5.1f秒  頼み文 %d字" % (i, tm.get("prompt_n"), tm.get("cache_n"), (tm.get("prompt_ms") or 0) / 1000, len(p)))
    hist += [{"id": 2 * i, "role": "user", "text": u}, {"id": 2 * i + 1, "role": "assistant", "text": asst}]
ato = rows[1:]
print("2〜6ターン: 読み直し 合計 %d トークン・%.1f秒（1ターン %.0f トークン）" % (sum(r["prompt_n"] or 0 for r in ato), sum(r["秒"] for r in ato), sum(r["prompt_n"] or 0 for r in ato) / len(ato)))
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "kekka"), exist_ok=True)
json.dump({"並び": chat.NARABI, "ターン": rows}, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "kekka", "zatsudan_%s.json" % chat.NARABI), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
