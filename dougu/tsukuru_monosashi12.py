#!/usr/bin/env python3
"""自作テストF（2026-09-24）。速さの道具（テストE の外れを読んで作った）を測る未見の 速さ問題 48問。
Luna（Codex CLI）が 8種×16問を作る → 別の Luna 呼び出しが問題だけ見て解く → 答えが一致したものだけ残す。
7段・教材（kernel/tehon.jsonl）と 2字の重なりが 0.45 以上のものは捨てる（教材から答えが漏れないように）。
→ monosashi/mondai_12dan.jsonl（答えは整数。教材には絶対に混ぜない）
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tsukuru_tehon as T
from tsukuru_tehon_luna import luna

OUT = os.path.join(HERE, "..", "monosashi", "mondai_12dan.jsonl")
SHURUI = {
    "速さ_向かい合う": "2人（乗り物でもよい）が両端から向かい合って進み、片方が途中で速さを変える・休む・遅れて出発する。出会うまでの時間か、出会うまでに片方が進んだ道のり",
    "速さ_追いかける": "後ろから追いかけ、どちらかが途中で速さを変える・遅れて出発する。追いつくまでの時間か道のり",
    "速さ_いろいろ": "出会い・追いつきで、単位が混じる（km と m、時速と分速）か、3段以上で速さが変わる。答えは時間（分）か道のり",
}
TSUKURU = ("日本語の算数の文章題を作ってください。ファイルやコマンドは使わず頭だけで。種類「{k}」＝{v}。"
           "16問。小学校高学年〜中学レベル、答えは整数1つ、問題文は100〜220字、場面と数値は毎回変える。"
           "出力は JSON Lines だけ（1行1問、説明なし）: {{\"問\": 問題文, \"答\": \"整数\"}}")


def main():
    mono = [T.bigram(json.loads(l)["問"]) for l in open(T.OUT, encoding="utf-8")] + T.MONO + \
           [T.bigram(json.loads(l)["問"]) for l in open(os.path.join(HERE, "..", "monosashi", "mondai_8dan.jsonl"), encoding="utf-8")] + \
           [T.bigram(json.loads(l)["問"]) for l in open(os.path.join(HERE, "..", "monosashi", "mondai_9dan.jsonl"), encoding="utf-8")] + \
           [T.bigram(json.loads(l)["問"]) for l in open(os.path.join(HERE, "..", "monosashi", "mondai_10dan.jsonl"), encoding="utf-8")] + \
           [T.bigram(json.loads(l)["問"]) for l in open(os.path.join(HERE, "..", "monosashi", "mondai_11dan.jsonl"), encoding="utf-8")]
    from concurrent.futures import ThreadPoolExecutor

    def hitotsu(kv):
        k, v = kv
        got = []
        for ln in luna(TSUKURU.format(k=k, v=v)).splitlines():
            try:
                d = json.loads(ln.strip().strip(","))
                a = T.kazu("答え: " + str(d["答"]))
                b = T.bigram(d["問"])
                if a is not None and not any(len(b & m) / max(1, len(b | m)) >= 0.45 for m in mono):
                    got.append((d["問"].strip(), a))
            except (ValueError, KeyError, TypeError):
                pass
        kentei = luna("次の各問を頭だけで慎重に解き、1行1問で `番号<TAB>答え（整数だけ）` とだけ出力。\n\n" +
                      "\n".join(f"{i}\t{q}" for i, (q, _) in enumerate(got)))
        kotae = {}
        for ln in kentei.splitlines():
            m = re.match(r"\s*(\d+)\s*\t\s*(-?[\d,]+)", ln)
            if m:
                kotae[int(m.group(1))] = T.kazu("答え: " + m.group(2))
        ok = [(q, a) for i, (q, a) in enumerate(got) if kotae.get(i) == a]
        print(k, "作った", len(got), "通った", len(ok), flush=True)
        return [{"id": f"e12-{k[3:]}{j + 1:02d}", "段": 12, "型": k, "問": q, "答": str(a), "答の形": "数"}
                for j, (q, a) in enumerate(ok)]

    with ThreadPoolExecutor(4) as ex:
        rows = [r for g in ex.map(hitotsu, SHURUI.items()) for r in g]
    with open(OUT, "w", encoding="utf-8") as w:
        for r in rows:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("→", OUT, len(rows))


if __name__ == "__main__":
    main()
