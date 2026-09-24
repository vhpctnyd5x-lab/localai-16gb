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
        self.old_dir, self.old_db, self.old_ready = (
            server.chats.DIR, server.chats.DB, server.chats._READY,
        )
        server.chats.DIR = str(root / "legacy")
        server.chats.DB = str(root / "chats.sqlite3")
        server.chats._READY = False
        self.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        server.chats.DIR, server.chats.DB, server.chats._READY = (
            self.old_dir, self.old_db, self.old_ready,
        )
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

        def fake_handler(text, queue, stop):
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


if __name__ == "__main__":
    unittest.main()
