#!/usr/bin/env python3
"""題名の短縮・手直し例・空会話の保存規則。"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import chats  # noqa: E402


class ChatTitleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old = chats.DIR, chats.DB, chats.TITLE_EXAMPLES, chats._READY
        chats.DIR = str(root / "legacy")
        chats.DB = str(root / "chats.sqlite3")
        chats.TITLE_EXAMPLES = str(root / "title_examples.json")
        chats._READY = False

    def tearDown(self):
        chats.DIR, chats.DB, chats.TITLE_EXAMPLES, chats._READY = self.old
        self.tmp.cleanup()

    def test_fallback_title_removes_leading_fillers_and_limits_to_twenty(self):
        title = chats.fallback_title("えっと、まあ、あのー 明日の会議の資料を作ってください。余分な説明")
        self.assertTrue(title.startswith("明日の会議の資料を作ってください"))
        self.assertLessEqual(len(chats.fallback_title("あの " + "長い題名" * 10)), 20)
        voice = "えっと、まあ、今日もお願いします。えっと、なんだっけ、J16 の書き間違いを直して"
        self.assertEqual(chats.fallback_title(voice), "今日もお願いします")
        self.assertEqual(chats.fallback_title("なんだっけ、あの、チャットの整理を作って"), "チャットの整理を作って")

    def test_rename_saves_recent_ten_examples_and_they_are_retrievable(self):
        for i in range(12):
            chat = chats.create()
            chats.add_turn(chat["id"], "user", "最初の発言 %d" % i)
            chats.rename(chat["id"], "手直し題名 %d" % i)
        examples = chats.title_examples(20)
        self.assertEqual(len(examples), 10)
        self.assertEqual(examples[0]["発言"], "最初の発言 2")
        self.assertEqual(examples[-1]["題"], "手直し題名 11")
        self.assertEqual(len(json.loads(Path(chats.TITLE_EXAMPLES).read_text())), 10)

    def test_generated_title_only_replaces_default_after_first_exchange(self):
        empty = chats.create()
        self.assertEqual(chats.set_generated_title(empty["id"], "先走り題名"), False)
        self.assertNotIn(empty["id"], [x["id"] for x in chats.listing()])  # 一覧には出さない
        self.assertIsNotNone(chats.load(empty["id"]))  # 作った直後は消さない（最初の発言の前に一覧が呼ばれても）
        chats.purge_empty(older_than=0)
        self.assertIsNone(chats.load(empty["id"]))

        chat = chats.create()
        chats.add_turn(chat["id"], "user", "相談内容")
        chats.add_turn(chat["id"], "bot", "回答")
        self.assertTrue(chats.set_generated_title(chat["id"], "短い題名"))
        self.assertFalse(chats.needs_generated_title(chat["id"]))
        chats.rename(chat["id"], "本人の題名")
        self.assertFalse(chats.set_generated_title(chat["id"], "自動題名"))
        self.assertEqual(chats.load(chat["id"])["題"], "本人の題名")

        another = chats.create()
        chats.add_turn(another["id"], "user", "別の相談")
        chats.add_turn(another["id"], "bot", "返事")
        chats.rename(another["id"], "新しい会話")
        self.assertFalse(chats.set_generated_title(another["id"], "自動題名"))

    def test_listing_purges_empty_conversations_but_keeps_spoken_ones(self):
        empty = chats.create()
        active = chats.create()
        chats.add_turn(active["id"], "user", "発言あり")
        self.assertEqual([x["id"] for x in chats.listing()], [active["id"]])
        chats.purge_empty(older_than=0)
        self.assertIsNone(chats.load(empty["id"]))
        self.assertIsNotNone(chats.load(active["id"]))


if __name__ == "__main__":
    unittest.main()
