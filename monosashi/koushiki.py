#!/usr/bin/env python3
"""公式ベンチマーク（2026-09-24 本人:「代表的なベンチマークを測らないと発表できない」）。
立てた llama-server（OpenAI 互換 /v1/chat/completions）に 公式の問題を投げ、公式の採点で数える。
自作の採点はしない: MMLU-Pro は TIGER-Lab の抜き出し方、数学は HF の math-verify、IFEval は lm-eval の採点。
設定は Qwen3 の公表の評価設定に合わせる（考える: 温度 0.6/top_p 0.95/top_k 20、考えない: 0.7/0.8/20）。
使い方: python3 koushiki.py --kijun mmlu_pro --bubun 3/20 --out 結果.jsonl [--kagiri N]
"""
import argparse, json, os, re, sys, time, urllib.request

KIJUN = {  # 名前: (HF のデータ, 分け, 考えるか, 書き出しの上限)
    "mmlu_pro": ("TIGER-Lab/MMLU-Pro", "test", False, 4096),
    "ifeval": ("google/IFEval", "train", False, 2048),
    "math500": ("HuggingFaceH4/MATH-500", "test", True, 30000),
    "aime25": ("math-ai/aime25", "test", True, 38000),
    "gpqa": ("Idavidrein/gpqa", "train", True, 30000),   # gpqa_diamond（利用規約の同意と HF_TOKEN が要る）
}
MOJI = "ABCDEFGHIJ"


def kiku(msg, kangaeru, cap, url="http://127.0.0.1:8080/v1/chat/completions"):
    body = {"messages": [{"role": "user", "content": msg}], "max_tokens": cap,
            "chat_template_kwargs": {"enable_thinking": kangaeru}}
    body.update({"temperature": 0.6, "top_p": 0.95, "top_k": 20} if kangaeru else {"temperature": 0.7, "top_p": 0.8, "top_k": 20})
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=4 * 3600) as r:
        d = json.load(r)
    c = d["choices"][0]["message"]
    text = (c.get("content") or "")
    kotae = re.sub(r"(?s)^.*</think>", "", text).strip()          # 考えた部分は採点に使わない
    return kotae, text, d.get("usage", {}).get("completion_tokens", 0)


def mondai(kijun):
    from datasets import load_dataset
    na, bu, _, _ = KIJUN[kijun]
    if kijun == "gpqa":
        return list(load_dataset(na, "gpqa_diamond", split=bu))
    return list(load_dataset(na, split=bu))


# ── 各ベンチマークの 問い方 と 採点（公式どおり）──────────────────
def mmlu_pro(d):
    q = ("The following is a multiple choice question about %s. Think step by step and then finish your answer "
         "with \"the answer is (X)\" where X is the correct letter choice.\n\nQuestion: %s\nOptions:\n%s\nAnswer: Let's think step by step."
         % (d["category"], d["question"], "\n".join("%s. %s" % (MOJI[i], o) for i, o in enumerate(d["options"]))))
    def saiten(out):   # TIGER-Lab/MMLU-Pro evaluate_from_api.py の extract_answer と同じ順
        for pat in (r"answer is \(?([A-J])\)?", r".*[aA]nswer:\s*([A-J])"):
            m = re.search(pat, out)
            if m: return m.group(1) == d["answer"]
        m = re.search(r"\b[A-J]\b(?!.*\b[A-J]\b)", out, re.DOTALL)
        return bool(m) and m.group(0) == d["answer"]
    return q, saiten


def suugaku(d, mondai_key, kotae_key):
    from math_verify import parse, verify
    q = d[mondai_key] + "\n\nPlease reason step by step, and put your final answer within \\boxed{}."
    def saiten(out):
        return bool(verify(parse("$" + str(d[kotae_key]) + "$"), parse(out)))
    return q, saiten


def gpqa(d, i):
    import random
    ch = [d["Correct Answer"], d["Incorrect Answer 1"], d["Incorrect Answer 2"], d["Incorrect Answer 3"]]
    random.Random(i).shuffle(ch)   # 選択肢の順は 番号で固定（毎回同じ）
    sei = MOJI[ch.index(d["Correct Answer"])]
    q = ("Answer the following multiple choice question. The last line of your response should be of the following format: "
         "'Answer: $LETTER' (without quotes) where LETTER is one of ABCD. Think step by step before answering.\n\n%s\n\n%s"
         % (d["Question"].strip(), "\n".join("%s) %s" % (MOJI[j], c.strip()) for j, c in enumerate(ch))))
    def saiten(out):   # simple-evals の gpqa_eval と同じ抜き出し
        m = re.search(r"(?i)Answer\s*:\s*\$?([A-D])", out)
        return bool(m) and m.group(1).upper() == sei
    return q, saiten


def ifeval(d):
    def saiten(out):
        from lm_eval.tasks.ifeval.utils import process_results
        r = process_results(d, [out])
        return {"strict": r["prompt_level_strict_acc"], "loose": r["prompt_level_loose_acc"],
                "inst_strict": r["inst_level_strict_acc"], "inst_loose": r["inst_level_loose_acc"]}
    return d["prompt"], saiten


def toikata(kijun, d, i):
    if kijun == "mmlu_pro": return mmlu_pro(d)
    if kijun == "math500": return suugaku(d, "problem", "answer")
    if kijun == "aime25": return suugaku(d, "problem", "answer")
    if kijun == "gpqa": return gpqa(d, i)
    if kijun == "ifeval": return ifeval(d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kijun", required=True, choices=KIJUN)
    ap.add_argument("--bubun", default="0/1")
    ap.add_argument("--kagiri", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    i0, n = map(int, a.bubun.split("/"))
    zen = mondai(a.kijun)
    ban = [i for i in range(len(zen)) if i % n == i0]
    if a.kagiri: ban = ban[:a.kagiri]
    _, _, kangaeru, cap = KIJUN[a.kijun]
    sumi = set()
    if os.path.exists(a.out):   # 途中から続ける
        sumi = {json.loads(l)["i"] for l in open(a.out, encoding="utf-8")}
    with open(a.out, "a", encoding="utf-8") as w:
        for i in ban:
            if i in sumi: continue
            q, saiten = toikata(a.kijun, zen[i], i)
            t0 = time.time()
            try:
                kotae, zenbun, toks = kiku(q, kangaeru, cap)
                s = saiten(kotae)
            except Exception as e:
                kotae, zenbun, toks, s = "", "", 0, False
                print("しくじり", i, str(e)[:100], flush=True)
            w.write(json.dumps({"i": i, "○": s, "秒": round(time.time() - t0, 1), "字": toks,
                                "答え": kotae[-300:]}, ensure_ascii=False) + "\n"); w.flush()
            print(i, s, round(time.time() - t0), "秒", toks, "字", flush=True)


if __name__ == "__main__":
    main()
