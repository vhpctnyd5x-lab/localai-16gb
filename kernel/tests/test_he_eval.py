#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "LocalAI改良/tools/ops/humaneval"))
import he_eval


class HumanEvalTests(unittest.TestCase):
    def _problem(self, task_id="HumanEval/0"):
        return {
            "task_id": task_id,
            "prompt": "def add(a, b):\n    \"\"\"add\"\"\"\n",
            "entry_point": "add",
            "test": "def check(candidate):\n    assert candidate(2, 3) == 5\n",
        }

    def test_missing_generation_stays_in_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data.jsonl"
            gen = root / "gen.jsonl"
            data.write_text(json.dumps(self._problem()) + "\n" +
                            json.dumps(self._problem("HumanEval/1")) + "\n",
                            encoding="utf-8")
            gen.write_text(json.dumps({
                "task_id": "HumanEval/0",
                "raw": "```python\ndef add(a, b):\n    return a+b\n```",
            }) + "\n", encoding="utf-8")
            summary, rows = he_eval.evaluate(
                data, gen, timeout=3, memory_mb=256, output_mb=1,
                sandbox=False)
            self.assertEqual(summary["data_n"], 2)
            self.assertEqual(summary["pass"], 1)
            self.assertEqual(summary["missing_generation_n"], 1)
            self.assertEqual(summary["accuracy_over_data"], 0.5)
            self.assertEqual(rows[1]["why"], "missing_generation")

    def test_timeout_is_reported(self):
        problem = self._problem()
        generation = {"task_id": problem["task_id"],
                      "raw": "```python\ndef add(a,b):\n    while True: pass\n```"}
        result = he_eval.run_case(problem, generation, timeout=0.2,
                                  memory_mb=256, output_mb=1, sandbox=False)
        self.assertFalse(result["pass"])
        self.assertEqual(result["why"], "timeout")


if __name__ == "__main__":
    unittest.main()
