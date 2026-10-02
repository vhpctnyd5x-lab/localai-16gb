#!/usr/bin/env python3
"""専門家を減らした Qwen3.6 を作って測る流れ（2026-10-02 本人「11.7GB をもう少し少なく」）。頭脳を長く使う。

  python3 dougu/kezuru_tejun.py            # 192人・160人
  python3 dougu/kezuru_tejun.py --keep 224

imatrix（校正文 dougu/kekka/kazoe_bun.txt）→ 層ごとに使われる順で K 人だけ残す（MTP も外す）→ 読み込みと一問の確認
→ 知識25問（chishiki_wa）→ 全41問（honban j）→ 速さ（hayasa --wa）。頭脳の常駐メモリを30秒ごとに記録する。
出来た物は作り直さないので、途中で止めても続きから流せる。結果は dougu/kekka/kezuru_1002/matome.md。
事前学習は最初に止めて最後に戻す。Claude の Bash では砂箱の外で呼ぶ。
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import honban   # noqa: E402

HOME = Path.home() / "LocalAI_mirror"
MODEL = HOME / "models/Qwen3.6-35B-A3B-MTP-UD-Q2_K_XL.gguf"
BIN = HOME / "llama-koukai/src/build/bin"
LLAMA = HOME / "llama-koukai/llama-server"
PY = HOME / "goi_venv/bin/python3"
OUT = honban.KEKKA / "kezuru_1002"
TOI = honban.KEKKA / "codex_1001b_toi2.jsonl"
ARGS = "KOUKAI_VOCAB_KEEP=vocab_keep_9999_q36_ids.txt --spec-type none"


def ookisa(model):
    size = model.stat().st_size
    return f"{size / 1e9:.2f}GB（{size / 2**30:.1f}GiB）"


def num(cell):
    try:
        return float(cell)
    except ValueError:
        return 0.0


def log(text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    with (OUT / "tejun.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


class Jouchuu(threading.Thread):
    """llama-server の RSS（ファイルを読み込んだ分も含む）と自前の分（footprint）を、段ごとに集める。"""
    def __init__(self):
        super().__init__(daemon=True)
        self.dan, self.kiroku = "", {}

    def run(self):
        n = 0
        while True:
            time.sleep(30)
            rows = subprocess.run(["ps", "-axo", "pid=,rss=,comm="], capture_output=True, text=True).stdout.splitlines()
            servers = [r.split() for r in rows if r.strip().endswith("llama-server")]
            if not servers or not self.dan:
                continue
            pid, rss = max(servers, key=lambda r: int(r[1]))[:2]
            row = self.kiroku.setdefault(self.dan, {"rss": [], "fp": []})
            row["rss"].append(int(rss) / 1e6)
            n += 1
            if n % 10 == 1:
                out = subprocess.run(["footprint", pid], capture_output=True, text=True).stdout
                for word in out.split("Footprint:")[1:2]:
                    value, unit = word.split()[:2]
                    row["fp"].append(float(value) / (1000 if unit == "MB" else 1))

    def matome(self, dan):
        row = self.kiroku.get(dan, {"rss": [], "fp": []})
        if not row["rss"]:
            return "—"
        fp = f"・自前 {max(row['fp']):.1f}GB" if row["fp"] else ""
        return f"RSS 中央 {statistics.median(row['rss']):.1f}GB・最大 {max(row['rss']):.1f}GB{fp}"


def imatrix():
    out = OUT / "imatrix.gguf"
    if out.exists():
        return out
    log("imatrix を作る（校正文 約4万トークン）")
    with (OUT / "imatrix.log").open("w") as f:
        rc = subprocess.run([str(BIN / "llama-imatrix"), "-m", str(MODEL), "-f", str(honban.KEKKA / "kazoe_bun.txt"),
                             "-c", "2048", "--parse-special", "--no-ppl", "-t", "6",
                             "--output-format", "gguf", "-o", str(out)], stdout=f, stderr=subprocess.STDOUT).returncode
    if rc or not out.exists():
        raise SystemExit(f"imatrix が失敗（{rc}）: {OUT / 'imatrix.log'}")
    log("imatrix 終わり")
    return out


def kezuru(im, keep):
    out = OUT / f"q36_k{keep}.gguf"
    if not out.exists():
        log(f"{keep}人に削る")
        env = dict(os.environ, PYTHONPATH=str(HOME / "llama-koukai/src/gguf-py"))
        rc = subprocess.run([str(PY), "-B", str(honban.KOUKAI / "dougu/senmonka_kezuru.py"), "--model", str(MODEL),
                             "--imatrix", str(im), "--keep", str(keep), "--drop-mtp", "--out", str(out)], env=env).returncode
        if rc:
            raise SystemExit(f"{keep}人に削るのが失敗（{rc}）")
    return out


def yomikomi(model):
    """読み込めるか、日本語で一問答えられるかだけ先に見る（壊れていたら長い試験をしない）。"""
    subprocess.run(["pkill", "-x", "llama-server"])
    time.sleep(3)
    words, env = honban.split_env(ARGS)
    server = subprocess.Popen([str(LLAMA), "-m", str(model), "--port", "8080", "-t", "6", "-ngl", "0", "-c", "4096",
                               "-np", "1", "-fa", "off", *words], env=env,
                              stdout=open(OUT / f"{model.stem}_yomikomi.log", "wb"), stderr=subprocess.STDOUT)
    try:
        for _ in range(150):
            if server.poll() is not None:
                return f"読み込めない（終了 {server.returncode}）"
            try:
                urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2)
                break
            except OSError:
                time.sleep(2)
        prompt = ("<|im_start|>user\n日本の首都はどこですか。一文で答えて。<|im_end|>\n"
                  "<|im_start|>assistant\n<think>\n\n</think>\n\n")
        req = urllib.request.Request("http://127.0.0.1:8080/completion", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"prompt": prompt, "n_predict": 40, "temperature": 0}).encode())
        answer = json.loads(urllib.request.urlopen(req, timeout=300).read())["content"].strip()
        return answer
    finally:
        server.terminate()
        server.wait()


def chishiki(model, name):
    out = OUT / f"chishiki_{name}.jsonl"
    if not out.exists() or sum(1 for _ in out.open()) < 25:
        out.unlink(missing_ok=True)
        log(f"{name}: 知識25問")
        subprocess.run([sys.executable, "dougu/chishiki_wa.py", "--toi", str(TOI), "--model", str(model),
                        "--out", str(out)], cwd=honban.KOUKAI, stdout=open(OUT / f"chishiki_{name}.log", "w"),
                       stderr=subprocess.STDOUT)
    rows = [json.loads(line) for line in out.open(encoding="utf-8")] if out.exists() else []
    return sum(r["正"] for r in rows), sum(r["秒"] for r in rows), len(rows)


def zenmon(model, name):
    md = honban.KEKKA / "kyoudou_0928" / f"wa_q36_41_{name}.md"
    if not md.exists():
        log(f"{name}: 全41問")
        subprocess.run([sys.executable, "dougu/honban.py", "j", "--model", str(model), "--llama", str(LLAMA),
                        "--opts", '{"raw_template": true}', "--args", ARGS, "--out", f"wa_q36_41_{name}"],
                       cwd=honban.KOUKAI, stdout=open(OUT / f"zenmon_{name}.log", "w"), stderr=subprocess.STDOUT)
    rows = [r for r in md.read_text(encoding="utf-8").splitlines() if r.startswith("| J")] if md.exists() else []
    cells = [r.split("|") for r in rows]
    return (sum("PASS" in c[2] for c in cells), sum(num(c[3]) for c in cells), len(rows),
            [c[1].strip() for c in cells if "PASS" not in c[2]])


def hayasa(models):
    out = OUT / "hayasa.txt"
    if not out.exists():
        log("速さ（輪の前置きで200字）")
        lines = []
        for name, model in models.items():
            res = subprocess.run([sys.executable, "dougu/hayasa.py", "--model", str(model), "--conf", f"k_{name}:{ARGS}",
                                  "--llama", str(LLAMA), "--wa"], cwd=honban.KOUKAI, capture_output=True, text=True)
            lines += [f"{name} {line}" for line in res.stdout.splitlines() if "{" in line]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep", type=int, nargs="+", default=[192, 160])
    parser.add_argument("--kihon-j", default="g", help="比べる全41問（元のモデル）の名前 wa_q36_41_<名>")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    mitate = Jouchuu()
    mitate.start()
    was_on = honban.gakushuu_yasumu()
    lines = [f"# 専門家を減らす（{time.strftime('%m/%d %H:%M')}）", "",
             "|版|大きさ|一問|知識25問|全41問|常駐（知識の間）|常駐（41問の間）|", "|---|---:|---|---:|---:|---|---|"]
    hayai = {"256": MODEL}
    try:
        mitate.dan = "k256_chishiki"
        sei, byou, n = chishiki(MODEL, "k256")
        p, s, n41, ochi = zenmon(MODEL, args.kihon_j)
        log(f"元: 知識 {sei}/{n}（{byou}秒）・全41問 {p}/{n41}（{s:.0f}秒）落ちた {ochi}")
        lines.append(f"|元 256人|{ookisa(MODEL)}|—|{sei}/{n}（{byou}秒）|{p}/{n41}（{s:.0f}秒）"
                     f"|{mitate.matome('k256_chishiki')}|—|")
        mitate.dan = "imatrix"
        im = imatrix()
        for keep in args.keep:
            model = kezuru(im, keep)
            name = f"k{keep}"
            mitate.dan = f"{name}_yomi"
            answer = yomikomi(model)
            log(f"{name}: {ookisa(model)}・一問「{answer[:60]}」")
            if "東京" not in answer:
                lines.append(f"|{keep}人|{ookisa(model)}|×「{answer[:30]}」|—|—|—|—|")
                continue
            mitate.dan = f"{name}_chishiki"
            sei, byou, n = chishiki(model, name)
            log(f"{name}: 知識 {sei}/{n}（{byou}秒）")
            if sei < 20:
                lines.append(f"|{keep}人|{ookisa(model)}|○|{sei}/{n}（{byou}秒）|知識で大きく落ちたので測らない"
                             f"|{mitate.matome(mitate.dan)}|—|")
                continue
            mitate.dan = f"{name}_zenmon"
            p, s, n41, ochi = zenmon(model, name)
            log(f"{name}: 全41問 {p}/{n41}（{s:.0f}秒）落ちた {ochi}")
            lines.append(f"|{keep}人|{ookisa(model)}|○|{sei}/{n}（{byou}秒）|{p}/{n41}（{s:.0f}秒）"
                         f"|{mitate.matome(f'{name}_chishiki')}|{mitate.matome(mitate.dan)}|")
            hayai[str(keep)] = model
        mitate.dan = "hayasa"
        text = hayasa(hayai)
        lines += ["", "## 速さ（hayasa --wa）", "```", text.strip(), "```"]
    finally:
        honban.gakushuu_modosu(was_on)
        (OUT / "matome.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
