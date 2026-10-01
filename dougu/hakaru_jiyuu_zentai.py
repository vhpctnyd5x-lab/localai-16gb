#!/usr/bin/env python3
"""jiyuu の決まり文＋道具定義を HEAD と比較して計測する。"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jiyuu

URL = "http://127.0.0.1:8080"


def definitions(source: str):
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id in {"SYSTEM", "TOOLS"}
                     for target in node.targets)]
    namespace = {"_tool": jiyuu._tool, "_s": jiyuu._s}
    for node in nodes:
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<jiyuu-definitions>", "exec"), namespace)
    return namespace["SYSTEM"], namespace["TOOLS"]


def post(path: str, body: dict):
    request = urllib.request.Request(URL + path, json.dumps(body, ensure_ascii=False).encode(),
                                    {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.load(response)


def measure(system: str, tools: list):
    messages = [{"role": "system", "content": system}]
    chars = len(system) + len(json.dumps(tools, ensure_ascii=False, separators=(",", ":")))
    applied = post("/apply-template", {"messages": messages, "tools": tools,
                                        "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
    tokens = len(post("/tokenize", {"content": applied})["tokens"])
    return chars, tokens


def main():
    old_source = subprocess.run(["git", "show", "HEAD:dougu/jiyuu.py"], check=True,
                                capture_output=True, text=True, encoding="utf-8").stdout
    before = definitions(old_source)
    after = (jiyuu.SYSTEM, jiyuu.TOOLS)
    print("前置き計測（文字数 = 決まり文 + 道具定義 JSON）")
    print(f"項目数: {len(before[1])} → {len(after[1])}")
    print(f"文字数: {len(before[0]) + len(json.dumps(before[1], ensure_ascii=False, separators=(',', ':')))} → "
          f"{len(after[0]) + len(json.dumps(after[1], ensure_ascii=False, separators=(',', ':')))}")
    try:
        old_chars, old_tokens = measure(*before)
        new_chars, new_tokens = measure(*after)
    except (OSError, urllib.error.URLError, TimeoutError, KeyError, ValueError):
        print("トークン数: llama-server (127.0.0.1:8080) 停止中または計測不可")
        return
    print(f"文字数（適用後）: {old_chars} → {new_chars}")
    print(f"トークン数（/apply-template → /tokenize）: {old_tokens} → {new_tokens} "
          f"（{(old_tokens-new_tokens)/old_tokens:.1%}減）")


if __name__ == "__main__":
    main()
