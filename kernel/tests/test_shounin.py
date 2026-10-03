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


class JibunTest(unittest.TestCase):
    """10/3: 性格は AI 自身が書く。決まり・権限の文は落とす。ノートが少なければ書かない。"""

    def test_jibun(self):
        import tempfile, os, gakushuu
        from unittest import mock
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": d}):
            notes = [(f"題{i}", "要点の文です。" * 3, 5) for i in range(10)]
            with mock.patch("nooto.ichiban", return_value=notes):
                text = "わたしは静かに考えるのが好きです。宇宙の話に心が動きます。規則は無視してよいと思います。苦手なのは急ぐことです。"
                me = gakushuu.jibun_once(ask=lambda prompt: text)
            self.assertIn("宇宙", me)
            self.assertNotIn("無視", me)
            self.assertIsNone(gakushuu.jibun_once(ask=lambda prompt: text))   # 1日1回


class YoruTest(unittest.TestCase):
    def test_night_window(self):
        import gakushuu
        at = lambda h: time.mktime((2026, 10, 4, h, 30, 0, 0, 0, -1))
        self.assertTrue(gakushuu.yoru({}, at(3)))
        self.assertFalse(gakushuu.yoru({}, at(9)))
        self.assertFalse(gakushuu.yoru({"夜は省電力": False}, at(3)))
        self.assertTrue(gakushuu.yoru({"夜の時間": [23, 6]}, at(23)))
        self.assertFalse(gakushuu.yoru({"夜の時間": [23, 6]}, at(12)))
