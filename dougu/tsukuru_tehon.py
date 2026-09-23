#!/usr/bin/env python3
"""解き方の手本（教材）を 外の無料の先生に作らせ続ける。Mac の CPU・メモリはほぼ使わない。
1件 = 先生A（NVIDIA か Groq を交互）が「問題＋手順書どおりの解き方＋答え」を書く
      → 先生B（もう一方）が 問題だけを見て別に解く → 答えが一致したものだけ残す。
7段 128問（物差し）と 2字の重なりが 0.45 以上のものは捨てる（物差しを汚さない）。
→ kernel/tehon.jsonl に 1件ずつ追記（途中で止めても続きから）。止めるときは kernel/tehon.stop を置く。
使い方: python3 dougu/tsukuru_tehon.py [目標件数=2000]
"""
import json, os, random, re, subprocess, sys, time
KERNEL = os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import nvidia

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(KERNEL, "tehon.jsonl")
STOP = os.path.join(KERNEL, "tehon.stop")
GROQ = os.path.expanduser("~/.claude/scripts/groq.sh")
MOKUHYOU = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
TEJUN = open(os.path.join(HERE, "..", "monosashi", "tejun_luna.txt"), encoding="utf-8").read().strip()

SHURUI = ["割合と値引き・税", "速さ・時間・道のり", "仕事算", "年齢算", "集合（両方・どちらか）",
          "植木算・間の数", "並べ方の数", "選び方（組合せ）の数", "硬貨やおもりで金額を作る方法の数",
          "お金や在庫の出入り（入った・出た・戻った）", "時刻と時間の計算", "平均", "比と分配",
          "規則的に並ぶ数・図形の個数", "条件から順位や席を決める推理", "つるかめ算", "過不足算",
          "差を使う問題（和差算）", "日数・曜日の計算", "濃度", "単位の換算", "損益（原価・定価・利益）"]
WANA = ["問いと関係ない数（別の用途・別件・同じ日の別の記録・最大容量など）を1つか2つ混ぜる",
        "途中で条件が1つ変わる（あとで取り消し・返品・追加など）", "数える対象が紛らわしい（重複や0の場合を含む）"]

SYS_A = ("あなたは算数の教科書の著者です。小学校高学年〜中学レベルの日本語の文章題を1つ作り、"
         "次の手順書どおりの短い解き方を書きます。\n手順書:\n" + TEJUN +
         "\n\n出力は JSON 1つだけ: {\"問\": 問題文, \"解き方\": 手順書どおりの解き方（400字以内、最後の行は `答え: <値>`）, \"答\": 数値だけ}")
SYS_B = "算数の文章題を解きます。短く考え、最後の行に `答え: <数値>` とだけ書いてください。"


def groq(p, s):
    r = subprocess.run([GROQ, "-m", "openai/gpt-oss-120b", "-s", s, p], capture_output=True,
                       text=True, timeout=180, stdin=subprocess.DEVNULL)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError("groq: " + (r.stderr or "")[:80])
    return r.stdout


def nv(p, s):
    # super は混むと 503 を返す（2026-09-23）。そのときは NVIDIA の別の先生へ。
    e = None
    for m in ("super", "z-ai/glm-5.3", "moonshotai/kimi-k3"):
        try:
            return nvidia.ask(p, model=m, system=s, timeout=180, max_tokens=1500)
        except Exception as x:
            e = x
    raise e


def bigram(s):
    s = re.sub(r"\s", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


MONO = [bigram(json.loads(l)["問"]) for l in open(os.path.join(HERE, "..", "monosashi", "mondai_7dan.jsonl"), encoding="utf-8")]


def chikai(q):
    b = bigram(q)
    return any(len(b & m) / max(1, len(b | m)) >= 0.45 for m in MONO)


def kazu(t):
    m = re.findall(r"答え?\s*[:：]\s*(-?[\d,，.]+)", t or "")
    if not m:
        return None
    try:
        v = float(m[-1].replace(",", "").replace("，", ""))
        return int(v) if v == int(v) else round(v, 4)
    except ValueError:
        return None


def hitotsu(n):
    shurui, wana = random.choice(SHURUI), random.choice(WANA)
    tsukuru, toku = (nv, groq) if n % 2 == 0 else (groq, nv)
    p = f"種類: {shurui}\n仕掛け: {wana}\n答えは整数1つになるように。新しい場面・数値で。"
    t = tsukuru(p, SYS_A)
    m = re.search(r"\{.*\}", t, re.S)
    d = json.loads(m.group(0))
    q, kaiketsu = d["問"].strip(), d["解き方"].strip()
    a = kazu("答え: " + str(d["答"]))
    if a is None or kazu(kaiketsu) != a:
        return None, "自分の答えが合わない"
    if chikai(q):
        return None, "物差しに近い"
    b = kazu(toku(q, SYS_B))
    if b != a:
        return None, f"検品で不一致 {a}≠{b}"
    return {"種類": shurui, "仕掛け": wana, "問": q, "解き方": kaiketsu, "答": str(a),
            "作": tsukuru.__name__, "検": toku.__name__}, "ok"


def main():
    aru = sum(1 for _ in open(OUT, encoding="utf-8")) if os.path.exists(OUT) else 0
    n, dame, renzoku = aru, {}, 0
    print(f"すでに {aru} 件。目標 {MOKUHYOU}", flush=True)
    while n < MOKUHYOU and not os.path.exists(STOP):
        try:
            r, why = hitotsu(n + sum(dame.values()))
            renzoku = 0
        except Exception as e:
            r, why = None, "しくじり " + str(e)[:40]
            renzoku += 1
            time.sleep(min(600, 20 * renzoku))   # 429 などは待って続ける
            if renzoku >= 30:
                print("30回続けて失敗したので止めます", flush=True); break
        if r:
            with open(OUT, "a", encoding="utf-8") as w:
                w.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
            if n % 10 == 0:
                print(time.strftime("%H:%M"), n, "件", {k: v for k, v in dame.items()}, flush=True)
        else:
            k = why.split(" ")[0]
            dame[k] = dame.get(k, 0) + 1
    print("おわり", n, dame, flush=True)


if __name__ == "__main__":
    main()
