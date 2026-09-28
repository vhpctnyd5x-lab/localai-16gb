#!/usr/bin/env python3
"""OpenAI 形式の道具呼び出しで進める、短い文脈の協働の輪。"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import shlex
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.dont_write_bytecode = True  # 読取だけの kernel/ に import の .pyc を作らない
import kyoudou as gate
import web

SYSTEM = ("あなたはこのMacの作業係です。依頼を短く計画し、道具を使い、結果を見て次を決めてください。"
          "複数手なら達成条件を決めてください。移動はmove、削除はtrash（ゴミ箱へ）を使います。shでは消す・移すはできません。"
          "Macの様子（音量・電池・時刻・外付けなど）はmacで見ます。アプリを開くのはsh（open -a）、設定を見るのはsh（defaults readなど）です。"
          "同じ道具を同じ引数で繰り返さないでください。承認されなかった手は、承認が要ることを伝えて終えてください。"
          "ファイルの場所は依頼に書かれたフォルダまで含めて使い、名前だけをホーム直下に置かないでください。"
          "見つからない時は、答えを出す前にfindでホーム以下を名前から探し、見つけた場所を確認してください。"
          "ファイルを変えたら最後にfindまたはreadで存在と中身を確かめてください。権限拒否を別の道具で回避しないでください。"
          "道具を呼ばない返事で終了します。")

def _system() -> str:
    """9/28: 30B はホームの場所を知らず「/Users/yourusername」と想像で書いていた。本当の場所を教える（Mac ごとに一定なので KV は使い回せる）。"""
    return SYSTEM + f"ホームは {Path.home()} です（~ と書いてもよい）。場所は想像で書かず、ホームから書いてください。"

def _tool(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required,
                           "additionalProperties": False}}}

def _s(description):
    return {"type": "string", "description": description}

TOOLS = [
    _tool("sh", "砂箱で命令を実行。裏実行の結果確認と停止もできる。",
          {"command": _s("命令"), "background": {"type": "boolean"},
           "job": _s("仕事ID"), "action": {"type": "string", "enum": ["output", "stop"]}}, []),
    _tool("read", "ファイルやフォルダを読む。", {"path": _s("場所"), "start": _s("開始"), "end": _s("終了")}, ["path"]),
    _tool("write", "ファイルを書く。", {"path": _s("場所"), "content": _s("中身")}, ["path", "content"]),
    _tool("edit", "完全一致の1か所を直す。", {"path": _s("場所"), "old": _s("元"), "new": _s("新")}, ["path", "old", "new"]),
    _tool("find", "名前または本文から探す。", {"dir": _s("起点"), "glob": _s("名前の型"), "text": _s("本文")}, ["dir"]),
    _tool("trash", "対象をゴミ箱に移す。", {"paths": {"type": "array", "items": _s("場所")}}, ["paths"]),
    _tool("mac", "Macの様子を見る（音量・電池・メモリ・時刻・ネット・版と空き・重いアプリ・外付け）。", {"what": _s("見たいこと")}, ["what"]),
    _tool("move", "移す・名前を変える。上書きはしない。dstが既存フォルダか/で終わればその中へ。", {"src": _s("元"), "dst": _s("先")}, ["src", "dst"]),
    _tool("web", "検索か公開ページの読取。", {"query": _s("検索語"), "url": _s("URL")}, []),
]
SPECS = {item["function"]["name"]: item["function"]["parameters"] for item in TOOLS}
JOBS: dict[str, tuple[subprocess.Popen, Path, threading.Thread]] = {}
MAX_STEPS = 20
MAX_SECONDS = 600
_DELETE = re.compile(r"(?i)(?:^|[;&|()]\s*|\s)(?:rm|rmdir|unlink|shred|srm|trash)\b|\bfind\b[^\n]*\s-delete\b|\bdiskutil\s+erase\w*\b")
_DANGER = re.compile(r"(?i)\b(?:sudo|csrutil|sharing)\b|\bfdesetup\s+disable\b|\bspctl\s+--master-disable\b|\bsocketfilterfw\s+--setglobalstate\s+(?:off|0)\b|\bsystemsetup\s+-set(?:remotelogin|remoteappleevents)\s+on\b|\bdefaults\s+write\s+[^\n]*com\.apple\.alf\b")
_SECRET_NAME = re.compile(r"(?i)^(?:\.env|\..*\.env|auth\.json|credentials[^/]*|[^/]+\.(?:pem|key)|id_(?:rsa|ed25519)[^/]*|cookies(?:-journal)?|login data)$")
_SENSITIVE_COMMAND = re.compile(r"(?i)\bsecurity\s+find-[\w-]*-password\b")
_GUARD_SETTING = re.compile(r"(?i)\b(?:csrutil|spctl|fdesetup)\b|\bsocketfilterfw\s+--setglobalstate\s+(?:off|0)\b|\bsystemsetup\s+-setremotelogin\s+on\b|\btmutil\s+disable\b")
_GUARD_DOMAIN = re.compile(r"(?i)\b(?:com\.apple\.(?:screensaver|loginwindow|alf|security[\w.-]*)|LSQuarantine|SoftwareUpdate)\b")
_DEFAULTS_MUTATION = re.compile(r"(?i)\bdefaults\s+(?:-[\w-]+\s+)*(?:write|delete)\s+([^\n;&|]+)")
_THINK = re.compile(r"<think>.*?</think>\s*", re.S)

def _clean(text: str) -> str:
    """考えの印を取る。閉じる印だけが残った時（前に考えの切れ端がある）は、その後ろだけを使う。"""
    text = _THINK.sub("", str(text or ""))
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    text = text.replace("<think>", "").strip()
    text = re.sub(r"^[^\n\u3040-\u30ff\u4e00-\u9fff]{1,12}\n\s*\n(?=[\s\S]*[\u3040-\u30ff\u4e00-\u9fff])", "", text)
    return re.sub(r"^答え\s*[:：]\s*", "", text)   # 9/28: 「答え：」で始める癖を取る
_AGENT = re.compile(r"(?i)(?:\.claude|\.codex|claude\.app|\bclaude(?:\s+code)?\b|\bcodex\b|@anthropic-ai|@openai/codex)")

def _home_resolve(raw) -> Path:
    """相対の場所はホームから数える（sh の作業フォルダと同じ）。"""
    path = Path(os.path.expanduser(_volume_path(str(raw))))
    return Path(os.path.abspath(path if path.is_absolute() else Path.home() / path))

def _secret_path(raw) -> bool:
    """名前で分かる秘密と秘密フォルダは、読取を含め全道具で禁止する。"""
    lexical = _home_resolve(raw)
    home = Path(os.path.realpath(Path.home()))
    for path in (lexical, Path(os.path.realpath(lexical))):
        parts = tuple(part.casefold() for part in path.parts)
        if any(part in {".ssh", ".gnupg", ".aws", "keychains"} for part in parts):
            return True
        if (path == home / ".netrc" or parts[-2:] == (".config", "gh")
                or ".config" in parts and "gh" in parts[parts.index(".config") + 1:]):
            return True
        if any(_SECRET_NAME.fullmatch(part) for part in parts):
            return True
    return False

def _forbidden_command(command: str) -> bool:
    if _SENSITIVE_COMMAND.search(command) or _GUARD_SETTING.search(command):
        return True
    if any(_GUARD_DOMAIN.search(m.group(1)) for m in _DEFAULTS_MUTATION.finditer(command)):
        return True
    # 引用符や環境変数を含む命令でも、秘密の場所を明示した時点で止める。
    if re.search(r"(?i)(?:^|[/~\s'\"=])(?:\.ssh|\.gnupg|\.aws|\.netrc|keychains|auth\.json|credentials[\w.-]*|id_(?:rsa|ed25519)[\w.-]*|cookies(?:-journal)?|login data|[^/\s'\"]+\.(?:pem|key)|\.env|\.[\w.-]+\.env)(?:[/\s'\";]|$)", command):
        return True
    if re.search(r"(?i)\.config/gh(?:/|\b)", command):
        return True
    return gate._command_reads_secret(command)

def _volume_path(value: str) -> str:
    """外付けの表記を、実在する場所に合わせる。試験用ホームの仮想Volumesも尊重する。"""
    home_volumes = Path.home() / "Volumes"
    if value.startswith("~/Volumes/") and not home_volumes.exists():
        return value[1:]
    if value.startswith("/Volumes/") and not Path(value).exists():
        local = home_volumes / value[len("/Volumes/"):]
        if local.exists():
            return str(local)
    return value

def _is_big_root(path: Path) -> bool:
    """ホーム・書類・デスクトップ・ボリュームそのものなど、丸ごと動かしてはいけない場所。"""
    home = Path.home()
    big = [Path("/"), Path("/Users"), Path("/Applications"), Path("/System"), Path("/Library"), Path("/Volumes"), home]
    big += [home / n for n in ("Desktop", "Documents", "Downloads", "Library", "Pictures", "Music", "Movies", "Applications", "Public", ".Trash")]
    real = Path(os.path.realpath(path))
    return real in {Path(os.path.realpath(b)) for b in big} or real.parent == Path("/Volumes")

def _unmovable(raw, big: bool = True) -> bool:
    """big=False は行き先用（書類フォルダの中へ入れるのは良い。丸ごと動かすのは元だけが問題）。"""
    path = _home_resolve(raw)
    return (big and _is_big_root(path)) or gate._is_protected_path(str(path), mutation=True) or gate._is_secret_path(str(path))

_MAC_Q = [
    (r"外付け|外部|SSD|USB", "外付けは何が繋がってる？"),
    (r"音量|ボリューム", "音量はいくつ？"),
    (r"電池|バッテリー|充電", "電池はあと何%？"),
    (r"メモリ", "メモリはどれくらい使ってる？"),
    (r"時刻|時間|何時|日付|今日", "いま何時？"),
    (r"ネット|Wi-?Fi|インターネット", "ネットにつながってる？"),
    (r"版|バージョン|macOS|名前", "このMacの名前とmacOSの版は？"),
    (r"空き|容量|ストレージ|ディスク", "このMacのmacOSの版と、起動ディスクの空き容量を数値で教えて"),
    (r"重い|CPU|負荷|アプリ", "一番重いアプリは？"),
    (r"起動", "起動してからどのくらい？"),
]

# 9/28: 近道（カーネルが一瞬で答える）は、ねらいを絞った問いを取りちがえる
#（「デスクトップの dougu_shiken の中で一番大きいファイル」に、デスクトップの一覧で答えた）。
# 名前・フォルダの中・いちばん○○・操作の言葉がある問いは、新しい輪で考える。
_KUWASHII = re.compile(
    r"[「『\"]"                                   # 名前を括って指している
    r"|\w*[_.][A-Za-z0-9]+"                      # dougu_shiken・テスト.txt のような名前
    r"|の中|中で|中の|にある\S+の中"                 # フォルダの中に絞っている
    r"|(?:の|にある)\S+(?:で|フォルダ)"              # 入れ子の場所
    r"|最大|最小|最新|最古|大きい順|新しい順"
    r"|(?:一番|いちばん|最も)(?:大き|小さ|新し|古)"  # いちばん○○なファイル
    r"|整理|移し|移動|消し|削除|作っ|作成|書い|書き|開い|開け|変え|変更|直し")


def chikamichi_ok(text) -> bool:
    """近道に回してよい問いか。Mac の様子や、場所の一覧・数だけを聞く問いに限る。"""
    return not _KUWASHII.search(str(text or ""))


def _normalize(args: dict) -> dict:
    """相対の場所はホームから数える（門番もこの場所で判断する）。~ はそのまま（門番が広げる）。"""
    def fix(value):
        if isinstance(value, str) and value:
            value = _volume_path(value)
            if not value.startswith(("/", "~")):
                return str(Path.home() / value) + ("/" if value.endswith("/") else "")
        return value
    for key in ("path", "dir", "src", "dst"):
        if key in args:
            args[key] = fix(args[key])
    if "paths" in args:
        args["paths"] = [fix(v) for v in args["paths"]]
    return args

def _record(session, step, phase, data, route):
    gate._log_event(session, step, phase, {"輪": "jiyuu", "経路": route, **data})

def _short(result, session, step):
    raw = json.dumps(result, ensure_ascii=False, default=str)
    gate._register_secret_values(raw)
    sensitive = (gate._SESSION_SECRET_DIRTY or gate._contains_secret_value(raw)
                 or gate._AUTH_URL.search(raw) or gate._CARD_NUMBER.search(raw))
    body = gate._redact(raw) if sensitive else raw
    if len(body) <= 1200:
        return body
    if sensitive:
        return body[:1200]
    path = gate._kiroku_dir() / f"{session}_{step}_{uuid.uuid4().hex[:8]}_output.txt"
    path.write_text(body, encoding="utf-8")
    marker = f"\n… 全文: {path} …\n"
    half = max(0, (1200 - len(marker)) // 2)
    return body[:half] + marker + body[-(1200 - len(marker) - half):]

def _compact(messages, hard=False):
    """文脈を 8192 の6割に保つ。30B が返した本当のトークン数で測る（日本語は1字≒1トークンで、字数の見積もりは甘かった）。"""
    used = _LAST_USAGE.get("prompt_tokens") or 0
    if not hard and used <= _CTX * 0.6 and len(json.dumps(messages, ensure_ascii=False)) <= _CTX * 0.6:
        return
    tools = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    for i in tools[:-1 if hard else -2]:
        if len(str(messages[i].get("content", ""))) > 120:
            messages[i]["content"] = "（古い道具の結果は短くしました。要るなら同じ場所をもう一度見てください）"
    if hard:
        for m in messages[1:-2]:
            if m.get("role") == "assistant" and len(str(m.get("content") or "")) > 200:
                m["content"] = str(m["content"])[:200]

_CTX = 8192
_LAST_USAGE: dict = {}

class _ContextFull(Exception):
    """文脈（8192）があふれた。"""

def _post(payload):
    url = os.environ.get("KERNEL_LOCAL_URL", "http://127.0.0.1:8080").rstrip("/") + "/v1/chat/completions"
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.load(response)
    _LAST_USAGE.clear()
    _LAST_USAGE.update(body.get("usage") or {})
    return body["choices"][0]["message"]

def _ask(messages, thinking=False, final=False):
    """final=True は道具を使わせず、答えだけを書かせる（9/28: 終わり時を 30B が決められない対策）。"""
    payload = {"model": "local", "messages": messages, "tools": TOOLS,
               "tool_choice": "none" if final else "auto", "cache_prompt": True,
               "chat_template_kwargs": {"enable_thinking": thinking},
               "max_tokens": 128 if thinking else 512, "temperature": 0.2}
    try:
        return _post(payload)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        if re.search(r"context|exceed", body, re.I):
            raise _ContextFull(body[:200]) from error
        if error.code != 500:
            raise
    # 9/28: 30B が道具の引数の JSON を壊すと、サーバーは 500 を返す。生の返事をもらって、こちらで緩く読む。
    payload["parse_tool_calls"] = False
    try:
        raw = _post(payload).get("content") or ""
    except urllib.error.HTTPError:
        raw = ""
    calls = []
    for block in re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", raw, re.S):
        data = _loose_json(block)
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            args = data.get("arguments", {})
            calls.append({"id": "call_" + uuid.uuid4().hex[:8], "type": "function",
                          "function": {"name": data["name"], "arguments": json.dumps(args if isinstance(args, dict) else {}, ensure_ascii=False)}})
        else:   # 読めない呼び出しは、形を直すよう 30B に返す（_valid が知らせる）
            calls.append({"id": "call_" + uuid.uuid4().hex[:8], "type": "function",
                          "function": {"name": "形が壊れた呼び出し", "arguments": "{}"}})
    return {"content": re.sub(r"<tool_call>.*?</tool_call>", "", raw, flags=re.S).strip(), "tool_calls": calls}

def _text_call(content: str):
    """道具の呼び出しを文字で書いた返事（例: mac\n{"what": "音量"}）を、呼び出しとして読む（9/28 J09）。"""
    names = "|".join(SPECS)
    match = re.fullmatch(r"\s*(" + names + r")\s*[:：]?\s*(\{.*\})\s*", content or "", re.S)
    data = _loose_json(match.group(2)) if match else _loose_json((content or "").strip())
    if match and isinstance(data, dict):
        name, args = match.group(1), data
    elif isinstance(data, dict) and data.get("name") in SPECS and isinstance(data.get("arguments"), dict):
        name, args = data["name"], data["arguments"]
    else:
        return None
    return {"id": "call_" + uuid.uuid4().hex[:8], "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}

def _loose_json(text: str):
    """文字列の中の生の改行・タブを直してから読む（30B がよく壊す所）。"""
    for candidate in (text, _escape_raw_newlines(text)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None

def _escape_raw_newlines(text: str) -> str:
    out, inside, escaped = [], False, False
    for ch in text:
        if inside and not escaped and ch in "\n\t":
            out.append("\\n" if ch == "\n" else "\\t")
            continue
        out.append(ch)
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            inside = not inside
    return "".join(out)

def _valid(call):
    try:
        func = call["function"]
        name = func["name"]
        spec = SPECS[name]
        args = json.loads(func["arguments"])
        if not isinstance(args, dict) or set(args) - set(spec["properties"]) or set(spec["required"]) - set(args):
            raise ValueError("引数の名前または必須項目が違います")
        for key, value in args.items():
            kind = spec["properties"][key]["type"]
            if kind == "string" and not isinstance(value, str) or kind == "boolean" and not isinstance(value, bool) or kind == "array" and (not isinstance(value, list) or not all(isinstance(v, str) for v in value)):
                raise ValueError("引数の型が違います")
        if name == "sh" and (("command" in args) == ("job" in args)):
            raise ValueError("shにはcommandかjobの片方を指定")
        if name == "sh" and "job" in args and args.get("action") not in ("output", "stop"):
            raise ValueError("jobにはactionを指定")
        if name == "web" and (("query" in args) == ("url" in args)):
            raise ValueError("webにはqueryかurlの片方を指定")
        return name, args
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"道具呼び出しの形を直してください: {error}") from error

def _risk(name, args):
    if name == "sh" and "command" in args and _forbidden_command(args["command"]):
        return "禁止"
    if name in ("read", "write", "edit") and _secret_path(args["path"]):
        return "禁止"
    if name == "find" and (_secret_path(args["dir"]) or _secret_path(args.get("glob", ""))):
        return "禁止"
    if name == "move" and (_secret_path(args["src"]) or _secret_path(args["dst"])):
        return "禁止"
    if name == "trash" and any(_secret_path(p) for p in args["paths"]):
        return "禁止"
    if name == "sh" and "job" in args:
        return "戻せる" if args["action"] == "stop" else "見る"
    if name == "sh":
        command = args["command"]
        if _DELETE.search(command) or _DANGER.search(command) or _AGENT.search(command):
            return "禁止"
        if gate._command_has_outbound(command) and (gate._SESSION_SECRET_DIRTY or gate._contains_secret_value(command) or gate._command_reads_secret(command)):
            return "禁止"
        if args.get("background") and gate._command_reads_secret(command):
            return "禁止"
        risk = gate.kensa({"命令": {"cmd": command}})
        if risk == "戻せない":
            try:
                words = shlex.split(command)
            except ValueError:
                words = []
            if len(words) in (2, 3) and words[0] == "defaults" and words[1] in ("read", "domains", "find"):
                return "見る"
            if words == ["osascript", "-e", "get volume settings"] or words == ["osascript", "-e", "output volume of (get volume settings)"]:
                return "見る"
        return risk
    if name == "mac":
        return "見る"
    if name == "web":
        value = args.get("query", args.get("url", ""))
        if gate._contains_secret_value(value) or gate._looks_sensitive_content(value) or gate._SESSION_SECRET_DIRTY:
            return "禁止"
        return "見る"
    if name == "trash":
        paths = args["paths"]
        if not paths or any(_unmovable(p) for p in paths):
            return "禁止"
        return "戻せる"
    if name == "move":
        if _unmovable(args["src"]) or _unmovable(args["dst"].rstrip("/") or "/", big=False):
            return "禁止"
        return "戻せる"
    if name == "find":
        if gate._is_protected_path(args["dir"]):
            return "禁止"
        return gate.kensa({"読む": {"path": args["dir"]}})
    if gate._is_protected_path(args["path"]):
        return "禁止"
    kind = {"read": "読む", "write": "書く", "edit": "直す"}[name]
    return gate.kensa({kind: {"path": args["path"], **({"text": args.get("content", "")} if name == "write" else {})}})

def _job(args, risk, session, approved=False):
    if "job" in args:
        item = JOBS.get(args["job"])
        if item is None:
            return {"ok": False, "結果": "仕事IDが見つかりません"}
        process, path, reader = item
        if args["action"] == "stop" and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
        if process.poll() is not None:
            reader.join(timeout=1)
        output = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        if process.poll() is not None:
            JOBS.pop(args["job"], None)
        return {"ok": True, "job": args["job"], "状態": "実行中" if process.poll() is None else "終了", "終了コード": process.poll(), "結果": output}
    command = args["command"]
    if not args.get("background"):
        try:
            completed = gate._sandbox_command(
                command, risk=risk, deny_unlink=True,
                network_approved=bool(approved and risk == "戻せない" and gate._command_has_outbound(command)),
                cwd=os.path.expanduser("~"), env=os.environ.copy(), capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL)
            output = (completed.stdout or "") + (("\n" if completed.stdout else "") + completed.stderr if completed.stderr else "")
            return {"ok": completed.returncode == 0, "終了コード": completed.returncode,
                    "結果": output or ("出力なし" if completed.returncode == 0 else "命令が失敗しました")}
        except subprocess.TimeoutExpired:
            return {"ok": False, "結果": "60秒で時間切れになりました"}
    path = Path(gate._archive_text("", "jiyuu_job", session, 0))
    executable = gate.hako._sandbox_executable(os.environ)
    profile = gate.hako.build_profile(risk, bool(approved and risk == "戻せない" and gate._command_has_outbound(command)),
                                      protected_roots=gate._protected_roots() + gate._mutation_only_roots(), deny_unlink=True)
    process = subprocess.Popen([executable, "-p", profile, "/bin/zsh", "-lc", command],
                               cwd=os.path.expanduser("~"), stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    def capture():
        with path.open("a", encoding="utf-8") as output:
            for chunk in iter(lambda: process.stdout.read1(4096), b""):
                decoded = chunk.decode("utf-8", errors="replace")
                gate._register_secret_values(decoded)
                output.write(gate._redact(decoded))
                output.flush()
    reader = threading.Thread(target=capture, daemon=True)
    reader.start()
    ident = uuid.uuid4().hex[:12]
    JOBS[ident] = (process, path, reader)
    return {"ok": True, "job": ident, "状態": "実行中", "出力": str(path)}

def _run(name, args, risk, session, approved=False):
    if name == "sh":
        return _job(args, risk, session, approved=approved)
    if name == "read":
        return gate._read_file(args["path"], args.get("start"), args.get("end"), session=session)
    if name == "write":
        return gate._write_file(args["path"], args["content"])
    if name == "edit":
        return gate._edit_file(args["path"], args["old"], args["new"])
    if name == "find":
        root = Path(gate._resolve_path(args["dir"]))
        if not root.is_dir():
            return {"ok": False, "結果": "フォルダが見つかりません"}
        pattern = args.get("glob", "*")
        if pattern.startswith("/") or ".." in Path(pattern).parts:
            return {"ok": False, "結果": "globは起点の内側だけ指定"}
        found = []
        for path in root.glob(pattern):
            if _secret_path(path):
                continue
            if len(found) >= 100:
                break
            if args.get("text"):
                if not path.is_file() or path.stat().st_size > 1_000_000:
                    continue
                if args["text"] not in path.read_text(encoding="utf-8", errors="replace"):
                    continue
            found.append(str(path))
        return {"ok": True, "件数": len(found), "場所": found}
    if name == "trash":
        moved = []
        destination = Path.home() / ".Trash"
        destination.mkdir(exist_ok=True)
        for raw in args["paths"]:
            if _unmovable(raw):   # 9/28: 相対の場所もホームから数えて確かめる
                return {"ok": False, "結果": "保護された場所や大きなフォルダは移せません", "場所": moved}
            path = _home_resolve(raw)
            if not os.path.lexists(path):
                return {"ok": False, "結果": f"見つかりません: {raw}", "場所": moved}
            target = destination / path.name
            if target.exists():
                target = destination / f"{path.name}.{uuid.uuid4().hex[:8]}"
            shutil.move(str(path), str(target))
            moved.append(str(target))
        return {"ok": True, "結果": "ゴミ箱へ移しました", "場所": moved}
    if name == "mac":
        what = args["what"]
        answers = []
        for pattern, question in _MAC_Q:   # 言葉を、近道が答えられる決まった問いに言い換える
            if re.search(pattern, what, re.I):
                one = gate._quick_answer(question, "jiyuu_mac")   # 近道の入口（テストG の G35〜G44・G51 で通っている問い）
                if one and one not in answers:
                    answers.append(one)
        return {"ok": bool(answers), "結果": "\n".join(answers) or "分かりませんでした。shで調べてください。"}
    if name == "move":
        src, dst = _home_resolve(args["src"]), _home_resolve(args["dst"])
        if not os.path.lexists(src):
            return {"ok": False, "結果": f"見つかりません: {args['src']}"}
        as_folder = (dst.is_dir() or args["dst"].endswith("/")
                     or (not os.path.lexists(dst) and not dst.suffix and src.suffix))   # 「整理へ移して」はフォルダのこと（9/28 J04）
        if as_folder:
            dst = dst / src.name
        if os.path.lexists(dst):
            return {"ok": False, "結果": f"移動先に同じ名前があります（上書きしません）: {dst}"}
        if _unmovable(dst, big=False):
            return {"ok": False, "結果": "保護された場所へは移せません"}
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"ok": True, "結果": "移しました", "元": str(src), "先": str(dst)}
    if "query" in args:
        return {"ok": True, "結果": web.sagasu(args["query"])}
    result = web.yomu(args["url"])
    return {"ok": not bool(result.get("error")), "結果": result}

def _emit(on_event, event):
    if on_event is not None:
        try:
            on_event(event)
        except Exception:
            pass

def _display(value, limit=90):
    body = " ".join(str(value).split())
    gate._register_secret_values(body)
    body = gate._redact(body)
    return body[:limit] + ("…" if len(body) > limit else "")

def _show_path(value):
    path = str(value)
    home = str(Path.home())
    return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path

def _kiku(name, args, risk):
    """承認を聞く。札には人の言葉（_label）と本当の危険度を出す（9/28: 前は JSON と「戻せない」固定だった）。"""
    try:
        return gate.shounin.kiku(_label(name, args), risk=risk)
    except TypeError:   # risk を受けない古い shounin
        return gate.shounin.kiku(_label(name, args))


def _label(name, args):
    if name == "move":
        return _display(f"移す: {_show_path(args['src'])} → {_show_path(args['dst'])}")
    if name == "trash":
        paths = args["paths"]
        return _display("ゴミ箱へ: " + (_show_path(paths[0]) if paths else "対象なし") + (f" ほか{len(paths)-1}つ" if len(paths) > 1 else ""))
    if name == "sh":
        return _display("実行: " + args.get("command", f"仕事 {args.get('action', '')}: {args.get('job', '')}"))
    if name == "web":
        return _display("調べる: " + args.get("query", args.get("url", "")))
    if name == "find":
        return _display("探す: " + _show_path(args["dir"]) + "/" + args.get("glob", "*"))
    if name == "mac":
        return _display("Macを見る: " + args["what"])
    return _display({"read": "読む", "write": "書く", "edit": "直す"}[name] + ": " + _show_path(args["path"]))

def _missing_hint(name, args, result):
    """場所が無い時だけ、次に探す手を道具の返事へ添える。"""
    if result.get("ok") or name not in ("read", "edit", "move", "trash", "find"):
        return result
    body = str(result.get("結果", ""))
    if "見つかりません" not in body and "存在しません" not in body:
        return result
    raw = args.get("src", args.get("path", args.get("dir", "")))
    if name == "trash":
        raw = args["paths"][0] if args["paths"] else ""
    filename = Path(str(raw).rstrip("/")).name
    if filename and name != "find":
        result["次"] = f"場所を決めつけず、findのdirを~、globを**/{filename}として探し、見つかった場所を確認してください。"
    elif name == "find":
        result["次"] = "起点の場所を確認し、必要ならホーム以下から探してください。"
    return result

def kotaeru(text: str, rireki: list[dict] | None = None, mode: str | None = None, on_event=None) -> str:
    if not text or not text.strip():
        return "頼みが空です"
    mode = mode or "自動"
    if mode not in ("手動", "自動", "バイパス", "読むだけ"):
        raise ValueError("modeは手動・自動・バイパス・読むだけ")
    route = os.environ.get("KERNEL_JIYUU_ROUTE", "画面")
    session = "jiyuu_" + uuid.uuid4().hex[:16]
    messages = [{"role": "system", "content": _system()}]
    for row in (rireki or [])[-6:]:
        if row.get("role") in ("user", "assistant"):
            messages.append({"role": row["role"], "content": str(row.get("content", row.get("text", "")))[:1200]})
    messages.append({"role": "user", "content": text})
    gate._reset_session()
    gate.shounin.hajimeru()
    start = time.monotonic()
    failures = 0
    used = 0
    seen: set[str] = set()
    force = False
    try:
        _record(session, 0, "依頼", {"文": text, "モード": mode}, route)
        for step in range(1, MAX_STEPS + 1):
            if time.monotonic() - start >= MAX_SECONDS or gate.TOMERU is not None and gate.TOMERU.is_set():
                _emit(on_event, {"type": "note", "text": "時間切れ、または停止されました。"})
                return "時間切れ、または停止されました。"
            try:
                reply = _ask(messages, final=force)   # 9/28: 考える段は外した。force は答えだけを書かせる
            except _ContextFull:
                _compact(messages, hard=True)
                reply = _ask(messages, final=True)
            except urllib.error.URLError as error:
                _record(session, step, "結果", {"ok": False, "結果": f"30B の返事を読めませんでした: {error}"}, route)
                return "30B の返事を読めませんでした（サーバーの誤り）。もう一度頼んでください。"
            calls = [] if force else (reply.get("tool_calls") or [])
            if not calls and not force:
                written = _text_call(_clean(reply.get("content") or ""))
                if written:
                    calls, reply = [written], {"content": ""}
            if not isinstance(calls, list):
                calls = []
                reply = {"content": "道具呼び出しの形を直してください。"}
            for call in calls:
                if isinstance(call, dict) and not call.get("id"):
                    call["id"] = "call_" + uuid.uuid4().hex[:8]
            reply["content"] = _clean(reply.get("content") or "")
            messages.append({"role": "assistant", "content": reply.get("content") or "", **({"tool_calls": calls} if calls else {})})
            if not calls:
                answer = gate._redact(reply.get("content") or "完了しました。")
                _record(session, step, "結果", {"答え": answer}, route)
                return answer
            for call in calls:
                if used >= MAX_STEPS:
                    _emit(on_event, {"type": "note", "text": "20手の上限に達しました。"})
                    return "20手の上限に達しました。"
                used += 1
                ident = call.get("id") if isinstance(call, dict) else "call_" + uuid.uuid4().hex[:8]
                name, args = None, None
                try:
                    name, args = _valid(call)
                    args = _normalize(args)
                    signature = name + json.dumps(args, ensure_ascii=False, sort_keys=True)
                    risk = "同じ手" if signature in seen else _risk(name, args)
                    seen.add(signature)
                    _record(session, step, "提案", {"道具": name, "入力": args, "門番": risk}, route)
                    _emit(on_event, {"type": "tool_start", "id": ident, "name": name,
                                     "label": _label(name, args), "risk": risk})
                    if risk == "同じ手":
                        result = {"ok": False, "結果": "同じ手をもう一度呼んでいます。前の結果を使って、道具を使わずに答えてください。"}
                        force = True
                        _emit(on_event, {"type": "note", "text": "同じ操作の繰り返しを止めました。"})
                    elif risk == "禁止":
                        result = {"ok": False, "結果": "禁止された操作です。削除はtrashを使ってください。"}
                    elif mode == "読むだけ" and risk != "見る":
                        result = {"ok": False, "結果": "読むだけの設定なので、見る以外はしません"}
                    elif (mode == "手動" and risk != "見る" or mode == "自動" and risk == "戻せない") and not _kiku(name, args, risk):
                        result = {"ok": False, "結果": "承認されませんでした。同じ手は繰り返さず、承認が要ることを本人に伝えて終えてください。"}
                        force = True
                        _emit(on_event, {"type": "note", "text": "承認されなかったため、操作を止めました。"})
                    else:
                        result = _run(name, args, risk, session, approved=(mode == "バイパス" or risk == "戻せない"))
                        result = _missing_hint(name, args, result)
                    failures = 0 if result.get("ok") else failures + 1
                except Exception as error:
                    result = {"ok": False, "結果": gate._redact(error)}
                    failures += 1
                if name is not None and args is not None:
                    _emit(on_event, {"type": "tool_end", "id": ident, "ok": bool(result.get("ok")),
                                     "summary": _display(result.get("結果", "完了"))})
                tool_content = _short(result, session, step)
                _record(session, step, "結果", result, route)
                messages.append({"role": "tool", "tool_call_id": ident, "content": tool_content})
            if used >= 16:
                force = True   # 手数の予算。ここからは答えさせる
                _emit(on_event, {"type": "note", "text": "操作の上限が近いため、ここで答えをまとめます。"})
            _compact(messages)
        _emit(on_event, {"type": "note", "text": "20手の上限に達しました。"})
        return "20手の上限に達しました。"
    finally:
        gate.shounin.owaru()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("text")
    parser.add_argument("--mode", choices=("手動", "自動", "バイパス", "読むだけ"), default="自動")
    options = parser.parse_args()
    print(kotaeru(options.text, mode=options.mode))
