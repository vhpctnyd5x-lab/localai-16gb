#!/usr/bin/env python3
"""30Bを起動せずに輪の境界を試す。"""
import json
import io
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
    assert len(captured[0]["tools"]) == 13 and captured[0]["max_tokens"] == 128
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
    assert "指定されたフォルダ" in jiyuu._system() and "findでホーム以下" in jiyuu._system()
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
                db.execute("INSERT INTO chishiki VALUES (?,?,?,?,?)", (f"星{number}", "星の話" * 100, "Wikipedia", "https://example.org", "今日"))
        got = jiyuu._run("shiru", {"query": "星"}, "見る", "test")["結果"]
        assert len(got) == 3 and all(len(row["本文"]) <= 300 for row in got)
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
    # 9/29: 道具が止められた後に答えの文が空なら「完了」と言わず、止められたことを伝える。
    replies = iter([{"content": "", "tool_calls": [call("sh", command="sudo ls")]}, {"content": "", "tool_calls": []}])
    with mock.patch.object(jiyuu, "_ask", side_effect=lambda *a, **k: next(replies)):
        said = jiyuu.kotaeru("試験", mode="自動")
    assert said.startswith("終わりまでできませんでした") and "禁止" in said, said
    # 9/30: 対話の python は承認を聞かずに、write への道を返す。
    seen = conversation([call("sh", command="python")])
    assert "write" in seen[1][-1]["content"] and "承認" not in seen[1][-1]["content"], seen[1][-1]
    checks += 1
    print(f"jiyuu 自己試験: {checks}/{checks} PASS")
