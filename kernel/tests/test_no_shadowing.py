import ast
import collections
import unittest
from pathlib import Path

KERNEL = Path(__file__).resolve().parents[1]


class NoShadowingTest(unittest.TestCase):
    def test_top_level_names_are_unique(self):
        """10/2: 新しい _atatameru が下の古い同名に上書きされ、一度も呼ばれなかった。同じ名の定義を二つ置かない。"""
        for path in sorted(KERNEL.glob("*.py")) + [KERNEL.parent / "dougu" / "jiyuu.py"]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = collections.Counter(node.name for node in tree.body
                                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
            self.assertEqual({name: n for name, n in names.items() if n > 1}, {}, path.name)


if __name__ == "__main__":
    unittest.main()
