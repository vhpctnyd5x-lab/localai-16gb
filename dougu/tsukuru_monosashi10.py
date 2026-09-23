#!/usr/bin/env python3
"""新しい物差し「8段」（2026-09-23）。7段は今日何度も見たので、合わせ込みの心配がない別の 128問を作る。
Luna（Codex CLI）が 8種×16問を作る → 別の Luna 呼び出しが問題だけ見て解く → 答えが一致したものだけ残す。
7段・教材（kernel/tehon.jsonl）と 2字の重なりが 0.45 以上のものは捨てる（教材から答えが漏れないように）。
→ monosashi/mondai_10dan.jsonl（答えは整数。教材には絶対に混ぜない）
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tsukuru_tehon as T
from tsukuru_tehon_luna import luna

OUT = os.path.join(HERE, "..", "monosashi", "mondai_10dan.jsonl")
SHURUI = {
    "多段_割合": "割引・税・手数料が2〜3段かかる買い物",
    "関係ない数_出入り": "人数・お金・在庫の出入りに、問いと無関係な数（別の日・別の人・容量）が2つ混じる",
    "取り消し_後戻り": "途中で予定や注文が取り消され、1つ前の状態に戻ってから続く",
    "並べ方_条件": "条件つきの並べ方・選び方の数（隣り合わない・必ず含む等）",
    "速さ_出会い": "2人が向かい合う・追いかける・途中で速さが変わる",
    "時刻_日数": "日付・曜日・時刻をまたぐ計算（月末・うるう年は使わない）",
    "推理_順位": "条件から順位や位置を決め、その番号を答える",
    "単位_換算": "単位が2種類以上混じる量の合計や差",
}
TSUKURU = ("日本語の算数の文章題を作ってください。ファイルやコマンドは使わず頭だけで。種類「{k}」＝{v}。"
           "16問。小学校高学年〜中学レベル、答えは整数1つ、問題文は100〜220字、場面と数値は毎回変える。"
           "出力は JSON Lines だけ（1行1問、説明なし）: {{\"問\": 問題文, \"答\": \"整数\"}}")


def main():
    mono = [T.bigram(json.loads(l)["問"]) for l in open(T.OUT, encoding="utf-8")] + T.MONO + \
           [T.bigram(json.loads(l)["問"]) for l in open(os.path.join(HERE, "..", "monosashi", "mondai_8dan.jsonl"), encoding="utf-8")] + \
           [T.bigram(json.loads(l)["問"]) for l in open(os.path.join(HERE, "..", "monosashi", "mondai_9dan.jsonl"), encoding="utf-8")]
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
        return [{"id": f"e10-{k[:2]}{j + 1:02d}", "段": 10, "型": k, "問": q, "答": str(a), "答の形": "数"}
                for j, (q, a) in enumerate(ok)]

    with ThreadPoolExecutor(4) as ex:
        rows = [r for g in ex.map(hitotsu, SHURUI.items()) for r in g]
    with open(OUT, "w", encoding="utf-8") as w:
        for r in rows:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("→", OUT, len(rows))


if __name__ == "__main__":
    main()
