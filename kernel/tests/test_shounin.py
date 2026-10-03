import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shounin


class ZenbuTest(unittest.TestCase):
    """10/3: 「全部」は聞いた危険度以下・10分まで。戻せない操作は毎回聞く。"""

    def setUp(self):
        shounin.hajimeru()
        self.asked = []
        shounin.TOIKAKE = lambda message: self.asked.append(message) or shounin.kotaeru(message["承認"]["id"], "やめる")

    def tearDown(self):
        shounin.TOIKAKE = None
        shounin.owaru()

    def test_scope(self):
        shounin._zenbu_ireru("戻せる")
        self.assertTrue(shounin.kiku("移す", risk="戻せる"))
        self.assertTrue(shounin.kiku("読む", risk="見る"))
        self.assertFalse(shounin.kiku("送る", risk="戻せない"))
        self.assertFalse(shounin.kiku("何か", risk=None))
        self.assertEqual(len(self.asked), 2)

    def test_irreversible_is_once(self):
        shounin._zenbu_ireru("戻せない")
        self.assertFalse(shounin.kiku("送る", risk="戻せない"))

    def test_expires(self):
        shounin._zenbu_ireru("戻せる")
        shounin._ZENBU.kigen = time.time() - 1
        self.assertFalse(shounin.kiku("移す", risk="戻せる"))


if __name__ == "__main__":
    unittest.main()


class TopicDriftTest(unittest.TestCase):
    """10/3: 事前学習が名前の似た記事を辿って偏った（前田裕二→前田亘輝→前田たかひろ）。"""

    def test_too_close(self):
        import gakushuu
        near = ["前田裕二", "ムシウタ"]
        self.assertTrue(gakushuu._too_close("前田亘輝", near))
        self.assertTrue(gakushuu._too_close("ムシウタbug", near))
        self.assertFalse(gakushuu._too_close("岩井恭平", near))
