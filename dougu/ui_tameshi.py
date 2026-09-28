#!/usr/bin/env python3
"""隔離した新画面の API 試験。通常は URL を出して前面で待つ。"""
import argparse
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "kernel"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="API を確認して終了")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="kernel-ui-") as base:
        scratch = Path(base)
        work = scratch / "project" / "kernel"
        work.parent.mkdir(parents=True)
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "settings.json", "journal.jsonl",
            "notebook*.json", "*.db", "*.sqlite3", "kiroku", "hikae", "waza"))
        # 本番と同じ並び: 新しい輪と門番（dougu が正）を kernel の中に置く
        for name in ("jiyuu.py", "kyoudou.py", "hako.py"):
            shutil.copy2(ROOT / "dougu" / name, work / name)
        home = scratch / "home"
        home.mkdir()
        real_home = Path.home()
        for name in (".nvidia.env", ".groq.env"):
            secret = real_home / name
            if secret.is_file():
                (home / name).symlink_to(secret)
        env = os.environ.copy()
        env.update(HOME=str(home), KERNEL_PROJECT_DIR=str(work.parent),
                   KERNEL_KIROKU_DIR=str(work / "kiroku"),
                   KERNEL_WAZA_DIR=str(work / "waza"),
                   KERNEL_HIKAE_DIR=str(work / "hikae"),
                   KERNEL_TSUIKA_DIR=str(work / "tsuika"),
                   KERNEL_MODERU_IDLE="0", KERNEL_PORT=env.get("KERNEL_PORT", "0"))
        models = real_home / "LocalAI_mirror" / "models"
        if models.is_dir():
            env["KERNEL_MODELS_DIR"] = str(models)
        binary = real_home / "LocalAI_mirror" / "llama-latest" / "build" / "bin" / "llama-server"
        if binary.is_file():
            env["KERNEL_LLAMA_SERVER"] = str(binary)
        if args.check:
            env["KERNEL_LOCAL_URL"] = "http://127.0.0.1:9"
        proc = subprocess.Popen([sys.executable, "-B", str(work / "server.py")],
                                cwd=work, env=env, stdout=subprocess.PIPE,
                                stderr=sys.stderr, text=True, bufsize=1)
        try:
            ready, _, _ = select.select([proc.stdout], [], [], 20)
            if not ready:
                raise RuntimeError("20秒以内に URL が出ませんでした")
            url = proc.stdout.readline().strip()
            parsed = urllib.parse.urlparse(url)
            token = urllib.parse.parse_qs(parsed.query).get("t", [""])[0]
            if parsed.hostname != "127.0.0.1" or not token:
                raise RuntimeError("合言葉付き URL を受け取れませんでした")
            for endpoint in ("/state", "/settings", "/commands"):
                req = urllib.request.Request(f"{parsed.scheme}://127.0.0.1:{parsed.port}{endpoint}",
                                             headers={"X-Token": token})
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status != 200:
                        raise RuntimeError(f"{endpoint}: HTTP {response.status}")
                    response.read()
                print(f"{endpoint}: 200", file=sys.stderr)
            if args.check:
                print("API 3件: 200", flush=True)
            else:
                print(url, flush=True)
                proc.wait()
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
