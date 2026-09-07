"""NVIDIA NIM を使ったマルチエージェント評議会。

役割の違う複数モデルに同じ資料を渡して並列に考えさせ、最後に1体が統合する。
1体に長考させるより、視点の違いを衝突させたほうが穴が見つかりやすいという読み。
"""
import concurrent.futures as cf
import os
import subprocess
import sys
import time

NV = os.path.expanduser("~/.local/bin/nv")


def ask(model, system, brief, timeout=900):
    t0 = time.time()
    try:
        p = subprocess.run([NV, "ask", "-m", model, "-s", system],
                           input=brief, capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip(), time.time() - t0, p.returncode
    except subprocess.TimeoutExpired:
        return "(時間切れ)", time.time() - t0, -1


def run(members, brief, outdir, synth=None, workers=4):
    """members: [(識別名, モデル短縮名, システムプロンプト), ...]"""
    os.makedirs(outdir, exist_ok=True)
    results = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(ask, m, s, brief): name for name, m, s in members}
        for f in cf.as_completed(futs):
            name = futs[f]
            text, dt, rc = f.result()
            results[name] = text
            path = os.path.join(outdir, f"{name}.md")
            open(path, "w").write(text)
            print(f"[完了] {name:16s} {dt:5.0f}秒 {len(text):6d}文字 rc={rc}", flush=True)

    if synth is None:
        return results
    sname, smodel, ssystem = synth
    joined = "\n\n".join(f"===== {n} の回答 =====\n{t}" for n, t in results.items())
    text, dt, rc = ask(smodel, ssystem, brief + "\n\n" + joined, timeout=1800)
    open(os.path.join(outdir, f"{sname}.md"), "w").write(text)
    print(f"[統合] {sname} {dt:.0f}秒 {len(text)}文字")
    results[sname] = text
    return results
