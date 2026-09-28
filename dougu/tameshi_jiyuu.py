#!/usr/bin/env python3
"""30Bを起動せずに輪の境界を試す。"""
import json
import io
import os
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
    captured = []
    def fake_urlopen(request, timeout):
        captured.append(json.loads(request.data))
        return io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')
    with mock.patch.object(jiyuu.urllib.request, "urlopen", side_effect=fake_urlopen):
        assert jiyuu._ask([{"role": "system", "content": jiyuu.SYSTEM}], thinking=True)["content"] == "ok"
    assert captured[0]["cache_prompt"] is True
    assert captured[0]["chat_template_kwargs"]["enable_thinking"] is True
    assert len(captured[0]["tools"]) == 9 and captured[0]["max_tokens"] == 128
    checks += 1
    preview = jiyuu._short({"ok": True, "結果": "A" * 6000}, "long", 1)
    archive = Path(preview.split("全文: ", 1)[1].split(" …", 1)[0])
    assert len(preview) <= 1200 and "A" * 6000 in archive.read_text(encoding="utf-8")
    checks += 1
    def call(name, **args):
        return {"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
    def conversation(calls, mode="自動"):
        replies = iter([{"content": "", "tool_calls": calls}, {"content": "完了"}])
        seen = []
        def ask(messages, thinking=False, final=False):
            seen.append(json.loads(json.dumps(messages)))
            return next(replies)
        with mock.patch.object(jiyuu, "_ask", side_effect=ask):
            assert jiyuu.kotaeru("試験", mode=mode) == "完了"
        return seen

    target = home / "memo.txt"
    seen = conversation([call("write", path=str(target), content="一行")])
    assert target.read_text() == "一行"
    assert seen[1][-2]["role"] == "assistant" and seen[1][-1]["role"] == "tool"
    checks += 1

    # 指定フォルダを保ち、見つからない時はホームから再探索する手を返す。
    assert "フォルダまで含めて" in jiyuu._system() and "findでホーム以下" in jiyuu._system()
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

    logs = list((Path(temporary) / "kiroku").glob("jiyuu_*.jsonl"))
    assert logs and '"輪":"jiyuu"' in logs[0].read_text() and '"経路":"試験"' in logs[0].read_text()
    checks += 1
    print(f"jiyuu 自己試験: {checks}/{checks} PASS")
