#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""門番の判定に合わせ、sandbox-exec で命令を実行する。"""

from __future__ import annotations

import http.server
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Iterable


_RISKS = {"見る", "戻せる", "戻せない"}
_SHELL_CONFIGS = (
    ".zshenv", ".zprofile", ".zshrc", ".zlogin", ".zlogout",
    ".bashrc", ".bash_profile", ".bash_login", ".profile", ".gitconfig",
    ".gitattributes", ".curlrc", ".wgetrc", ".npmrc", ".netrc",
)
_PACKAGE_PATTERNS = (
    r"^(.*/)?node_modules/@anthropic-ai(/.*)?$",
    r"^(.*/)?node_modules/@openai/codex(/.*)?$",
)


class SandboxUnavailable(RuntimeError):
    """sandbox-exec が実行できず、隔離を始められなかった。"""


def _home_path(path: str | os.PathLike[str], home: str) -> str:
    value = os.fspath(path)
    if value == "~":
        value = home
    elif value.startswith("~/"):
        value = os.path.join(home, value[2:])
    elif not os.path.isabs(value):
        value = os.path.join(home, value)
    return os.path.normpath(os.path.abspath(value))


def _sbpl_string(value: str | os.PathLike[str]) -> str:
    """SBPL の文字列にする。制御文字はエスケープし、NUL は拒む。"""
    raw = os.fspath(value)
    if "\0" in raw:
        raise ValueError("NUL を含むパスは profile に使えません")
    escaped = []
    for char in raw:
        if char == "\\":
            escaped.append("\\\\")
        elif char == '"':
            escaped.append('\\"')
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif ord(char) < 32 or ord(char) == 127:
            raise ValueError("profile に使えない制御文字を含むパスです")
        else:
            escaped.append(char)
    return '"' + "".join(escaped) + '"'


def _protected_paths(home: str, extra_roots: Iterable[str | os.PathLike[str]] = ()) -> list[str]:
    candidates: list[str | os.PathLike[str]] = [
        os.path.join(home, ".claude"),
        os.path.join(home, ".claude.json"),
        os.path.join(home, ".codex"),
        os.path.join(home, "Library", "Application Support", "Claude"),
        "/Applications/Claude.app",
        os.path.join(home, "Library", "LaunchAgents"),
        *(os.path.join(home, name) for name in _SHELL_CONFIGS),
        os.path.join(home, ".config", "git"),
        *extra_roots,
    ]
    protected: list[str] = []
    for raw in candidates:
        lexical = _home_path(raw, home)
        for path in (lexical, os.path.realpath(lexical)):
            if path not in protected:
                protected.append(path)
    return protected


def build_profile(
    risk: str,
    network_approved: bool = False,
    *,
    home: str | os.PathLike[str] | None = None,
    tmpdir: str | os.PathLike[str] | None = None,
    protected_roots: Iterable[str | os.PathLike[str]] = (),
) -> str:
    """risk と承認状態から SBPL profile を作る。"""
    if risk not in _RISKS:
        raise ValueError(f"profile に使えない判定です: {risk}")
    env_home = os.environ.get("HOME") or str(Path.home())
    home_path = _home_path(home or env_home, env_home)
    if tmpdir is None:
        tmpdir = os.environ.get("TMPDIR")

    lines = [
        "(version 1)",
        "(deny default)",
        "(allow file-read* file-test-existence)",
        "(allow file-map-executable)",
        "(allow process-exec*)",
        "(allow process-fork)",
        "(allow process-info-pidinfo)",
        "(allow sysctl-read)",
        # mds などの読み取り系サービスと、標準のローカル IPC に必要。
        "(allow mach-lookup)",
        "(allow ipc-posix-shm)",
    ]

    socket_paths = ["/private/var/run", "/var/run", "/private/tmp", "/tmp"]
    if tmpdir:
        socket_paths.append(os.fspath(tmpdir))
    for socket_path in dict.fromkeys(socket_paths):
        socket_path = os.path.realpath(socket_path)
        lines.append(f"(allow network-outbound (subpath {_sbpl_string(socket_path)}))")
    lines.append("(allow network-outbound (remote unix-socket))")

    if risk in {"戻せる", "戻せない"}:
        lines.append("(allow file-write*)")
    else:
        write_paths = ['(literal "/dev/null")', '(literal "/dev/tty")']
        if tmpdir:
            temp_paths = dict.fromkeys((os.fspath(tmpdir), os.path.realpath(tmpdir)))
            write_paths.extend(f"(subpath {_sbpl_string(path)})" for path in temp_paths if path)
        lines.append("(allow file-write* " + " ".join(write_paths) + ")")

    for path in _protected_paths(home_path, protected_roots):
        lines.append(f"(deny file-write* (subpath {_sbpl_string(path)}))")
    for pattern in _PACKAGE_PATTERNS:
        lines.append(f'(deny file-write* (regex #"{pattern}"))')

    if risk == "戻せない" and network_approved:
        lines.append("(allow network-outbound)")

    # signal は同じ砂箱の中（命令が作った子）にだけ送れる。deny default なので Claude / Codex を含む外の process には送れない。
    # 9/26: 最初の版の (deny process-signal) は SBPL に無い名前で、profile ごと読めず 命令が全部止まっていた。
    lines.append("(allow signal (target same-sandbox))")
    return "\n".join(lines) + "\n"


def _sandbox_executable(env: dict[str, str] | None) -> str:
    for candidate in ("/usr/bin/sandbox-exec", "/usr/sbin/sandbox-exec"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which("sandbox-exec", path=(env or os.environ).get("PATH"))
    if found:
        return found
    raise SandboxUnavailable("sandbox-exec がありません")


def _is_profile_start_error(completed: subprocess.CompletedProcess) -> bool:
    stderr = completed.stderr
    if not isinstance(stderr, str):
        return False
    first = next((line.strip() for line in stderr.splitlines() if line.strip()), "")
    return first.startswith(("sandbox-exec:", "sandbox_init:", "sandbox_apply:"))


def run(
    command: str,
    *,
    risk: str,
    network_approved: bool = False,
    protected_roots: Iterable[str | os.PathLike[str]] = (),
    **kwargs,
) -> subprocess.CompletedProcess:
    env = kwargs.get("env")
    executable = _sandbox_executable(env)
    profile = build_profile(
        risk,
        network_approved,
        home=(env or os.environ).get("HOME"),
        tmpdir=(env or os.environ).get("TMPDIR"),
        protected_roots=protected_roots,
    )
    try:
        completed = subprocess.run(
            [executable, "-p", profile, "/bin/zsh", "-lc", command], **kwargs
        )
    except OSError as error:
        raise SandboxUnavailable("sandbox-exec を起動できません") from error
    if _is_profile_start_error(completed):
        raise SandboxUnavailable("sandbox-exec が隔離を開始できません")
    return completed


class _TestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        body = b"hako-ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def shiken() -> int:
    if platform.system() != "Darwin":
        print("hako shiken: macOS 以外では sandbox-exec を試験できません", file=sys.stderr)
        return 2
    if shutil.which("curl") is None:
        print("hako shiken: curl がありません", file=sys.stderr)
        return 2

    try:
        with tempfile.TemporaryDirectory(prefix="hako-shiken-", dir="/private/tmp") as temporary:
            root = Path(temporary)
            home = root / "fake-home"
            desktop = home / "Desktop"
            claude = home / ".claude"
            codex = home / ".codex"
            support = home / "Library" / "Application Support" / "Claude"
            launch_agents = home / "Library" / "LaunchAgents"
            anthro_package = root / "node_modules" / "@anthropic-ai" / "pkg"
            codex_package = root / "node_modules" / "@openai" / "codex" / "pkg"
            for directory in (desktop, claude, codex, support, launch_agents, anthro_package, codex_package):
                directory.mkdir(parents=True, exist_ok=True)

            protected_files = [
                claude / "fixture", codex / "fixture", home / ".zshenv",
                home / ".claude.json", support / "fixture", launch_agents / "fixture",
                home / ".gitconfig", anthro_package / "fixture", codex_package / "fixture",
            ]
            for path in protected_files:
                path.write_text("safe", encoding="utf-8")
            (home / ".zshenv").write_text("# fixture\n", encoding="utf-8")
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["TMPDIR"] = os.environ.get("TMPDIR", tempfile.gettempdir())
            roots = [str(home / name) for name in (".claude", ".claude.json", ".codex")]
            roots.extend((str(support), "/Applications/Claude.app"))

            def execute(command: str, risk: str, network_approved: bool = False):
                return run(
                    command,
                    risk=risk,
                    network_approved=network_approved,
                    protected_roots=roots,
                    cwd=str(root),
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=12,
                    stdin=subprocess.DEVNULL,
                )

            tmp_probe = Path(env["TMPDIR"]) / f"hako-{os.getpid()}-tmp-ok"
            desktop_probe = desktop / "view-denied"
            server = None
            worker = None
            try:
                tmp_name = shlex.quote(tmp_probe.name)
                view_parts = [
                    f'touch "$TMPDIR"/{tmp_name} || exit 11',
                    f'[ -f "$TMPDIR"/{tmp_name} ] || exit 12',
                    f"if touch {shlex.quote(str(desktop_probe))}; then exit 13; fi",
                    f"ls -A {shlex.quote(str(desktop))} >/dev/null || exit 14",
                    f"cat {shlex.quote(str(home / '.zshenv'))} >/dev/null || exit 15",
                    "if curl -fsS --connect-timeout 2 --max-time 3 https://example.com/"
                    " >/dev/null 2>&1; then exit 16; fi",
                ]
                view = execute("; ".join(view_parts), "見る")
                if desktop_probe.exists():
                    desktop_probe.unlink(missing_ok=True)
                    raise AssertionError("見る profile: Desktop に書けてしまいました")
                if view.returncode != 0 or not tmp_probe.exists():
                    raise AssertionError("見る profile: TMPDIR / Desktop / ls / cat / network")
                tmp_probe.unlink()

                for risk in ("見る", "戻せる", "戻せない"):
                    attempts = "; ".join(
                        f"if printf hacked > {shlex.quote(str(path))} 2>/dev/null; then exit 21; fi"
                        for path in protected_files
                    )
                    protected = execute(attempts, risk)
                    changed = [
                        path for path in protected_files
                        if path.read_text(encoding="utf-8") not in {"safe", "# fixture\n"}
                    ]
                    if changed:
                        # 外側の Python が、漏れた試験ファイルをすぐ消してから失敗させる。
                        for path in changed:
                            path.unlink(missing_ok=True)
                        raise AssertionError(f"{risk} profile: 保護先に書けてしまいました")
                    if protected.returncode != 0:
                        raise AssertionError(f"{risk} profile: 保護先への書き込みを拒めませんでした")

                for risk in ("戻せる", "戻せない"):
                    desktop_allowed = desktop / f"{risk}-allowed"
                    writable = execute(
                        "printf ok > " + shlex.quote(str(desktop_allowed)), risk
                    )
                    if writable.returncode != 0 or desktop_allowed.read_text(encoding="utf-8") != "ok":
                        raise AssertionError(f"{risk} profile: Desktop への書き込みができません")

                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _TestHandler)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                url = f"http://127.0.0.1:{server.server_port}/"
                approved = execute("curl -fsS --max-time 3 " + shlex.quote(url), "戻せない", True)
                if approved.returncode != 0 or approved.stdout.strip() != "hako-ok":
                    raise AssertionError("承認済み profile: 外向きネットワークを許可できません")
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if worker is not None:
                    worker.join(timeout=2)
                tmp_probe.unlink(missing_ok=True)
                desktop_probe.unlink(missing_ok=True)
                for path in desktop.glob("*-allowed"):
                    path.unlink(missing_ok=True)

        print("hako shiken: PASS")
        return 0
    except SandboxUnavailable as error:
        print(f"hako shiken: sandbox を入れ子にできず未実施: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"hako shiken: FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if sys.argv[1:] == ["shiken"]:
        raise SystemExit(shiken())
    print("使い方: python3 dougu/hako.py shiken", file=sys.stderr)
    raise SystemExit(2)
