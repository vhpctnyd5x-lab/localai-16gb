#!/usr/bin/env python3
"""server.py の、画面から使う新しい入口だけをモデル無しで検査する。"""

from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import server  # noqa: E402


class ServerApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old_dir, self.old_db, self.old_examples, self.old_ready = (
            server.chats.DIR, server.chats.DB, server.chats.TITLE_EXAMPLES, server.chats._READY,
        )
        self.old_seiri_oboe = server.chats.SEIRI_OBOE
        self.old_settings = server.CTX.get("設定")
        server.CTX["設定"] = {"モード": "試験", "会話の長さ": 8}
        server.chats.DIR = str(root / "legacy")
        server.chats.DB = str(root / "chats.sqlite3")
        server.chats.TITLE_EXAMPLES = str(root / "title_examples.json")
        server.chats.SEIRI_OBOE = str(root / "seiri_oboe.json")
        server.chats._READY = False
        self.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        server.chats.DIR, server.chats.DB, server.chats.TITLE_EXAMPLES, server.chats._READY = (
            self.old_dir, self.old_db, self.old_examples, self.old_ready,
        )
        server.chats.SEIRI_OBOE = self.old_seiri_oboe
        server.CTX["設定"] = self.old_settings
        self.tmp.cleanup()

    def post(self, path, body):
        request = Request(
            self.base + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Token": server.TOKEN},
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_chat_delete_and_restore_uses_sqlite(self):
        created = self.post("/chat/new", {})
        cid = created["会話"]
        deleted = self.post("/chat/delete", {"id": cid})
        self.assertEqual(deleted, {"ok": True, "取り消せる": True})
        self.assertIsNone(server.chats.load(cid))
        self.assertTrue(self.post("/chat/restore", {"id": cid})["ok"])
        self.assertIsNotNone(server.chats.load(cid))

    def test_seiri_suggests_three_kinds_learns_rejection_and_restores_trash(self):
        now = time.time()

        def conversation(title, messages=2, age_days=0):
            chat = server.chats.create()
            server.chats.rename(chat["id"], title)
            for i in range(messages):
                server.chats.add_turn(chat["id"], "user" if i % 2 == 0 else "bot", f"本文{i}-{title}")
            with server.chats._db() as conn:
                conn.execute("UPDATE conversations SET created=?, updated=? WHERE id=?",
                             (now-age_days*86400, now-age_days*86400, chat["id"]))
            return chat["id"]

        old_trial = conversation("試験: 古い確認", age_days=40)
        old_active = conversation("昔の議事録", messages=4, age_days=40)
        left = conversation("京都旅行の予定", messages=4)
        right = conversation("京都旅行の持ち物", messages=4)
        suggested = self.post("/chat/seiri/an", {})["案"]
        self.assertEqual({x["区分"] for x in suggested}, {"ゴミ箱", "しまう", "組"})
        # しまう候補を外すと覚え、他のチェック済みだけ実行する。
        items = [{**x, "checked": x["id"] != old_active} for x in suggested]
        result = self.post("/chat/seiri/suru", {"案": items})
        self.assertGreaterEqual(result["実行"], 3)
        self.assertNotIn(old_active, {x["id"] for x in self.post("/chat/seiri/an", {})["案"]})
        self.assertTrue(self.post("/chat/restore", {"id": old_trial})["ok"])

    def test_seiri_duplicate_first_message_keeps_newest_and_group_name_is_reused(self):
        first, second = server.chats.create(), server.chats.create()
        for chat in (first, second):
            server.chats.rename(chat["id"], "同じ相談")
            server.chats.add_turn(chat["id"], "user", "同じ最初の発言")
        with server.chats._db() as conn:
            conn.execute("UPDATE conversations SET updated=? WHERE id=?", (time.time()-20, first["id"]))
        ideas = self.post("/chat/seiri/an", {})["案"]
        trash = [x for x in ideas if x["区分"] == "ゴミ箱"]
        self.assertEqual([x["id"] for x in trash], [first["id"]])
        server.chats.remove(first["id"])
        self.assertTrue(self.post("/chat/restore", {"id": first["id"]})["ok"])

        a, b = server.chats.create(), server.chats.create()
        for chat, title in ((a, "星空写真の整理"), (b, "星空写真の共有")):
            server.chats.rename(chat["id"], title)
            server.chats.add_turn(chat["id"], "user", title)
        group_ideas = [x for x in self.post("/chat/seiri/an", {})["案"] if x["区分"] == "組"]
        selected_name = next(x["組"] for x in group_ideas if x["id"] == a["id"])
        self.post("/chat/seiri/suru", {"案": [{**x, "checked": x["id"] == a["id"]} for x in group_ideas]})
        c, d = server.chats.create(), server.chats.create()
        for chat, title in ((c, f"{selected_name}の追加案"), (d, f"{selected_name}を共有")):
            server.chats.rename(chat["id"], title)
            server.chats.add_turn(chat["id"], "user", title)
        reused = [x for x in self.post("/chat/seiri/an", {})["案"] if x["区分"] == "組" and x["id"] in {c["id"], d["id"]}]
        self.assertEqual({x["組"] for x in reused}, {selected_name})

    def test_model_title_strips_empty_think_block(self):
        """10/1 本番: --reasoning-format none で「<think> </think> デスク」が題名になった。"""
        import io, json as _json, unittest.mock as um
        chat = server.chats.create()
        server.chats.add_turn(chat["id"], "user", "えっと、デスクトップにあるフォルダの数を教えて")
        server.chats.add_turn(chat["id"], "bot", "3つです")
        replies = [io.BytesIO(_json.dumps([{"is_processing": False}]).encode()),
                   io.BytesIO(_json.dumps({"choices": [{"message": {"content": "<think>\n\n</think>\n\nデスクトップのフォルダ数"}}]}).encode())]
        def fake_urlopen(*_a, **_k):
            body = replies.pop(0)
            body.__enter__ = lambda self=body: self
            body.__exit__ = lambda *a: False
            return body
        with um.patch("time.sleep"), um.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            server._make_title(chat["id"])
        self.assertEqual(server.chats.load(chat["id"])["題"], "デスクトップのフォルダ数")

    def test_screen_only_new_chat_creates_no_database_row(self):
        empty = server.chats.create()
        with server.chats._db() as conn:   # 10分より前に作られた空の会話にする（作った直後は消さない）
            conn.execute("UPDATE conversations SET created = created - 900 WHERE id = ?", (empty["id"],))
        result = self.post("/chat/new", {"画面だけ": True})
        self.assertEqual(result, {"ok": True, "会話": None})
        self.assertIsNone(server.chats.load(empty["id"]))
        self.assertEqual(server.chats.listing(), [])

    def test_pick_file_returns_the_native_choice(self):
        selected = Path(self.tmp.name) / "選んだ.txt"
        selected.write_text("ok", encoding="utf-8")
        old_run = server.subprocess.run
        server.subprocess.run = lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=str(selected) + "\n", stderr=""
        )
        try:
            result = self.post("/pick-file", {})
        finally:
            server.subprocess.run = old_run
        self.assertEqual(result["パス"], str(selected))
        self.assertEqual(result["名"], "選んだ.txt")

    def test_client_disconnect_marks_the_streamed_answer_stopped_and_saves_it(self):
        old_handler = server.handle_text_nagashi
        old_queue_title = server._queue_title
        server._queue_title = lambda _cid: None

        def fake_handler(text, queue, stop, michi=None, rireki=None):
            # 切断を検知するまで何度か書く。Handler が BrokenPipe を受け取ると
            # stop が立ち、下の回答が履歴へ保存される。
            import teachers
            teachers.mado_settei(tomeru=stop)
            try:
                for _ in range(200):
                    if stop.is_set():
                        break
                    queue.put({"文字": "x"})
                    time.sleep(0.01)
                return {
                    "出力": "（ここで止めた）" if stop.is_set() else "完了",
                    "経過": "", "ミリ秒": 0, "モード": "試験", "止めた": stop.is_set(),
                }
            finally:
                teachers.mado_settei(None, None)

        server.handle_text_nagashi = fake_handler
        try:
            host, port = "127.0.0.1", self.httpd.server_address[1]
            conn = http.client.HTTPConnection(host, port, timeout=3)
            body = json.dumps({"text": "止める試験"}).encode("utf-8")
            conn.request("POST", "/ask/stream", body=body, headers={
                "Content-Type": "application/json", "X-Token": server.TOKEN,
            })
            response = conn.getresponse()
            # 最初の会話 ID を受け取ってから接続を切る。
            self.assertIn("会話", json.loads(response.readline().decode("utf-8")))
            response.close()
            conn.close()

            deadline = time.time() + 4
            saved = None
            while time.time() < deadline:
                listed = server.chats.listing()
                if listed:
                    saved = server.chats.load(listed[0]["id"])
                    if saved and len(saved["やりとり"]) == 2:
                        break
                time.sleep(0.02)
            self.assertIsNotNone(saved)
            self.assertEqual(saved["やりとり"][1]["文"], "（ここで止めた）")
        finally:
            server.handle_text_nagashi = old_handler
            server._queue_title = old_queue_title


if __name__ == "__main__":
    unittest.main()
