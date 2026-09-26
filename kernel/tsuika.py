#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加道具の候補・登録・退役台帳と sandbox-exec 起動口。"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import hako
import tsuika_worker

VERSION = "1.0.0"
MAX_CODE = tsuika_worker.MAX_SOURCE_BYTES
_ID = re.compile(r"^[a-f0-9]{32}$")


class TsuikaError(RuntimeError):
    pass


def registry_root() -> Path:
    default = Path(os.environ.get("KERNEL_PROJECT_DIR", os.path.expanduser("~/LocalAI_mirror"))) / "kernel" / "tsuika"
    return Path(os.environ.get("KERNEL_TSUIKA_DIR", str(default)))


def _sha(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _manifest_sha(manifest: dict) -> str:
    data = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
        raise TsuikaError("台帳ファイルが不正です")
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise TsuikaError("台帳の形が不正です")
    return value


def _directory(group: str, ident: str, version: str) -> Path:
    if not _ID.fullmatch(str(ident)) or not re.fullmatch(r"\d+\.\d+\.\d+", str(version)):
        raise TsuikaError("追加道具のIDまたは版が不正です")
    return registry_root() / group / ident / version


def retire_dir(path: Path, reason: str) -> None:
    if not path.exists() or path.is_symlink():
        return
    root = registry_root()
    try: relative = path.relative_to(root / "登録")
    except ValueError: return
    target = root / "退役" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists(): target = target.with_name(target.name + "-" + uuid.uuid4().hex[:8])
    try:
        manifest = _read_json(path / "manifest.json")
        manifest["退役理由"] = reason[:300]
        _write_json(path / "manifest.json", manifest)
    except Exception: pass
    os.replace(path, target)


def _record(path: Path, *, used=False, verified=False, elapsed=0.0, approval_denied=False, failure=False) -> None:
    stats_path = path / "usage.json"
    try: stats = _read_json(stats_path)
    except (OSError, ValueError, TsuikaError):
        stats = {"used": 0, "verified_success": 0, "seconds": 0.0, "approval_denied": 0, "failures": 0, "consecutive_failures": 0}
    stats["used"] = int(stats.get("used", 0)) + int(used)
    stats["verified_success"] = int(stats.get("verified_success", 0)) + int(verified)
    stats["seconds"] = round(float(stats.get("seconds", 0)) + max(0.0, elapsed), 3)
    stats["approval_denied"] = int(stats.get("approval_denied", 0)) + int(approval_denied)
    stats["failures"] = int(stats.get("failures", 0)) + int(failure)
    stats["consecutive_failures"] = 0 if verified else int(stats.get("consecutive_failures", 0)) + int(failure)
    _write_json(stats_path, stats)
    if stats["consecutive_failures"] >= 2: retire_dir(path, "同じ失敗が2回続いた")


def record_use(path: Path, *, verified=False, denied=False, elapsed=0.0, failure=False) -> None:
    _record(path, used=True, verified=verified, elapsed=elapsed, approval_denied=denied, failure=failure)


def record_denial(path: Path) -> None:
    _record(path, approval_denied=True)


def worker_profile(home: Path, work: Path) -> str:
    """道具の子の SBPL。通信を禁じ、書くのは働き場だけ。本物の HOME は読めない（9/26 Claude: 見るの profile は
    どこでも読めたので、評価器に万一の穴があると 鍵などを読めた）。読めるのは Python の本体とこの台本だけ。"""
    base_profile = hako.build_profile("見る", home=home, tmpdir=work, protected_roots=[registry_root()])
    profile = "\n".join(line for line in base_profile.splitlines() if not line.lstrip().startswith("(allow network-outbound"))
    profile += "\n(deny network-outbound)\n"
    real_home = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)   # 環境変数 HOME に左右されない本当の家
    profile += f"(deny file-read* (subpath {hako._sbpl_string(real_home)}))\n"
    profile += f"(allow file-read-metadata (subpath {hako._sbpl_string(real_home)}))\n"
    readable = {os.path.realpath(sys.prefix), os.path.realpath(sys.base_prefix),
                os.path.realpath(os.path.dirname(sys.executable)), os.path.realpath(str(work)), os.path.realpath(str(home))}
    for path in sorted(readable):
        profile += f"(allow file-read* (subpath {hako._sbpl_string(path)}))\n"
    worker = os.path.realpath(str(Path(__file__).with_name("tsuika_worker.py")))
    profile += f"(allow file-read* (literal {hako._sbpl_string(worker)}))\n"
    return profile


def run_isolated(source: str, args: Any, inputs: Any, *, tests=False, timeout=6.0) -> dict:
    """hako の SBPL を使う。通信拒否、HOME 隔離、作成物は一時作業場だけ。"""
    tsuika_worker.validate_source(source)
    executable = hako._sandbox_executable(None)
    with tempfile.TemporaryDirectory(prefix="koukai-tsuika-") as temporary:
        root = Path(temporary); home, work = root / "home", root / "work"
        home.mkdir(); work.mkdir()
        token = secrets.token_hex(24)
        env = {"HOME": str(home), "TMPDIR": str(work), "TMP": str(work), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "TSUIKA_WORKER_TOKEN": token}
        profile = worker_profile(home, work)
        payload = json.dumps({"token": token, "source": source, "args": args, "inputs": inputs, "tests": tests}, ensure_ascii=False, separators=(",", ":"))
        if len(payload.encode("utf-8")) > tsuika_worker.MAX_INPUT_BYTES: raise TsuikaError("道具への入力が大きすぎます")
        command = [executable, "-p", profile, sys.executable, str(Path(__file__).with_name("tsuika_worker.py"))]
        try:
            completed = subprocess.run(command, input=payload, text=True, capture_output=True, timeout=timeout, env=env, cwd=str(work), check=False)
        except subprocess.TimeoutExpired as error:
            raise TsuikaError("箱庭の時間上限を超えました") from error
        except (OSError, hako.SandboxUnavailable) as error:
            raise TsuikaError("隔離を始められないため実行しませんでした") from error
        if hako._is_profile_start_error(completed): raise TsuikaError("sandbox-exec が隔離を始められないため実行しませんでした")
        if len(completed.stdout.encode("utf-8", errors="replace")) > tsuika_worker.MAX_OUTPUT_BYTES: raise TsuikaError("箱庭の出力上限を超えました")
        if completed.returncode != 0: raise TsuikaError((completed.stderr or "追加道具の実行に失敗しました")[:700].strip())
        try: result = json.loads(completed.stdout)
        except json.JSONDecodeError as error: raise TsuikaError("箱庭から読めない出力が返りました") from error
        if type(result) is not dict: raise TsuikaError("箱庭の出力形式が違います")
        return result


def prepare_candidate(name: str, description: str, source: str, sandbox_runner: Callable[..., dict] = run_isolated) -> dict:
    name, description = str(name).strip(), str(description).strip()
    if not name or len(name) > 100 or not description or len(description) > 1000: raise TsuikaError("名前または目的が空か長すぎます")
    tsuika_worker.validate_source(source)
    tests = sandbox_runner(source, None, None, tests=True)
    if not tests.get("ok") or not isinstance(tests.get("cases"), int) or tests["cases"] < 1: raise TsuikaError("tameshi() の試験を通過しませんでした")
    caps = tests.get("capabilities", [])
    if not isinstance(caps, list) or any(item not in {"write", "delete", "send"} for item in caps): raise TsuikaError("試験が許可していない能力を要求しました")
    risk = "見る" if not caps else "戻せる" if set(caps) == {"write"} else "戻せない"
    ident = uuid.uuid4().hex
    arguments = tests.get("args_shape")
    if type(arguments) is not dict or arguments.get("type") != "object":
        arguments = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    capabilities = (["親が読み取り確認したUTF-8テキスト"] if tests.get("reads_files") else []) + ["effect:" + item for item in caps]
    manifest = {"id": ident, "name": name, "description": description,
                "arguments": arguments,
                "capabilities": capabilities,
                "scope": "args に指定し、親が確認したファイル・フォルダ・保存先", "risk": risk, "version": VERSION, "sha256": _sha(source)}
    path = _directory("候補", ident, VERSION); path.mkdir(parents=True, exist_ok=False)
    (path / "tool.py").write_text(source, encoding="utf-8")
    _write_json(path / "manifest.json", manifest)
    _write_json(path / "usage.json", {"used": 0, "verified_success": 0, "seconds": 0.0, "approval_denied": 0, "failures": 0, "consecutive_failures": 0})
    return {"id": ident, "version": VERSION, "manifest": manifest, "source": source, "tests": tests, "path": str(path)}


def approval_preview(candidate: dict) -> dict:
    manifest = candidate["manifest"]
    return {"目的": manifest["description"], "名前": manifest["name"], "ID": manifest["id"], "版": manifest["version"],
            "sha256": manifest["sha256"], "コード": candidate["source"], "権限": manifest["capabilities"],
            "対象範囲": manifest["scope"], "危険度": manifest["risk"], "試験結果": candidate["tests"]}


def register_candidate(candidate: dict) -> dict:
    ident, version = candidate["id"], candidate["version"]
    origin = _directory("候補", ident, version)
    source = (origin / "tool.py").read_text(encoding="utf-8")
    manifest = _read_json(origin / "manifest.json")
    if manifest != candidate["manifest"] or _sha(source) != manifest.get("sha256"):
        raise TsuikaError("承認後にコードが変わりました")
    target = _directory("登録", ident, version); target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(origin, target)
    _write_json(target / "approval.json", {"version": version, "sha256": manifest["sha256"],
                                            "manifest_sha256": _manifest_sha(manifest), "approved": True})
    return manifest


def _load_registered(ident: str) -> tuple[dict, str, Path]:
    if not _ID.fullmatch(str(ident)): raise TsuikaError("追加道具のIDが不正です")
    root = registry_root() / "登録" / ident
    for version_path in sorted(root.glob("*"), reverse=True):
        if version_path.is_symlink() or not version_path.is_dir(): continue
        version = version_path.name; path = _directory("登録", ident, version)
        try:
            manifest = _read_json(path / "manifest.json")
            approval = _read_json(path / "approval.json")
            source_path = path / "tool.py"
            if source_path.is_symlink() or not source_path.is_file() or source_path.stat().st_size > MAX_CODE: raise TsuikaError("登録済みコードが不正")
            source = source_path.read_text(encoding="utf-8"); digest = _sha(source)
            expected_approval = {"version": version, "sha256": digest, "manifest_sha256": _manifest_sha(manifest), "approved": True}
            if manifest.get("id") != ident or manifest.get("version") != version or manifest.get("sha256") != digest or approval != expected_approval:
                raise TsuikaError("版または承認ハッシュが一致しません")
            return manifest, source, path
        except Exception as error:
            retire_dir(path, str(error)); raise TsuikaError("登録済みの道具を不整合で退役させました") from error
    raise TsuikaError("登録済みの追加道具がありません")


def _matches_shape(value: Any, schema: dict) -> bool:
    kind = schema.get("type")
    if kind == "object":
        if type(value) is not dict: return False
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list) or any(key not in value for key in required): return False
        if schema.get("additionalProperties") is False and any(key not in properties for key in value): return False
        return all(key not in properties or _matches_shape(item, properties[key]) for key, item in value.items())
    if kind == "array":
        return type(value) is list and len(value) <= tsuika_worker.MAX_ITEMS and all(_matches_shape(item, schema.get("items", {})) for item in value)
    if kind == "string": return type(value) is str
    if kind == "integer": return type(value) is int
    if kind == "number": return type(value) in (int, float)
    if kind == "boolean": return type(value) is bool
    if kind == "null": return value is None
    return True


def validate_args(manifest: dict, args: Any) -> None:
    schema = manifest.get("arguments")
    if type(args) is not dict or type(schema) is not dict or not _matches_shape(args, schema):
        raise TsuikaError("args が登録時に試験した形と一致しません")


def list_registered() -> list[dict]:
    root = registry_root() / "登録"
    if not root.is_dir(): return []
    result = []
    for directory in sorted(root.iterdir()):
        if directory.is_symlink() or not directory.is_dir() or not _ID.fullmatch(directory.name): continue
        try:
            manifest, _source, _path = _load_registered(directory.name)
            result.append({key: manifest[key] for key in ("id", "name", "description", "arguments", "capabilities", "scope", "risk", "version")})
        except (OSError, ValueError, TsuikaError, KeyError): pass
    return result


def run_registered(ident: str, args: Any, inputs: Any) -> tuple[dict, dict, Path]:
    manifest, source, path = _load_registered(ident)
    validate_args(manifest, args)
    return run_isolated(source, args, inputs), manifest, path


def _self_test():
    assert _sha("abc") == hashlib.sha256(b"abc").hexdigest()
    assert _ID.fullmatch("a" * 32)
    try: _directory("登録", "../bad", VERSION)
    except TsuikaError: pass
    else: raise AssertionError("不正IDを拒否しませんでした")
    source = "def run(args, inputs):\n return {'result': len(inputs['files']), 'effects': []}\ndef tameshi():\n return [{'args':{},'inputs':{'files':[{'path':'x.txt','text':'x'}]},'expected':{'result':1,'effects':[]}}]"
    prior = os.environ.get("KERNEL_TSUIKA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="tsuika-ledger-test-") as temporary:
            os.environ["KERNEL_TSUIKA_DIR"] = temporary
            runner = lambda _source, _args, _inputs, tests=False: {"ok": True, "cases": 1, "capabilities": []}
            candidate = prepare_candidate("試験道具", "台帳連鎖の試験", source, sandbox_runner=runner)
            preview = approval_preview(candidate)
            assert preview["コード"] == source and preview["sha256"] == candidate["manifest"]["sha256"]
            manifest = register_candidate(candidate)
            listed = list_registered()
            assert len(listed) == 1 and listed[0]["id"] == manifest["id"]
            loaded, loaded_source, path = _load_registered(manifest["id"])
            assert loaded_source == source and loaded["sha256"] == manifest["sha256"]
            record_use(path, verified=True, elapsed=0.125)
            assert _read_json(path / "usage.json")["verified_success"] == 1
            (path / "tool.py").write_text("改変", encoding="utf-8")
            assert list_registered() == []
            assert (Path(temporary) / "退役" / manifest["id"] / VERSION).is_dir()
    finally:
        if prior is None: os.environ.pop("KERNEL_TSUIKA_DIR", None)
        else: os.environ["KERNEL_TSUIKA_DIR"] = prior


def _sandbox_test():
    source = "def run(args, inputs):\n return {'result': sum(inputs['values']), 'effects': []}\ndef tameshi():\n return [{'args':{},'inputs':{'values':[2,3]},'expected':{'result':5,'effects':[]}}]"
    tested = run_isolated(source, None, None, tests=True)
    ran = run_isolated(source, {}, {"values": [7, 8]})
    if tested.get("ok") is not True or tested.get("cases") != 1 or ran != {"result": 15, "effects": []}:
        raise TsuikaError("sandbox-exec の試験結果が違います")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        _self_test(); print("tsuika: ok")
    elif sys.argv[1:] == ["--sandbox-test"]:
        _sandbox_test(); print("tsuika sandbox: ok")
