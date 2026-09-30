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


# 9/30: 輪と同じ前置き（決まり文＋道具）で、前の結果の名前を写しながら道具を呼ばせる。先読み（n-gram）が当たる場面の書く速さを見る。
WA_TASKS = [
    ("~/Documents/作業票 のtxtを全部読んで、状態が完了のものだけ ~/Desktop/仕分け/完了 へ移して。",
     "read", {"path": "~/Documents/作業票"},
     {"ok": True, "結果": "フォルダ内の名前（全8件）: " + "、".join(
         f"2026-09-{d:02d}_作業票_{k}.txt" for d, k in ((1, "梱包"), (3, "検品"), (5, "発送"), (8, "棚卸"),
                                                        (12, "返品"), (15, "修理"), (19, "点検"), (22, "清掃")))}),
    ("~/Downloads/保管候補 の8月のファイルを ~/Documents/保管/2026-08 へ全部移して。",
     "find", {"dir": "~/Downloads/保管候補", "glob": "*"},
     {"ok": True, "件数": 6, "場所": [f"/Users/me/Downloads/保管候補/2026-08-{d:02d}_記録.txt" for d in (3, 9, 14, 20, 26, 31)]}),
    ("この3つの週報の件数を ~/Desktop/一覧.csv に ファイル名,件数 の列で書いて。",
     "sh", {"command": "grep -H 件数 ~/Documents/週報原本/*.txt"},
     {"ok": True, "結果": "\n".join(f"/Users/me/Documents/週報原本/{d}曜.txt:件数: {n}" for d, n in (("月", 4), ("火", 7), ("水", 2)))}),
]


def wa_convs():
    """門番の決まり文と道具は、別の Python で一時 HOME にして読む（本物の記録や技に触れない）。"""
    code = ("import json, os, sys, tempfile; d = tempfile.mkdtemp(prefix='hayasa-'); "
            "os.environ.update({k: d for k in ('HOME', 'KERNEL_KIROKU_DIR', 'KERNEL_HIKAE_DIR', 'KERNEL_TSUIKA_DIR', 'KERNEL_WAZA_DIR')}); "
            "sys.path.insert(0, sys.argv[1]); import jiyuu; print(json.dumps({'system': jiyuu._system(), 'tools': jiyuu.TOOLS}, ensure_ascii=False))")
    out = subprocess.run([sys.executable, "-c", code, str(Path(__file__).resolve().parent)],
                         capture_output=True, text=True, check=True).stdout
    fixed = json.loads(out.strip().splitlines()[-1])
    convs = []
    for request, name, args, result in WA_TASKS:
        call = {"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
        convs.append({"tools": fixed["tools"], "messages": [
            {"role": "system", "content": fixed["system"]}, {"role": "user", "content": request},
            {"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "c1", "content": json.dumps(result, ensure_ascii=False)}]})
    return convs


def post(path, body, timeout=600):
    request = urllib.request.Request("http://127.0.0.1:8080" + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(request, timeout=timeout))


def measure_wa(convs, n_predict):
    rows = []
    for i, conv in enumerate([convs[0]] + convs):   # 1回目は温め（前置きを読む。数えない）
        prompt = post("/apply-template", {**conv, "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
        timings = post("/completion", {"prompt": prompt, "n_predict": n_predict, "temperature": 0, "cache_prompt": True})["timings"]
        if i:
            rows.append(timings)
    drafted = sum(t.get("draft_n", 0) for t in rows)
    accepted = sum(t.get("draft_n_accepted", 0) for t in rows)
    written = sum(t["predicted_n"] for t in rows)
    return {"道具を書く": round(written / sum(t["predicted_ms"] / 1000 for t in rows), 2), "書いた": written,
            "先読み": f"{accepted}/{drafted}" if drafted else "-"}


def measure(model, extra, log_path, n_predict, llama, convs=None):
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
        if convs:
            return measure_wa(convs, n_predict)
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
    parser.add_argument("--wa", action="store_true", help="輪と同じ前置きで道具を呼ばせ、書く速さと先読みだけを見る")
    args = parser.parse_args()
    convs = wa_convs() if args.wa else None
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
            result = measure(model, extra, honban.KEKKA / f"hayasa_{name}.log", args.n, Path(args.llama).expanduser(), convs)
            print(f"{model.name[:34]:34} {name:8} {json.dumps(result, ensure_ascii=False)}", flush=True)
    finally:
        if was_on:
            honban.call(honban.base(), "/gakushuu", {"入": True})


if __name__ == "__main__":
    main()
