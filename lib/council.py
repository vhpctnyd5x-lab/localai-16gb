"""NVIDIA NIM を使ったマルチエージェント評議会。

役割の違う複数モデルに同じ資料を渡して並列に考えさせ、最後に1体が統合する。
1体に長考させるより、視点の違いを衝突させたほうが穴が見つかりやすいという読み。
"""
import concurrent.futures as cf
import os
import subprocess
import sys
import time

# ★ 2026-09-07: 決め打ちだと そのパスが無い環境で即死する。PATH も見る。
import shutil as _shutil
NV = (os.environ.get("NV_CLI")
      or _shutil.which("nv")
      or os.path.expanduser("~/.local/bin/nv"))


def ask(model, system, brief, timeout=900):
    t0 = time.time()
    try:
        p = subprocess.run([NV, "ask", "-m", model, "-s", system],
                           input=brief, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            # ★ 前は 異常終了でも 中身をそのまま返していた。空や壊れた文が
            #   次の工程（統合）にそのまま流れる。呼ぶ側が気づけるようにする。
            sys.stderr.write("nv が異常終了しました（%d）: %s\n"
                             % (p.returncode, (p.stderr or "")[:200]))
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
            with open(path, "w", encoding="utf-8") as _f:   # ★ with で確実に閉じる
                _f.write(text)
            print(f"[完了] {name:16s} {dt:5.0f}秒 {len(text):6d}文字 rc={rc}", flush=True)

    if synth is None:
        return results
    sname, smodel, ssystem = synth
    joined = "\n\n".join(f"===== {n} の回答 =====\n{t}" for n, t in results.items())
    text, dt, rc = ask(smodel, ssystem, brief + "\n\n" + joined, timeout=1800)
    with open(os.path.join(outdir, f"{sname}.md"), "w", encoding="utf-8") as _f:
        _f.write(text)
    print(f"[統合] {sname} {dt:.0f}秒 {len(text)}文字")
    results[sname] = text
    return results
