#!/usr/bin/env python3
"""解き方の手本を GPT-6 Luna（Codex CLI）にまとめて作らせる。Claude の枠は使わない（ChatGPT 側の枠）。
1回 = Luna が 50問を「問題＋手順書どおりの解き方＋答え」で書く → 別の Luna 呼び出しが 問題だけを見て解く
      → 答えが一致したものだけ kernel/tehon.jsonl に足す（7段に近いものは捨てる）。
使い方: python3 dougu/tsukuru_tehon_luna.py [回数=3]
"""
import json, os, random, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tsukuru_tehon as T

KAI = int(sys.argv[1]) if len(sys.argv) > 1 else 3
N = 50


def luna(tanomi):
    d = tempfile.mkdtemp()
    out = os.path.join(d, "out.txt")
    subprocess.run(["codex", "exec", "--skip-git-repo-check", "-m", "gpt-6-luna", "-c", "model_reasoning_effort=max",
                    "-s", "read-only", "-C", d, "-o", out, tanomi], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)
    return open(out, encoding="utf-8").read() if os.path.exists(out) else ""


def rei(k=2):
    L = [json.loads(l) for l in open(T.OUT, encoding="utf-8")]
    return "\n".join(json.dumps({"種類": d["種類"], "問": d["問"], "解き方": d["解き方"], "答": d["答"]}, ensure_ascii=False)
                     for d in random.sample(L, k))


def main():
    for kai in range(KAI):
        shurui = random.sample(T.SHURUI, 10)
        tanomi = (f"日本語の算数の文章題を {N} 問作ってください。ファイルやコマンドは使わず、頭だけで。\n"
                  f"種類はこの10種から各5問: {'、'.join(shurui)}。\n"
                  f"各問に次の仕掛けのどれかを入れる: {' / '.join(T.WANA)}。答えは整数1つ。\n"
                  "解き方は次の手順書どおり、400字以内、最後の行は `答え: <値>`。\n手順書:\n" + T.TEJUN +
                  "\n\n良い例（形と長さをまねる。内容はまねない）:\n" + rei() +
                  "\n\n出力は JSON Lines だけ（1行1問、説明なし）: {\"種類\": ..., \"問\": ..., \"解き方\": ..., \"答\": \"数値\"}")
        rows = []
        for ln in luna(tanomi).splitlines():
            try:
                d = json.loads(ln.strip().strip(","))
                a = T.kazu("答え: " + str(d["答"]))
                if a is not None and T.kazu(d["解き方"]) == a and not T.chikai(d["問"]):
                    rows.append((d, a))
            except (ValueError, KeyError, TypeError):
                pass
        print(f"{kai + 1}回目: 作った {len(rows)} 問", flush=True)
        if not rows:
            continue
        kentei = luna("次の各問を頭だけで解き、1行1問で `番号<TAB>答え（数値だけ）` とだけ出力。\n\n" +
                      "\n".join(f"{i}\t{d['問']}" for i, (d, _) in enumerate(rows)))
        kotae = {}
        for ln in kentei.splitlines():
            m = re.match(r"\s*(\d+)\s*\t\s*(-?[\d,.]+)", ln)
            if m:
                kotae[int(m.group(1))] = T.kazu("答え: " + m.group(2))
        ok = 0
        with open(T.OUT, "a", encoding="utf-8") as w:
            for i, (d, a) in enumerate(rows):
                if kotae.get(i) == a:
                    w.write(json.dumps({"種類": d.get("種類", ""), "仕掛け": "", "問": d["問"].strip(), "解き方": d["解き方"].strip(),
                                        "答": str(a), "作": "codex:gpt-6-luna", "検": "codex:gpt-6-luna(別呼び出し)"},
                                       ensure_ascii=False) + "\n")
                    ok += 1
        print(f"{kai + 1}回目: 検品を通った {ok}/{len(rows)}", flush=True)


if __name__ == "__main__":
    main()
