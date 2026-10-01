#!/usr/bin/env python3
"""本物の輪（jiyuu.kotaeru）で知識の問いを解かせ、頭脳が shiru を自分で呼ぶか・正答かを測る（2026-10-02）。

  python3 dougu/chishiki_wa.py --toi dougu/kekka/codex_1001b_toi2.jsonl

web・chrome・sensei はこの試験の間だけ使えない（ネットで答えを探すと知識の箱を測れない）。
承認の要る手は断る。事前学習を止め、アプリの llama-server を止めてから測り、終わったら戻す。
Claude の Bash では砂箱の外で呼ぶ。知識の箱は読むだけ。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import honban   # noqa: E402
import chishiki_kouka   # noqa: E402  採点（atari）を同じにする


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--toi", required=True)
    parser.add_argument("--model", default="~/LocalAI_mirror/models/Qwen3.6-35B-A3B-MTP-UD-Q2_K_XL.gguf")
    parser.add_argument("--llama", default="~/LocalAI_mirror/llama-koukai/llama-server")
    parser.add_argument("--out", default=str(honban.KEKKA / "chishiki_wa.jsonl"))
    args = parser.parse_args()
    toi = [json.loads(line) for line in open(args.toi, encoding="utf-8") if line.strip().startswith("{")]
    scratch = tempfile.mkdtemp(prefix="chishiki-wa-")   # 記録・技・控えは一時の場所へ（本物を汚さない）
    os.environ.update({k: scratch for k in ("KERNEL_KIROKU_DIR", "KERNEL_HIKAE_DIR", "KERNEL_TSUIKA_DIR", "KERNEL_WAZA_DIR")})
    os.environ["KERNEL_JIYUU_OPTS"] = json.dumps({"raw_template": True})
    import jiyuu
    was_on = honban.gakushuu_yasumu()
    subprocess.run(["pkill", "-x", "llama-server"])
    time.sleep(3)
    env = dict(os.environ, KOUKAI_VOCAB_KEEP=str(honban.KOUKAI / "dougu/jikken/vocab_keep_9999_q36_ids.txt"))
    server = subprocess.Popen([str(Path(args.llama).expanduser()), "-m", str(Path(args.model).expanduser()), "--port", "8080",
                               "-t", "6", "-ngl", "0", "-c", "8192", "-np", "1", "-cb", "-ub", "256", "--cache-reuse", "16",
                               "-fa", "off", "--reasoning-format", "none", "--spec-type", "none"],
                              stdout=open(honban.KEKKA / "chishiki_wa_llama.log", "wb"), stderr=subprocess.STDOUT, env=env)
    results = []
    real_run = jiyuu._run

    def run(name, args_, risk, session, **kw):
        if name in ("web", "chrome", "sensei"):
            return {"ok": False, "結果": "この試験では使えません。学んだ知識（shiru）か、分かることだけで答えてください。"}
        return real_run(name, args_, risk, session, **kw)
    try:
        for _ in range(300):
            try:
                urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2)
                break
            except OSError:
                time.sleep(1)
        with mock.patch.object(jiyuu, "_run", side_effect=run), mock.patch.object(jiyuu, "_kiku", return_value=False):
            for row in toi:
                events = []
                start = time.time()
                try:
                    answer = jiyuu.kotaeru(row["問"], mode="自動", on_event=events.append)
                except Exception as error:   # 1問の失敗で全体を止めない
                    answer = f"実行エラー: {type(error).__name__}: {error}"
                tools = [e.get("label", "") for e in events if e.get("type") == "tool_start"]
                r = {"id": row["id"], "正": chishiki_kouka.atari(answer, row), "shiru": sum("知識" in t or "shiru" in t for t in tools),
                     "道具": tools[:6], "添えた": bool(jiyuu._knowledge_hint(row["問"])), "秒": round(time.time() - start),
                     "答え": str(answer)[:120]}
                results.append(r)
                print(json.dumps(r, ensure_ascii=False)[:220], flush=True)
    finally:
        server.terminate()
        server.wait()
        honban.gakushuu_modosu(was_on)
        with open(args.out, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n = len(results)
    if n:
        print(f"\n{n}問  正答 {sum(r['正'] for r in results)}  shiru を呼んだ {sum(r['shiru'] > 0 for r in results)}"
              f"  門番が添えた {sum(r['添えた'] for r in results)}  合計 {sum(r['秒'] for r in results)} 秒")


if __name__ == "__main__":
    main()
