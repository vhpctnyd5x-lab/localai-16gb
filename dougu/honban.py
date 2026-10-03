#!/usr/bin/env python3
"""本番のカーネル（アプリ）を1行で扱う（2026-09-30）。

9/29〜30 は、本番へ写す・開き直す・API で聞く・11問を回す を毎回その場で書き、
合言葉の付け忘れ（/ping も要る）・server.url が開き直しの間だけ消える・古い窓が残る
（open -a が前に出すだけ）で何度も転んだ。ここにまとめる。

  python3 dougu/honban.py jotai                          … サーバー・事前学習・載っているモデル
  python3 dougu/honban.py ireru dougu/jiyuu.py kernel/server.py …   … 控えを取って本番へ写し compile
  python3 dougu/honban.py kaiten                         … 窓とサーバーを止めて開き直し、立つまで待つ
  python3 dougu/honban.py kiku kyoudou "頼み"            … 試験の会話で聞き、道具と答えを短く（kyoudou:mimo9 も可）
  python3 dougu/honban.py gakushuu on|off                … 事前学習の入・切
  python3 dougu/honban.py j [--id J10,J11] [--model パス] [--opts JSON] [--out 名前]
                                                         … 事前学習を止め、アプリの 30B を止めて 11問、元に戻す

Claude の Bash では砂箱の外で呼ぶ（open・lsof・localhost のため）。
"""
import argparse
import datetime
import getpass
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path.home()
SUP = HOME / "Library" / "Application Support" / "kernel-ai"
KOUKAI = Path(__file__).resolve().parent.parent
KERNEL = HOME / "LocalAI_mirror" / "kernel"
LLAMA = HOME / "LocalAI_mirror" / "llama-latest" / "build" / "bin" / "llama-server"
MODEL_MAIN = HOME / "LocalAI_mirror" / "models" / "Qwen3.6-35B-A3B-UD-Q2_K_XL-k160.gguf"   # 10/1: 30B は片付けた
KEKKA = KOUKAI / "dougu" / "kekka"
# koukai の写しの場所 → 本番の名前（dougu が正のもの）
DOUGU_TO_KERNEL = {"jiyuu.py", "kyoudou.py", "hako.py", "kyoukun.py"}


def split_env(text):
    """「KOUKAI_VOCAB_KEEP=ファイル名 --引数 …」を、引数の並びと環境に分ける。語彙ファイルは dougu/jikken から探す。"""
    words, env = shlex.split(text), dict(os.environ)
    while words and re.fullmatch(r"[A-Z_]+=.*", words[0]):
        key, _, value = words.pop(0).partition("=")
        if key == "KOUKAI_VOCAB_KEEP" and "/" not in value:
            value = str(KOUKAI / "dougu" / "jikken" / value)
        env[key] = value
    return words, env


def _url_line(old=""):
    try:
        text = (SUP / "server.url").read_text()
    except FileNotFoundError:   # 開き直しの間は消えている
        return ""
    return next((l.strip() for l in text.splitlines() if l.startswith("http://127.0.0.1") and l.strip() != old), "")


def _parts(line):
    u = urllib.parse.urlsplit(line)
    base = f"{u.scheme}://{u.netloc}"
    return base, urllib.parse.parse_qs(u.query)["t"][0]


def base(old="", wait=120):
    """立っているサーバーの URL。/ping にも合言葉が要る。"""
    deadline = time.time() + wait
    while time.time() < deadline:
        line = _url_line(old)
        if line:
            b, token = _parts(line)
            try:
                urllib.request.urlopen(urllib.request.Request(b + "/ping", headers={"X-Token": token, "Origin": b}), timeout=3)
                return line
            except OSError:
                pass
        time.sleep(1)
    raise SystemExit("サーバーが立っていません（server.url と kernel-ai.log を見る）")


def gakushuu_yasumu():
    """試験の前に事前学習を止め、前の状態を返す。アプリが立っていなければ何もしない（学習も動いていない）。
    10/2: 夜中にアプリが閉じていて、知識の測り直しが「サーバーが立っていません」で始まらなかった。"""
    try:
        line = base(wait=20)
    except SystemExit:
        print("アプリが立っていないので、事前学習を止めずに測ります", flush=True)
        return False
    was_on = call(line, "/gakushuu").get("入")
    if was_on:
        call(line, "/gakushuu", {"入": False})
    return was_on


def gakushuu_modosu(was_on):
    if not was_on:
        return
    try:
        call(base(), "/gakushuu", {"入": True})
    except SystemExit:
        print("アプリが立っていないので、事前学習を戻せませんでした", flush=True)


def call(line, path, body=None, timeout=30):
    b, token = _parts(line)
    headers = {"X-Token": token, "Origin": b, "Referer": b + "/", "Content-Type": "application/json"}
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    request = urllib.request.Request(b + path, data=data, headers=headers, method="GET" if body is None else "POST")
    return json.load(urllib.request.urlopen(request, timeout=timeout))


def loaded_model():
    pid = subprocess.run(["pgrep", "-x", "llama-server"], capture_output=True, text=True).stdout.split()
    if not pid:
        return "なし"
    command = subprocess.run(["ps", "-o", "command=", "-p", pid[0]], capture_output=True, text=True).stdout
    match = re.search(r"-m (\S+)", command)
    return Path(match.group(1)).name if match else "不明"


def jotai(_args):
    line = base(wait=5)
    g = call(line, "/gakushuu")
    print("サーバー", urllib.parse.urlsplit(line).netloc, "｜モデル", loaded_model())
    print("事前学習", {k: g.get(k) for k in ("入", "動いている", "いま")}, g.get("数"))


def ireru(args):
    stamp = datetime.datetime.now().strftime("%m%d_%H%M")
    keep = KEKKA / "moto" / stamp
    keep.mkdir(parents=True, exist_ok=True)
    for name in args.files:
        source = (KOUKAI / name).resolve()
        target = KERNEL / source.name
        if source.parent.name == "dougu" and source.name not in DOUGU_TO_KERNEL:
            raise SystemExit(f"本番に無い dougu のファイルです: {name}")
        if target.exists():
            shutil.copy2(target, keep / target.name)
        text = source.read_text(encoding="utf-8")
        if source.name == "settings.py":   # 公開の写しは <user>
            text = text.replace("<user>", getpass.getuser())
        target.write_text(text, encoding="utf-8")
        if target.suffix == ".py":
            subprocess.run([sys.executable, "-m", "py_compile", str(target)], check=True)
        print("入れた", target.name)
    print("控え", keep.relative_to(KOUKAI))


def _gone(pattern):
    return subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode != 0


def _shimau():
    """窓とサーバー（server.py）を止める。止めたら True。"""
    old = _url_line()
    was_up = False
    if old:
        port = urllib.parse.urlsplit(old).port
        pids = subprocess.run(["lsof", "-nP", f"-tiTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
        for pid in pids:
            if "server.py" in subprocess.run(["ps", "-o", "command=", "-p", pid], capture_output=True, text=True).stdout:
                os.kill(int(pid), signal.SIGTERM)
                was_up = True
    # 窓（kernel-window＝アプリ本体）が生きていると open -a は前に出すだけで、開き直さない。
    for pid in subprocess.run(["pgrep", "-f", "[k]ernel-window"], capture_output=True, text=True).stdout.split():
        os.kill(int(pid), signal.SIGTERM)
    for _ in range(60):
        if _gone("[k]ernel-window") and _gone("[s]erver.py"):
            break
        time.sleep(0.5)
    return was_up


def kaiten(_args):
    old = _url_line()
    _shimau()
    subprocess.run(["open", "-a", "カーネル"], check=True)
    line = base(old)
    print("開き直した", urllib.parse.urlsplit(line).netloc, "｜モデル", loaded_model())


def kiku(args):
    line = base()
    chat = call(line, "/chat/new", {"題": "試験: honban"})["会話"]
    b, token = _parts(line)
    body = json.dumps({"text": args.text, "会話": chat, "michi": args.michi}, ensure_ascii=False).encode()
    request = urllib.request.Request(b + "/ask/stream", data=body, headers={
        "X-Token": token, "Origin": b, "Referer": b + "/", "Content-Type": "application/json"})
    start, tools, answer = time.time(), [], ""
    for raw in urllib.request.urlopen(request, timeout=900):
        text = raw.decode("utf-8", "replace").strip()
        if not text:
            continue
        event = json.loads(text)
        if "操作イベント" in event and event["操作イベント"].get("type") == "tool_start":
            tools.append(event["操作イベント"].get("label", "")[:60])
        if "完了" in event:
            answer = event["完了"].get("出力", "")
    print(f"{round(time.time() - start)}秒｜モデル {loaded_model()}｜道具 {tools}")
    print("答え", answer[:300])
    # 10/1 本人: 試験で作った会話が一覧に溜まって紛らわしい。終わったらゴミ箱へ（戻せる）。
    call(line, "/chat/delete", {"id": chat.get("id") if isinstance(chat, dict) else chat})


def gakushuu(args):
    g = call(base(), "/gakushuu", {"入": args.on == "on"})
    print("事前学習", {k: g.get(k) for k in ("入", "動いている", "いま")})


def j(args):
    """アプリの 30B と試験のモデルは同時に載らない（16GB）。事前学習を止めて 11問、元に戻す。"""
    was_on = gakushuu_yasumu()
    # 10/3: アプリが立ったままだと、温め・横の仕事が同じ 8080 の試験の頭脳へ頼みを送り、
    #   キャッシュを追い出し合った（2つの会話が交互に伸び、1手ごとに全部読み直し・J15/J16 が10分切れ）。試験の間は閉じる。
    app_was_up = _shimau()
    lock = Path.home() / "Library/Application Support/kernel-ai/shiken.lock"   # アプリはこれがある間、頭脳を立てない
    lock.write_text(str(os.getpid()))
    subprocess.run(["pkill", "-x", "llama-server"])
    for _ in range(30):
        if subprocess.run(["pgrep", "-x", "llama-server"], capture_output=True).returncode:
            break
        time.sleep(1)
    out_dir = KEKKA / "kyoudou_0928"
    out_dir.mkdir(parents=True, exist_ok=True)
    model = Path(args.model).expanduser() if args.model else MODEL_MAIN
    log = open(out_dir / f"{args.out}_llama.log", "wb")
    # 例: --args "KOUKAI_EXPERT_P=0.70 --spec-type none"（頭の KOUKAI_…=値 は環境。先読みを変える時は既定の ngram を外す）
    extra, env = split_env(args.args)
    spec = [] if "--spec-type" in extra else ["--spec-type", "ngram-simple", "--spec-ngram-simple-size-m", "16"]
    command = [str(Path(args.llama).expanduser()), "-m", str(model), "--port", "8080", "-t", "6",
               "-ngl", "0", "-c", "8192", "-np", "1", "-cb", "-ub", "256", "--cache-reuse", "16",
               "-fa", "off", "--reasoning-format", "none", *spec, *extra]
    # 10/3: 開き直した直後のアプリは温めのために頭脳を立て直し、8080 を取り返した（試験の頭脳は bind できず 0/3）。
    #   取れなかったら、もう一度止めて立て直す。
    for _ in range(5):
        server = subprocess.Popen(command, stdout=log, stderr=log, env=env)
        time.sleep(8)
        if server.poll() is None:
            break
        subprocess.run(["pkill", "-x", "llama-server"])
        time.sleep(5)
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2)
                break
            except OSError:
                time.sleep(2)
        env = dict(os.environ, **({"KERNEL_JIYUU_OPTS": args.opts} if args.opts else {}))
        extra = (["--id", args.id] if args.id else []) + (["--mondai", args.mondai] if args.mondai else [])
        subprocess.run([sys.executable, "dougu/tegoro.py", "--kata", "輪", "--wa", "jiyuu", *extra,
                        "--output", str(out_dir / f"{args.out}.md")], cwd=KOUKAI, env=env,
                       stdout=open(out_dir / f"{args.out}.log", "w"), stderr=subprocess.STDOUT)
    finally:
        server.terminate()
        server.wait()
        lock.unlink(missing_ok=True)
        if app_was_up:
            kaiten(None)
        gakushuu_modosu(was_on)
    rows = [r for r in (out_dir / f"{args.out}.md").read_text(encoding="utf-8").splitlines() if re.match(r"\| [JH]\d", r)]
    if args.mondai:   # 秘密の問題集は点数だけ出す（中身を開発者に見せない）
        print(f"{model.name}: PASS {sum('PASS' in r for r in rows)} / {len(rows)}")
        return
    print(f"{model.name}: PASS {sum('PASS' in r for r in rows)} / {len(rows)}")
    for row in rows:
        print(row[:110])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("jotai").set_defaults(fn=jotai)
    p = sub.add_parser("ireru"); p.add_argument("files", nargs="+"); p.set_defaults(fn=ireru)
    sub.add_parser("kaiten").set_defaults(fn=kaiten)
    p = sub.add_parser("kiku"); p.add_argument("michi"); p.add_argument("text"); p.set_defaults(fn=kiku)
    p = sub.add_parser("gakushuu"); p.add_argument("on", choices=["on", "off"]); p.set_defaults(fn=gakushuu)
    p = sub.add_parser("j"); p.add_argument("--id"); p.add_argument("--model"); p.add_argument("--opts")
    p.add_argument("--mondai", help="問題集（既定は monosashi/jiyuu.jsonl。秘密の問題集は dougu/kekka/himitsu/）")
    p.add_argument("--out", default="wa_honban"); p.add_argument("--args", default="", help="llama-server に足す引数")
    p.add_argument("--llama", default=str(LLAMA), help="llama-server（圧縮入りは ~/LocalAI_mirror/llama-koukai/llama-server）")
    p.set_defaults(fn=j)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
