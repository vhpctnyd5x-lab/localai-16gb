#!/usr/bin/env python3
"""NVIDIA Build を協働の輪の代わりの頭・HTML 判定役として使う。"""

import argparse
import contextlib
import datetime
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request


DEFAULT_UPSTREAM = "https://integrate.api.nvidia.com/v1/chat/completions"
LOG = Path(__file__).resolve().parent / "kekka" / "nv_kawari.jsonl"
# chat_template_kwargs は渡す（kimi-k3 は enable_thinking=False で考えを省く。9/26 試し）
DROP = {"grammar", "json_schema", "cache_prompt",
        "n_probs", "id_slot", "slot_id", "mirostat", "mirostat_tau",
        "mirostat_eta", "repeat_penalty", "repeat_last_n", "penalize_nl",
        "top_k", "min_p", "typical_p", "tfs_z", "n_keep", "n_predict",
        "samplers", "cache_reuse", "seed", "draft_max"}
THINK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.I | re.S)


def get_key(reason):
    """nv.py の _key と同じ取得順序。試験時は秘密に触れない。"""
    if os.environ.get("NV_KAWARI_SHIKEN") == "1":
        return "shiken"
    envf = os.path.expanduser("~/.nvidia.env")
    if os.path.exists(envf) and (os.stat(envf).st_mode & 0o077) == 0:
        with open(envf) as f:
            for line in f:
                if line.startswith("NVIDIA_API_KEY="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value
    sys.path.insert(0, os.path.expanduser("~/.claude/skills/ai-keychain/scripts"))
    import access_broker
    key = access_broker.request_secret("NVIDIA_API_KEY", requester="Claude", reason=reason)
    if not key:
        raise RuntimeError("鍵の取得が承認されませんでした")
    return key


def first_json(content):
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", content):
        try:
            value, end = decoder.raw_decode(content[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            return content[match.start():match.start() + end]
    return content.strip()


def clean_content(content, grammar=False):
    content = THINK.sub("", content or "")
    # 閉じていない思考タグも回答には含めない。
    content = re.sub(r"<think\b[^>]*>.*$", "", content, flags=re.I | re.S)
    return first_json(content) if grammar else content


def prepare(body, model):
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        raise ValueError("messages が必要です")
    grammar = "grammar" in body or "json_schema" in body
    outgoing = {k: v for k, v in body.items() if k not in DROP}
    outgoing["model"] = model
    outgoing["stream"] = False
    outgoing["messages"] = [dict(m) for m in body["messages"]]
    if grammar:
        instruction = "1行のJSONだけを返す"
        systems = [m for m in outgoing["messages"] if m.get("role") == "system"]
        if systems:
            system = systems[-1]
            system["content"] = str(system.get("content") or "") + "\n" + instruction
        else:
            outgoing["messages"].insert(0, {"role": "system", "content": instruction})
    return outgoing, grammar


def record(path, model, status, elapsed, attempts, usage, kind):
    path.parent.mkdir(parents=True, exist_ok=True)
    usage = usage if isinstance(usage, dict) else {}
    item = {"time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "kind": kind, "model": model, "status": status,
            "seconds": round(elapsed, 3), "calls": attempts,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens")}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def query(upstream, key, body, model, log=LOG, kind="kawari", delay=1, tries=2):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    start = time.monotonic()
    status, raw, attempts = 502, b"", 0
    for attempt in range(1, tries + 1):
        attempts = attempt
        request = urllib.request.Request(
            upstream, data=data,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        except TimeoutError:
            status, raw = 504, b'{"error":"upstream timeout"}'
        except urllib.error.URLError as error:
            timed_out = isinstance(error.reason, TimeoutError)
            status = 504 if timed_out else 502
            raw = b'{"error":"upstream timeout"}' if timed_out else b'{"error":"upstream unavailable"}'
        if status not in (429, 502, 503, 504) and status < 500:
            break
        if attempt < tries:
            time.sleep(delay * 2 ** (attempt - 1))
    usage = {}
    if status == 200:
        try:
            result = json.loads(raw)
            usage = result.get("usage") or {}
            raw = result
        except (ValueError, AttributeError):
            status, raw = 502, b'{"error":"invalid upstream JSON"}'
    record(log, model, status, time.monotonic() - start, attempts, usage, kind)
    return status, raw


def proxy_response(body, model, upstream, key, log=LOG, delay=1, tries=2):
    outgoing, grammar = prepare(body, model)
    status, result = query(upstream, key, outgoing, model, log, delay=delay, tries=tries)
    if status == 200:
        for choice in result.get("choices", []):
            message = choice.get("message") or {}
            if isinstance(message.get("content"), str):
                message["content"] = clean_content(message["content"], grammar)
        return status, json.dumps(result, ensure_ascii=False).encode("utf-8")
    return status, result


def serve(model, port, upstream, key, log=LOG):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_json(200, b'{"status":"ok"}')
            else:
                self.send_json(404, b'{"error":"not found"}')

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self.send_json(404, b'{"error":"not found"}')
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 1 or size > 16 * 1024 * 1024:
                    raise ValueError("body size")
                body = json.loads(self.rfile.read(size))
                status, result = proxy_response(body, model, upstream, key, log, delay=5, tries=5)
            except (ValueError, TypeError) as error:
                status, result = 400, json.dumps({"error": str(error)}).encode()
            except Exception:
                status, result = 502, b'{"error":"proxy failure"}'
            self.send_json(status, result)

        def send_json(self, status, data):
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server


def judge(model, files, upstream, key, log=LOG):
    instruction = ("HTMLのページを評価。見た目のかっこよさ、作りの丁寧さ、壊れていないか、"
                   "頼みに合っているかを各1〜10の整数で採点する。見えない動作は推測と明記。"
                   "JSONだけを1行で返す。キーは mitame, teinei, koware, irai, riyuu。"
                   "riyuu は日本語の理由1行。")
    for name in files:
        try:
            html = Path(name).read_text(encoding="utf-8")
            body = {"model": model, "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": f"ファイル名: {name}\nHTML:\n{html}"}],
                "temperature": 0, "stream": False}
            status, result = query(upstream, key, body, model, log, kind="hantei", delay=5, tries=5)
            if status != 200:
                raise RuntimeError(f"upstream HTTP {status}")
            content = clean_content(result["choices"][0]["message"]["content"], True)
            scores = json.loads(content)
            if any(type(scores.get(k)) is not int or not 1 <= scores[k] <= 10
                   for k in ("mitame", "teinei", "koware", "irai")):
                raise ValueError("採点形式が不正です")
            if not isinstance(scores.get("riyuu"), str):
                raise ValueError("理由がありません")
            scores["riyuu"] = " ".join(scores["riyuu"].splitlines())
            output = {"file": name, **scores}
        except (OSError, ValueError, KeyError, IndexError, TypeError, RuntimeError) as error:
            output = {"file": name, "error": str(error)}
        print(json.dumps(output, ensure_ascii=False))


def shiken():
    os.environ["NV_KAWARI_SHIKEN"] = "1"
    assert get_key("test") == "shiken"
    seen = []

    class Fake(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(body)
            if len(seen) == 1:
                status, result = 429, {"error": "retry"}
            elif any("always-fail" in str(m.get("content", "")) for m in body["messages"]):
                status, result = 503, {"error": "unavailable"}
            else:
                status = 200
                content = ('{"mitame":8,"teinei":7,"koware":6,"irai":5,"riyuu":"構造は明瞭"}'
                           if "mitame" in str(body["messages"][0].get("content", ""))
                           else '<think>secret</think>前置き {"ok":true} 後書き')
                result = {"choices": [{"message": {"content":
                          content},
                          "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 3, "completion_tokens": 4,
                                    "total_tokens": 7}}
            raw = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args):
            pass

    fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    thread = threading.Thread(target=fake.serve_forever, daemon=True)
    thread.start()
    upstream = f"http://127.0.0.1:{fake.server_port}/v1/chat/completions"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "calls.jsonl"
            body = {"messages": [{"role": "system", "content": "元の指示"},
                                 {"role": "user", "content": "test"}],
                    "grammar": "root ::= object", "json_schema": {},
                    "cache_prompt": True, "chat_template_kwargs": {},
                    "n_probs": 1, "id_slot": 2, "model": "local"}
            status, raw = proxy_response(body, "fake/model", upstream, get_key("test"), log, 0)
            answer = json.loads(raw)
            assert status == 200 and len(seen) == 2
            assert answer["choices"][0]["message"]["content"] == '{"ok":true}'
            assert answer["choices"][0]["finish_reason"] == "stop"
            assert answer["usage"]["total_tokens"] == 7
            assert all(k not in seen[0] for k in DROP)
            assert seen[0]["model"] == "fake/model"
            assert seen[0]["messages"][0]["content"].endswith("1行のJSONだけを返す")
            assert len(json.loads(log.read_text().splitlines()[0])) == 9
            assert json.loads(log.read_text().splitlines()[0])["calls"] == 2
            seen.clear()
            body.pop("grammar")
            body.pop("json_schema")
            status, raw = proxy_response(body, "fake/model", upstream, "shiken", log, 0)
            assert status == 200
            assert json.loads(raw)["choices"][0]["message"]["content"] == '前置き {"ok":true} 後書き'
            assert "1行のJSONだけを返す" not in seen[-1]["messages"][0]["content"]
            assert len(log.read_text().splitlines()) == 2
            local = serve("fake/model", 0, upstream, "shiken", log)
            local_thread = threading.Thread(target=local.serve_forever, daemon=True)
            local_thread.start()
            try:
                base = f"http://127.0.0.1:{local.server_port}"
                with urllib.request.urlopen(base + "/health") as response:
                    assert response.status == 200
                request = urllib.request.Request(base + "/v1/chat/completions",
                                                 data=json.dumps(body).encode())
                with urllib.request.urlopen(request) as response:
                    assert response.status == 200
                    assert json.load(response)["choices"][0]["message"]["content"].startswith("前置き")
            finally:
                local.shutdown()
                local.server_close()
                local_thread.join()
            fail = {"messages": [{"role": "user", "content": "always-fail"}]}
            status, _ = proxy_response(fail, "fake/model", upstream, "shiken", log, 0)
            assert status == 503
            page = Path(tmp) / "page.html"
            page.write_text("<html><title>Test</title></html>", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                judge("fake/model", [str(page)], upstream, "shiken", log)
            assert json.loads(output.getvalue())["mitame"] == 8
            assert len(log.read_text().splitlines()) == 5
    finally:
        fake.shutdown()
        fake.server_close()
        thread.join()
    print("shiken: OK (HTTP中継・項目除去・JSON抽出・think除去・再試行・記録・採点)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("kawari", "hantei"):
        part = sub.add_parser(command)
        part.add_argument("--model", required=True)
        part.add_argument("--upstream", default=DEFAULT_UPSTREAM)
        if command == "kawari":
            part.add_argument("--port", type=int, default=8091)
        else:
            part.add_argument("files", metavar="file.html", nargs="+")
    sub.add_parser("shiken")
    args = parser.parse_args()
    if args.command == "shiken":
        shiken()
    else:
        key = get_key(f"{args.model} を {args.command} に使用")
        if args.command == "kawari":
            server = serve(args.model, args.port, args.upstream, key)
            print(f"127.0.0.1:{server.server_port} で待機", file=sys.stderr)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        else:
            judge(args.model, args.files, args.upstream, key)


if __name__ == "__main__":
    main()
