#!/usr/bin/env python3
"""事前学習とスキル API の、ネット・30B を使わない自己試験。"""
import json
import fcntl
import importlib.util
import os
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kernel"))


def check(value, message):
    if not value:
        raise AssertionError(message)


with tempfile.TemporaryDirectory(prefix="tameshi_gakushuu_") as temporary:
    base = Path(temporary)
    os.environ["KERNEL_GAKUSHUU_DIR"] = str(base / "gakushuu")
    os.environ["KERNEL_SKILLS_DIR"] = str(base / "skills")
    os.environ["KERNEL_KIROKU_DIR"] = str(base / "kiroku")
    os.environ["KERNEL_TRASH_DIR"] = str(base / "trash")
    os.environ["KERNEL_CHATS_DB"] = str(base / "chats.sqlite3")
    import gakushuu
    import settings

    settings.PATH = str(base / "settings.json")
    cfg = settings.load()
    cfg["事前学習"] = gakushuu.validate(cfg["事前学習"], {"入": True, "充電中だけ": False})
    settings.save(cfg)

    class FakeWiki:
        calls = 0
        topics = []

        @classmethod
        def ask(cls, title, chars=5000):
            cls.calls += 1
            cls.topics.append(title)
            return {"題": "試験記事", "本文": "試験記事の本文。調べたい言葉が入る。", "url": "https://example.invalid/wiki/test",
                    "ほかの候補": ["候補題一", "候補題二", "候補題三", "候補題四", "候補題五", "候補題六",
                                   "A(説明)", "一覧の項目", "曖昧さ回避", "1999年の出来事", "あ"]}

    check(gakushuu.learn_once(cfg, wiki_module=FakeWiki), "記事を追加")
    check(FakeWiki.topics[0] in gakushuu.LEARN_SEEDS and FakeWiki.topics[0] != "あ", "最初の題は学習種から選ぶ")
    queued = gakushuu._state()["次の題"]
    check([x["題"] for x in queued] == ["候補題一", "候補題二", "候補題三", "候補題四", "候補題五"],
          "リンク候補は条件で絞って5題まで")
    check(all(x["深さ"] == 1 for x in queued), "リンク題に深さを記録")
    with sqlite3.connect(gakushuu.folder() / "chishiki.sqlite3") as db:
        check(db.execute("SELECT count(*) FROM chishiki WHERE chishiki MATCH '試験記事'").fetchone()[0] == 1, "FTS5 検索")
    check(not gakushuu.learn_once(cfg, wiki_module=FakeWiki), "同じ記事を入れない")
    check(gakushuu.overview(cfg)["数"]["記事"] == 1, "記事数")

    class DepthWiki:
        calls = 0
        topics = []

        @classmethod
        def ask(cls, title, chars=5000):
            cls.calls += 1
            cls.topics.append(title)
            links = ["二段目候補"] if cls.calls == 2 else ["候補題一", "候補題二", "候補題三", "候補題四", "候補題五"]
            return {"題": f"深さ記事{cls.calls}", "本文": "深さ確認の記事本文。", "ほかの候補": links}

    gakushuu._write(gakushuu.folder() / "state.json", {"版": gakushuu.STATE_VERSION, "次の題": []})
    check(gakushuu.learn_once(cfg, wiki_module=DepthWiki), "種記事からリンクを追加")
    check(gakushuu.learn_once(cfg, wiki_module=DepthWiki), "深さ1の記事を学習")
    check("二段目候補" not in [x["題"] for x in gakushuu._state()["次の題"]], "深さ1からリンクを広げない")
    old = {"版": gakushuu.STATE_VERSION - 1, "次の題": [{"題": "ゆめりあ", "深さ": 1}]}
    check(gakushuu._topic(old, set(), False) == gakushuu.LEARN_SEEDS[0], "旧版の次の題を捨てる")
    check(gakushuu._version_state({"版": 1, "見た記録": ["x.jsonl:1"]})["見た記録"] == [], "旧版の見た記録を捨てる")
    plain = [x for x in gakushuu.LEARN_SEEDS if "(" not in x]
    check(gakushuu._topic({"版": gakushuu.STATE_VERSION, "見た題": plain}, set(), False) == "ファイル (コンピュータ)",
          "括弧つきの種も学ぶ")
    check(gakushuu._valid_title("二字") and not gakushuu._valid_title("あ")
          and not gakushuu._valid_title("題 (説明)") and not gakushuu._valid_title("一覧")
          and not gakushuu._valid_title("曖昧さ回避") and not gakushuu._valid_title("2024年の出来事"), "題の除外条件")
    check(not gakushuu._valid_title("コンピュータゲーム") and not gakushuu._valid_title("コンピュータRPG")
          and gakushuu._valid_title("パーソナルコンピュータ"), "遊び・芸能の題を外す")

    low = {**cfg, "事前学習": {**cfg["事前学習"], "上限MB": 0}}
    before = FakeWiki.calls
    check(not gakushuu.learn_once(low, wiki_module=FakeWiki) and FakeWiki.calls == before, "上限で停止")

    original_charging = gakushuu.charging
    gakushuu.charging = lambda: False
    charge_cfg = {**cfg, "事前学習": {**cfg["事前学習"], "充電中だけ": True}}
    check(not gakushuu.learn_once(charge_cfg, wiki_module=FakeWiki) and FakeWiki.calls == before, "非充電で休む")
    gakushuu.charging = original_charging

    busy = gakushuu.folder() / "busy"
    busy.write_text("test", encoding="ascii")
    check(not gakushuu.learn_once(cfg, wiki_module=FakeWiki) and FakeWiki.calls == before, "会話中に休む")
    busy.unlink()

    logdir = base / "kiroku"
    logdir.mkdir()
    (logdir / "slow.jsonl").write_text(
        json.dumps({"段階": "開始", "内容": {"依頼": "遅い頼み"}}, ensure_ascii=False) + "\n"
        + json.dumps({"段階": "結果", "内容": {"ok": True, "ミリ秒": 45000}}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    check(any(r["題"] == "遅い頼み" for r in gakushuu._records()), "遅い記録を読む")

    check(not gakushuu.DEFAULT["振り返りで外の先生に聞く"] and not gakushuu.DEFAULT["会話の言葉から学ぶ題を選ぶ"], "外部送信は既定で切")
    check(gakushuu._topic({"次の題": []}, set(), False) != "会話だけの題", "会話題を既定で使わない")
    check(gakushuu.validate(cfg["事前学習"], {"振り返りで外の先生に聞く": True})["振り返りで外の先生に聞く"], "送信設定")
    (base / "skills" / "容量.md").parent.mkdir(parents=True, exist_ok=True)
    (base / "skills" / "容量.md").write_text(gakushuu._skill_text("容量", "試験", False, "カーネル", "増量"), encoding="utf-8")
    check(gakushuu.used_bytes() >= (base / "skills" / "容量.md").stat().st_size, "提案スキルも容量に算入")
    (base / "skills" / "容量.md").unlink()
    log = gakushuu.folder() / "log.jsonl"
    log.write_bytes(b"x" * (5 * 1024 * 1024))
    gakushuu._log("回した後")
    check(log.stat().st_size < 1024 and log.with_suffix(".jsonl.1").exists(), "log は5MBで回す")
    log.write_text("".join(json.dumps({"文": str(i)}) + "\n" for i in range(30)), encoding="utf-8")
    check(gakushuu.overview(cfg)["記録"] == [str(i) for i in range(10, 30)], "記録は尻の20行")
    lock_path = gakushuu.folder() / "worker.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gakushuu.run()
        check(not (gakushuu.folder() / "worker.pid").exists(), "二重起動を止める")
        fcntl.flock(lock, fcntl.LOCK_UN)

    gakushuu._records = lambda: [{"題": "試験の失敗", "文": "失敗した操作", "識別": "record-1"}]
    sent = []
    def teacher(question, config, timeout=60):
        sent.append(question)
        return {"答え": "手順を確認し、小さく試してから進める。", "error": None}
    check(not gakushuu.reflect_once(cfg, ask=lambda *a, **k: (_ for _ in ()).throw(AssertionError("外へ送った")), network=True), "先生オフなら振り返りを休む")
    state = gakushuu._state()
    check("record-1" not in state.get("見た記録", []), "休止中は記録を消費しない")
    check("外の先生が切なので休み" in (gakushuu.folder() / "log.jsonl").read_text(encoding="utf-8"), "休止を記録に書く")
    log_text = (gakushuu.folder() / "log.jsonl").read_text(encoding="utf-8")
    check("失敗" not in log_text, "休止時に失敗をログへ書かない")
    gakushuu.reflect_once(cfg, ask=lambda *a, **k: (_ for _ in ()).throw(AssertionError("外へ送った")), network=True)
    check((gakushuu.folder() / "log.jsonl").read_text(encoding="utf-8").count("外の先生が切") == 1,
          "休止は1回だけ記録する")
    gakushuu._write(gakushuu.folder() / "state.json", {})
    cfg["事前学習"]["振り返りで外の先生に聞く"] = True
    check(gakushuu.reflect_once(cfg, ask=teacher, network=True), "先生の技提案")
    check("失敗した操作" not in sent[0] and "試験の失敗" in sent[0], "先生へ記録本文を送らない")
    proposed = [s for s in gakushuu.skills() if s["made_by"] == "カーネル"]
    check(len(proposed) == 1 and proposed[0]["on"] is False, "提案はオフ")
    check(not gakushuu.reflect_once(cfg, ask=teacher, network=True), "1時間に1つ")

    spec = importlib.util.spec_from_file_location("kernel_server_test", ROOT / "kernel" / "server.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    server.CTX["設定"] = cfg
    original_popen = server.subprocess.Popen

    class FakeProcess:
        stopped = False

        def poll(self):
            return 0 if self.stopped else None

        def terminate(self):
            self.stopped = True

        def wait(self, timeout=None):
            return 0

    fake_process = FakeProcess()
    server.subprocess.Popen = lambda *args, **kwargs: fake_process
    try:
        orphan = gakushuu.folder() / "worker.pid"
        orphan.write_text("987654", encoding="ascii")
        signals = []
        def fake_kill(pid, sig):
            signals.append((pid, sig))
            if sig == 0:
                raise ProcessLookupError()
        with mock.patch.object(server.subprocess, "run", return_value=type("Result", (), {"stdout": str(ROOT / "kernel" / "gakushuu.py")})()), mock.patch.object(server.os, "kill", side_effect=fake_kill):
            server._gakushuu_process(True)
        check(any(sig == server.signal.SIGTERM for _, sig in signals), "孤児の学び手を停止")
        orphan.unlink()
        check(server._GAKUSHUU_PROCESS is fake_process, "学習 process 起動")
        server._gakushuu_process(False)
        check(server._GAKUSHUU_PROCESS is None and fake_process.stopped, "学習 process 停止")
    finally:
        server.subprocess.Popen = original_popen

    httpd = server.Server(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"

    def request(path, payload=None, token=True):
        headers = {"Origin": url}
        if token:
            headers["X-Token"] = server.TOKEN
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url + path, data=data, headers=headers,
                                     method="GET" if payload is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    try:
        code, _ = request("/skills", token=False)
        check(code == 403, "GET の token")
        code, _ = request("/skills", {"動き": "保存", "name": "../bad", "description": "bad", "body": "bad"})
        check(code == 400, "名前の検査")
        code, result = request("/skills", {"動き": "保存", "name": "私の技", "description": "手順", "body": "一歩ずつ", "on": True})
        check(code == 200 and any(s["name"] == "私の技" for s in result["スキル"]), "保存")
        code, result = request("/skills", {"動き": "切替", "name": "私の技", "on": False})
        check(code == 200 and next(s for s in result["スキル"] if s["name"] == "私の技")["on"] is False, "切替")
        code, result = request("/skills", {"動き": "ゴミ箱", "name": "私の技"})
        check(code == 200 and (base / "trash" / "私の技.md").exists(), "ゴミ箱")
        code, result = request("/gakushuu")
        check(code == 200 and result["数"]["記事"] == 3, "事前学習 GET")
        code, result = request("/gakushuu", {"入": False, "上限MB": 4})
        check(code == 200 and result["入"] is False and settings.load()["事前学習"]["上限MB"] == 4,
              "事前学習 POST と保存")
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=3)

print("OK: FTS5・重複・容量・充電・会話休止・技提案・skills API・gakushuu API")
