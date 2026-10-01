#!/usr/bin/env python3
"""事前学習の「知識の箱」が答えに役立つかを測る（2026-10-01）。

  python3 dougu/chishiki_kouka.py --toi dougu/kekka/codex_1001_toi.jsonl

同じ問いを4通りで手元の頭脳に答えさせ、正答率を比べる。
  A なし        … 何も見ずに答える
  B 今の検索    … 頭脳が書いた検索語で、輪の shiru（jiyuu._knowledge: FTS5 の既定の区切り）を引く
  C 直した検索  … 同じ検索語を言葉に分け、題・本文に含まれるかで点を付け、当たった所の前後を渡す
  D 正しい記事  … 問いを作った記事の根拠の前後を渡す（上限）
事前学習を止め、アプリの llama-server を止めてから測り、終わったら戻す（honban.py j と同じ流れ）。
Claude の Bash では砂箱の外で呼ぶ。知識の箱は読むだけ。
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import honban   # noqa: E402

DB = Path(os.environ.get("KERNEL_GAKUSHUU_DIR", Path.home() / "Library/Application Support/kernel-ai/gakushuu")) / "chishiki.sqlite3"
KOTAE = "質問に、答えだけを短く書いてください。分からなければ「分からない」と書いてください。"
KENSAKU = "次の質問の答えを、学んだ記事から探します。検索語を空白で区切って1〜3語だけ書いてください（説明は書かない）。"
JOSHI = re.compile(r"[\s、。，．,.!?！？「」『』（）()・:：;；]+|について|とは|では|には|から|まで|より|として|の|は|が|を|に|で|と|も|へ|や|か")


def post(path, body, timeout=600):
    request = urllib.request.Request("http://127.0.0.1:8080" + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(request, timeout=timeout))


def ask(system, user, n=48):
    prompt = post("/apply-template", {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                      "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
    return post("/completion", {"prompt": prompt, "n_predict": n, "temperature": 0, "cache_prompt": True})["content"].strip()


def articles():
    with sqlite3.connect(f"file:{urllib.parse.quote(str(DB))}?mode=ro", uri=True) as db:
        return db.execute("SELECT title, text FROM chishiki").fetchall()


def naoshita(query, rows, k=3, width=300):
    """言葉に分けて、題に含まれれば3点・本文に含まれれば1点。当たった所の前後を渡す。"""
    words = [w for w in JOSHI.split(query) if len(w) >= 2]
    scored = []
    for title, text in rows:
        score = sum(3 * (w in title) + (w in text) for w in words)
        if score:
            scored.append((score, title, text))
    scored.sort(key=lambda r: -r[0])
    out = []
    for _, title, text in scored[:k]:
        hit = min((text.find(w) for w in words if w in text), default=0)
        start = max(0, hit - width // 3)
        out.append({"題": title, "本文": text[start:start + width]})
    return out


def seiki(text):
    return re.sub(r"[\s、。,.・「」『』()（）]", "", unicodedata.normalize("NFKC", str(text))).lower()


def atari(answer, row):
    got = seiki(answer)
    return any(seiki(a) and seiki(a) in got for a in [row["答"], *row.get("別解", [])])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--toi", required=True)
    parser.add_argument("--model", default="~/LocalAI_mirror/models/Qwen3.6-35B-A3B-MTP-UD-Q2_K_XL.gguf")
    parser.add_argument("--llama", default="~/LocalAI_mirror/llama-koukai/llama-server")
    parser.add_argument("--out", default=str(honban.KEKKA / "chishiki_kouka.jsonl"))
    parser.add_argument("--joken", default="ABCD", help="測る通り（例 B だけ）")
    args = parser.parse_args()
    toi = [json.loads(line) for line in open(args.toi, encoding="utf-8") if line.strip().startswith("{")]
    rows = articles()
    by_title = {title: text for title, text in rows}
    import tempfile
    scratch = tempfile.mkdtemp(prefix="chishiki-")   # 輪を読み込む時、本物の記録・技・控えに触れない
    os.environ.update({k: scratch for k in ("KERNEL_KIROKU_DIR", "KERNEL_HIKAE_DIR", "KERNEL_TSUIKA_DIR", "KERNEL_WAZA_DIR")})
    import jiyuu   # 輪と同じ検索（今の形）
    was_on = honban.gakushuu_yasumu()
    subprocess.run(["pkill", "-x", "llama-server"])
    time.sleep(3)
    env = dict(os.environ, KOUKAI_VOCAB_KEEP=str(honban.KOUKAI / "dougu/jikken/vocab_keep_9999_q36_ids.txt"))
    server = subprocess.Popen([str(Path(args.llama).expanduser()), "-m", str(Path(args.model).expanduser()), "--port", "8080",
                               "-t", "6", "-ngl", "0", "-c", "8192", "-np", "1", "-cb", "-ub", "256", "--cache-reuse", "16",
                               "-fa", "off", "--reasoning-format", "none", "--spec-type", "none"],
                              stdout=open(honban.KEKKA / "chishiki_kouka_llama.log", "wb"), stderr=subprocess.STDOUT, env=env)
    results = []
    try:
        for _ in range(300):
            try:
                urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2)
                break
            except OSError:
                time.sleep(1)
        for row in toi:
            q = row["問"]
            query = ask(KENSAKU, q, n=24).splitlines()[0] if q else ""
            now = jiyuu._knowledge(query, q)["結果"]   # 輪の shiru と同じ（頭脳の検索語＋本人の問い）
            now = now if isinstance(now, list) else []
            fixed = naoshita(query, rows)
            text = by_title.get(row["題"], "")
            at = max(0, text.find(row.get("根拠", "")[:20]))
            oracle = [{"題": row["題"], "本文": text[max(0, at - 100):at + 200]}] if text else []
            r = {"id": row["id"], "検索語": query,
                 "B_記事": [c["題"] for c in now], "C_記事": [c["題"] for c in fixed]}
            hint = jiyuu._knowledge_hint(q)   # H: 頭脳が shiru を呼ばない時、門番が最初に添える分だけ（輪と同じ）
            r["H_添えた"] = bool(hint)
            for key, ctx in (("A", None), ("B", now), ("C", fixed), ("D", oracle), ("H", hint)):
                if key not in args.joken:
                    r[key], r[key + "_正"] = "", False
                    continue
                if key == "H":
                    user = q + hint
                else:
                    user = q if ctx is None else ("学んだ記事:\n" + json.dumps(ctx, ensure_ascii=False) + "\n\n質問: " + q)
                answer = ask(KOTAE, user)
                r[key], r[key + "_正"] = answer[:80], atari(answer, row)
            r["B_正しい記事"] = row["題"] in r["B_記事"]
            r["C_正しい記事"] = row["題"] in r["C_記事"]
            results.append(r)
            print(json.dumps(r, ensure_ascii=False)[:240], flush=True)
    finally:
        server.terminate()
        server.wait()
        honban.gakushuu_modosu(was_on)
        with open(args.out, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n = len(results)
    if n:
        print(f"\n{n}問  正答 A なし {sum(r['A_正'] for r in results)}  B 今の検索 {sum(r['B_正'] for r in results)}"
              f"  C 直した検索 {sum(r['C_正'] for r in results)}  D 正しい記事 {sum(r['D_正'] for r in results)}"
              f"  H 門番が添える {sum(r.get('H_正', False) for r in results)}（添えた {sum(r.get('H_添えた', False) for r in results)}）")
        print(f"正しい記事を引けた  B {sum(r['B_正しい記事'] for r in results)}  C {sum(r['C_正しい記事'] for r in results)}")


if __name__ == "__main__":
    main()
