#!/usr/bin/env python3
"""覚えられる量（文脈の長さ -c）を広げたときの 速さ と メモリ を Mac で測る（2026-09-24）。
本番と同じ指定で llama-server を 1本だけ立て、文脈を 7割まで埋めた頼みを投げて、
読み込み（prompt）と書き出し（predicted）の t/s、llama-server の常駐メモリ、スワップの増え方を見る。終わったら必ず止める。
使い方: python3 dougu/hakaru_nagasa.py 8192 16384 32768"""
import json, os, re, subprocess, sys, time, urllib.request

K = os.path.expanduser("~/LocalAI_mirror")
SERVER = f"{K}/llama-latest/build/bin/llama-server"
MODEL = f"{K}/models/Qwen3-30B-A3B-Q2_K.gguf"
OPTS = ["-t", "6", "-ngl", "0", "-dev", "none", "-np", "1", "-cb", "-ub", "256", "--cache-reuse", "16",
        "-fa", "off", "--reasoning-format", "none", "--host", "127.0.0.1", "--port", "8093"]
# 埋め草: 仕事場の日本語の文（本物に近い長さの資料）
KUSA = "".join(open(os.path.join(K, "koukai", p), encoding="utf-8").read() for p in ("AGENTS.md", "kazoeru.py", "monosashi/hakaru.py"))


def swap_mb():
    o = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True).stdout
    return float(re.search(r"used = ([\d.]+)M", o).group(1))


def post(path, body, timeout=3600):
    req = urllib.request.Request("http://127.0.0.1:8093" + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


for c in map(int, sys.argv[1:]):
    s0 = swap_mb()
    p = subprocess.Popen([SERVER, "-m", MODEL, "-c", str(c)] + OPTS, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(200):
            time.sleep(3)
            try:
                urllib.request.urlopen("http://127.0.0.1:8093/health", timeout=3); break
            except Exception:
                if p.poll() is not None: raise SystemExit("立たない -c %d" % c)
        n = len(post("/tokenize", {"content": KUSA})["tokens"])
        mono = (KUSA * (c * 7 // 10 // n + 1))
        toks = post("/tokenize", {"content": mono})["tokens"][: c * 7 // 10]
        t0 = time.time()
        r = post("/completion", {"prompt": toks + post("/tokenize", {"content": "\n\n上の資料を3行でまとめて:"})["tokens"],
                                 "n_predict": 128, "temperature": 0})
        tm = r["timings"]
        rss = int(subprocess.run(["ps", "-o", "rss=", "-p", str(p.pid)], capture_output=True, text=True).stdout) // 1024
        print(json.dumps({"c": c, "読んだ": tm["prompt_n"], "読み込み t/s": round(tm["prompt_per_second"], 1),
                          "書き出し t/s": round(tm["predicted_per_second"], 1), "かかった秒": round(time.time() - t0),
                          "常駐MB": rss, "スワップ増MB": round(swap_mb() - s0)}, ensure_ascii=False), flush=True)
    finally:
        p.terminate(); p.wait(30)
