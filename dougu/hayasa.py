#!/usr/bin/env python3
"""手元の Mac で、同じ文を書かせた時の速さを設定ごとに比べる（2026-09-30）。

  python3 dougu/hayasa.py --model ~/LocalAI_mirror/models/X.gguf --conf "なし:--spec-type none" "mtp2:--spec-type draft-mtp --spec-draft-n-max 2"

事前学習を止め、アプリの llama-server を止めてから測り、終わったら事前学習を戻す（honban.py j と同じ流れ）。
Claude の Bash では砂箱の外で呼ぶ。
"""
import argparse
import json
import shlex
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import honban   # noqa: E402

PROMPTS = ["日本の四季の特徴を、それぞれ2文ずつで説明してください。",
           "Python でテキストファイルを1行ずつ読み、空行を数える方法を、短いコードつきで説明してください。",
           "会議の議事録を短くまとめるコツを5つ、箇条書きで教えてください。"]


# 9/30: 短い頼み（50 トークンほど）では読む速さが測れない（輪は毎回 1,000 トークン以上読む）。長い文も読ませる。
NAGAI = ("事前学習は、Wikipedia の記事を読んで知識を貯め、会話の記録を振り返って次に使える手順を技として提案する仕組みです。"
         "記事は題から題へたどり、読んだ内容は短くまとめて手元の知識の箱に入れます。振り返りでは、道具の使い方で失敗した所を探し、"
         "同じ頼みが来た時にどうすればよいかを短い手順にします。") * 12


def post(path, body, timeout=600):
    request = urllib.request.Request("http://127.0.0.1:8080" + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(request, timeout=timeout))


def measure(model, extra, log_path, n_predict, llama):
    words, env = honban.split_env(extra)   # 頭の KOUKAI_…=値 は環境へ
    llama = Path(env.pop("LLAMA_BIN")).expanduser() if "LLAMA_BIN" in env else llama   # 設定ごとに llama-server を変える
    base = [str(llama), "-m", str(model), "--port", "8080", "-t", "6", "-ngl", "0", "-c", "8192",
            "-np", "1", "-cb", "-ub", "256", "-fa", "off", "--reasoning-format", "none"]
    server = subprocess.Popen(base + words, stdout=open(log_path, "wb"), stderr=subprocess.STDOUT, env=env)
    try:
        for _ in range(300):
            try:
                urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2)
                break
            except OSError:
                if server.poll() is not None:
                    return {"失敗": "サーバーが落ちた（ログを見る）"}
                time.sleep(1)
        rows = []
        for i, text in enumerate([PROMPTS[0]] + PROMPTS):   # 1回目は温め（数えない）
            prompt = post("/apply-template", {"messages": [{"role": "user", "content": text}],
                                              "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
            timings = post("/completion", {"prompt": prompt, "n_predict": n_predict, "temperature": 0,
                                           "cache_prompt": False})["timings"]
            if i:
                rows.append(timings)
        long_rows = []
        for _ in range(2):   # 長い文を2回読ませ、2回目（温まった後）を使う
            prompt = post("/apply-template", {"messages": [{"role": "user", "content": "次の文を一文で要約してください。\n" + NAGAI}],
                                              "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
            long_rows.append(post("/completion", {"prompt": prompt, "n_predict": 16, "temperature": 0,
                                                  "cache_prompt": False})["timings"])
        speed = [t["predicted_per_second"] for t in rows]
        drafted = sum(t.get("draft_n", 0) for t in rows)
        accepted = sum(t.get("draft_n_accepted", 0) for t in rows)
        return {"書く": round(statistics.median(speed), 2), "読む": round(statistics.median(t["prompt_per_second"] for t in rows), 2),
                "長く読む": round(long_rows[-1]["prompt_per_second"], 2), "長さ": long_rows[-1]["prompt_n"],
                "先読み": f"{accepted}/{drafted}" if drafted else "-"}
    finally:
        server.terminate()
        server.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--conf", nargs="+", required=True, help="名前:llama-server に足す引数")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--llama", default=str(honban.LLAMA), help="llama-server（圧縮入りは ~/LocalAI_mirror/llama-koukai/llama-server）")
    args = parser.parse_args()
    line = honban.base()
    was_on = honban.call(line, "/gakushuu").get("入")
    if was_on:
        honban.call(line, "/gakushuu", {"入": False})
    subprocess.run(["pkill", "-x", "llama-server"])
    time.sleep(3)
    model = Path(args.model).expanduser()
    try:
        for conf in args.conf:
            name, _, extra = conf.partition(":")
            result = measure(model, extra, honban.KEKKA / f"hayasa_{name}.log", args.n, Path(args.llama).expanduser())
            print(f"{model.name[:34]:34} {name:8} {json.dumps(result, ensure_ascii=False)}", flush=True)
    finally:
        if was_on:
            honban.call(honban.base(), "/gakushuu", {"入": True})


if __name__ == "__main__":
    main()
