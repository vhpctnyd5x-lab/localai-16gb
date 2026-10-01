#!/usr/bin/env python3
"""会話整理案のローカル生成・検証・実行。"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import chats  # noqa: E402


class _Response:
    def __init__(self, data):
        self.data = json.dumps(data, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.data


class ChatSeiriTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old = chats.DIR, chats.DB, chats.TITLE_EXAMPLES, chats.SEIRI_OBOE, chats._READY
        chats.DIR = str(root / "legacy")
        chats.DB = str(root / "chats.sqlite3")
        chats.TITLE_EXAMPLES = str(root / "title_examples.json")
        chats.SEIRI_OBOE = str(root / "seiri_oboe.json")
        chats._READY = False

    def tearDown(self):
        chats.DIR, chats.DB, chats.TITLE_EXAMPLES, chats.SEIRI_OBOE, chats._READY = self.old
        self.tmp.cleanup()

    def _chat(self, title, first, updated=None):
        conversation = chats.create(title)
        chats.add_turn(conversation["id"], "user", first)
        if updated is not None:
            with chats._db() as conn:
                conn.execute("UPDATE conversations SET updated=? WHERE id=?", (updated, conversation["id"]))
        return chats.load(conversation["id"])

    def test_qwen_json_is_read_after_think_tag_and_code_fence(self):
        payload = {"choices": [{"message": {"content": '<think>考え中</think>```json\n{"組":[],"ゴミ箱":[],"しまう":[]}\n```'}}]}
        with patch("urllib.request.urlopen", side_effect=[_Response([]), _Response(payload)]):
            answer = chats._ask_seiri_qwen([])
        self.assertEqual(answer, {"組": [], "ゴミ箱": [], "しまう": []})

    def test_broken_json_returns_none(self):
        payload = {"choices": [{"message": {"content": '```json\n{"組": ['}}]}
        with patch("urllib.request.urlopen", side_effect=[_Response([]), _Response(payload)]):
            self.assertIsNone(chats._ask_seiri_qwen([]))

    def test_nonexistent_ids_are_ignored_and_recent_chat_cannot_be_trashed(self):
        old = self._chat("古い会話", "内容", chats._now() - 9 * 86400)
        recent = self._chat("最近の会話", "別の内容")
        answer = {"組": [], "ゴミ箱": [
            {"id": "not-real", "理由": "存在しない"}, {"id": recent["id"], "理由": "最近"},
            {"id": old["id"], "理由": "不要"}], "しまう": []}
        proposals = chats._seiri_qwen_proposals([old, recent], answer)
        self.assertEqual([x["id"] for x in proposals], [old["id"]])
        self.assertEqual(proposals[0]["出どころ"], "Qwen3.6")

    def test_recent_chat_is_not_archived_by_qwen(self):
        recent = self._chat("今の作業", "続きをお願い", updated=chats._now() - 86400)
        old = self._chat("前の作業", "もう終わった", updated=chats._now() - 5 * 86400)
        answer = {"組": [], "ゴミ箱": [], "しまう": [{"id": recent["id"], "理由": "短い"}, {"id": old["id"], "理由": "終わった"}]}
        with patch.object(chats, "_ask_seiri_qwen", return_value=answer):
            proposals = [p for p in chats.seiri_an() if p.get("出どころ") == "Qwen3.6"]
        self.assertEqual([(p["id"], p["区分"]) for p in proposals], [(old["id"], "しまう")])

    def test_archived_chat_is_not_archived_again(self):
        done = self._chat("終わった作業", "もう済んだ", updated=chats._now() - 9 * 86400)
        chats.archive(done["id"], True)
        answer = {"組": [], "ゴミ箱": [], "しまう": [{"id": done["id"], "理由": "既にしまった"}]}
        with patch.object(chats, "_ask_seiri_qwen", return_value=answer):
            self.assertFalse([p for p in chats.seiri_an() if p.get("出どころ") == "Qwen3.6"])

    def test_timeout_falls_back_to_rules_only(self):
        chat = self._chat("試験: 古い会話", "古い試験", chats._now() - 8 * 86400)
        with patch.object(chats, "_ask_seiri_qwen", return_value=None):
            proposals = chats.seiri_an()
        self.assertEqual([(p["id"], p["区分"], p["出どころ"]) for p in proposals],
                         [(chat["id"], "ゴミ箱", "規則")])

    def test_qwen_group_name_reuses_existing_name_and_limits_fields(self):
        first = self._chat("旅の計画", "旅の計画を相談")
        second = self._chat("旅の荷物", "旅の荷物を相談")
        existing = self._chat("既存", "既存会話")
        chats.set_group(existing["id"], "旅行")
        answer = {"組": [{"名": "旅行メモ", "ids": [first["id"], second["id"], "missing"], "理由": "理由" * 30}],
                  "ゴミ箱": [], "しまう": []}
        proposals = chats._seiri_qwen_proposals([first, second], answer)
        self.assertEqual({p["組"] for p in proposals}, {"旅行"})
        self.assertTrue(all(len(p["理由"]) <= 40 for p in proposals))
        self.assertTrue(all(len(p["組"]) <= 12 for p in proposals))

    def test_rejected_proposal_is_not_shown_again(self):
        chat = self._chat("分類候補", "相談")
        Path(chats.SEIRI_OBOE).write_text(json.dumps({"外した": [{"id": chat["id"], "区分": "しまう"}], "組名": []}))
        answer = {"組": [], "ゴミ箱": [], "しまう": [{"id": chat["id"], "理由": "しまう"}]}
        self.assertEqual(chats._seiri_qwen_proposals([chat], answer), [])

    def test_seiri_suru_executes_remembered_plan_without_calling_qwen_again(self):
        first = self._chat("旅行の計画", "一つ目")
        second = self._chat("旅行の荷物", "二つ目")
        answer = {"組": [{"名": "旅行", "ids": [first["id"], second["id"]], "理由": "近い話"}],
                  "ゴミ箱": [], "しまう": []}
        with patch.object(chats, "_ask_seiri_qwen", return_value=answer):
            proposals = chats.seiri_an()
        with patch.object(chats, "_ask_seiri_qwen", side_effect=AssertionError("再問い合わせした")):
            done = chats.seiri_suru([{**p, "checked": True} for p in proposals])
        self.assertEqual(done, 2)
        self.assertEqual(chats.load(first["id"])["組"], "旅行")
        self.assertEqual(chats.load(second["id"])["組"], "旅行")


if __name__ == "__main__":
    unittest.main()
