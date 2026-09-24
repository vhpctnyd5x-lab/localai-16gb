#!/usr/bin/env python3
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import public_bench as pb


class Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self.body


def success_result(content="A", error=None):
    return {
        "content": content, "reasoning_chars": 0, "elapsed_sec": 0.01,
        "timings": {}, "usage": None, "model": "test", "error": error,
        "error_type": "test" if error else None, "http_status": 500 if error else 200,
        "error_body": "failure" if error else "", "attempts": [], "retry_count": 0,
        "prompt_hash": "hash",
    }


class PublicBenchTests(unittest.TestCase):
    def test_balanced_sample_is_exact_and_stable(self):
        rows = [{"id": str(i), "domain": domain}
                for i, domain in enumerate("aaabbbcccc")]
        first = pb.balanced_sample(rows, "domain", 7, 123,
                                   lambda row: row["id"])
        second = pb.balanced_sample(list(reversed(rows)), "domain", 7, 123,
                                    lambda row: row["id"])
        self.assertEqual([x["id"] for x in first], [x["id"] for x in second])
        self.assertEqual(len(first), 7)
        counts = {domain: sum(x["domain"] == domain for x in first)
                  for domain in "abc"}
        self.assertEqual(sum(counts.values()), 7)
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)

    def test_client_retries_and_records_http_body(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    request.full_url, 500, "server", {}, io.BytesIO(b"overloaded"))
            return Response(200, b'{"choices":[{"message":{"content":"A"}}]}')

        client = pb.LocalClient("http://example.test/v1/chat/completions", False,
                                8, 1, retries=2, retry_backoff=0, opener=opener)
        result = client.call("question", "item-1")
        self.assertEqual(result["content"], "A")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(result["attempts"][0]["status"], 500)
        self.assertEqual(result["attempts"][0]["body_excerpt"], "overloaded")
        self.assertIsNone(result["error"])

    def test_client_does_not_repeat_reasoning_only_truncation(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            return Response(
                200,
                b'{"choices":[{"finish_reason":"length","message":'
                b'{"content":"","reasoning_content":"long thought"}}]}',
            )

        client = pb.LocalClient("http://example.test/v1/chat/completions", True,
                                8, 1, retries=3, retry_backoff=0, opener=opener)
        result = client.call("question", "item-1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["error_type"], "OutputTruncatedError")
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["reasoning_chars"], len("long thought"))

    def test_adaptive_client_votes_and_assigns_max_profile_to_aime(self):
        class FakeClient:
            seed = 100

            def __init__(self):
                self.calls = []

            def call(self, prompt, item_id, **kwargs):
                self.calls.append((prompt, item_id, kwargs))
                answers = {"sample-1": "7", "sample-2": "8", "sample-3": "7"}
                content = next((value for key, value in answers.items()
                                if key in item_id), "7")
                return {
                    "content": content, "error": None, "error_type": None,
                    "http_status": 200, "error_body": "", "attempts": [],
                    "retry_count": 0, "elapsed_sec": 0.01, "timings": {},
                    "usage": None, "model": "test", "reasoning_chars": 10,
                    "request": kwargs,
                }

        profiles = {
            "fixed": pb.RequestProfile("fixed", False, 8, 1),
            "fast": pb.RequestProfile("fast", False, 8, 1),
            "deep": pb.RequestProfile("deep", True, 16, 2),
            "max": pb.RequestProfile("max", True, 32, 3),
        }
        fake = FakeClient()
        client = pb.AdaptiveClient(
            fake, "aime", "adaptive", profiles, pb.extract_integer,
            samples=3, sample_temperature=0.35,
        )
        result = client.call("Solve this problem", "aime/1")
        self.assertEqual(result["winner"], "7")
        self.assertEqual(result["vote_counts"], {"7": 2, "8": 1})
        self.assertEqual(result["profile"], "max")
        self.assertEqual(result["request_count"], 3)
        self.assertTrue(all(call[2]["think"] for call in fake.calls))
        self.assertTrue(all(call[2]["max_tokens"] == 32 for call in fake.calls))

    def test_adaptive_client_retries_fast_when_answer_format_is_invalid(self):
        class FakeClient:
            seed = 0

            def __init__(self):
                self.calls = []

            def call(self, prompt, item_id, **kwargs):
                self.calls.append((item_id, kwargs))
                content = "not an answer" if "fallback" not in item_id else "B"
                return {
                    "content": content, "error": None, "error_type": None,
                    "http_status": 200, "error_body": "", "attempts": [],
                    "retry_count": 0, "elapsed_sec": 0.01, "timings": {},
                    "usage": None, "model": "test", "reasoning_chars": 0,
                    "request": kwargs,
                }

        profiles = {
            "fixed": pb.RequestProfile("fixed", False, 8, 1),
            "fast": pb.RequestProfile("fast", False, 8, 1),
            "deep": pb.RequestProfile("deep", True, 16, 2),
        }
        profiles["max"] = pb.RequestProfile("max", True, 32, 3)
        fake = FakeClient()
        client = pb.AdaptiveClient(
            fake, "mmlu_pro", "adaptive", profiles,
            lambda text: pb.extract_letter(text, "ABCD"),
        )
        result = client.call("Choose one", "mmlu/1")
        self.assertEqual(result["content"], "B")
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[-1][1]["think"], False)
        self.assertEqual(fake.calls[-1][1]["max_tokens"], 264)

    def test_max_client_rescues_reasoning_only_response_with_fast_call(self):
        class FakeClient:
            seed = 0

            def __init__(self):
                self.calls = []

            def call(self, prompt, item_id, **kwargs):
                self.calls.append((item_id, kwargs))
                if "fallback-fast" not in item_id:
                    return {
                        "item_id": item_id, "content": "", "error": "cut",
                        "error_type": "OutputTruncatedError", "elapsed_sec": 1,
                        "timings": {}, "request": kwargs,
                    }
                return {
                    "item_id": item_id, "content": "C", "error": None,
                    "error_type": None, "elapsed_sec": 0.1, "timings": {},
                    "request": kwargs,
                }

        profiles = {
            "fixed": pb.RequestProfile("fixed", False, 8, 1),
            "fast": pb.RequestProfile("fast", False, 8, 1),
            "deep": pb.RequestProfile("deep", True, 16, 2),
            "max": pb.RequestProfile("max", True, 32, 3),
        }
        fake = FakeClient()
        client = pb.AdaptiveClient(
            fake, "gpqa_diamond", "max", profiles,
            lambda text: pb.extract_letter(text, "ABCD"),
        )
        result = client.call("Choose one", "gpqa/1")
        self.assertEqual(result["content"], "C")
        self.assertTrue(result["fallback_used"])
        self.assertEqual([kwargs["think"] for _, kwargs in fake.calls], [True, False])

    def test_corrupt_cache_is_quarantined_and_refetched(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            cache = out / "datasets" / "x__c__test.jsonl"
            cache.parent.mkdir()
            cache.write_text('{broken\n', encoding="utf-8")
            with mock.patch.object(pb, "get_json", return_value={
                "num_rows_total": 1, "rows": [{"row": {"id": 1}}]
            }):
                rows = pb.fetch_rows("x", "c", "test", out)
            self.assertEqual(rows, [{"id": 1}])
            self.assertTrue(list(cache.parent.glob(cache.name + ".corrupt-*")))
            self.assertEqual(pb.read_jsonl(cache), [{"id": 1}])

    def test_run_rows_retries_failed_existing_item_only(self):
        class FakeClient:
            def __init__(self, result):
                self.result = result
                self.calls = []

            def call(self, prompt, item_id):
                self.calls.append(item_id)
                return dict(self.result)

        rows = [{"id": "one", "answer": "A"}, {"id": "two", "answer": "A"}]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            first_client = FakeClient(success_result("", "HTTPError"))
            first = pb.run_rows("toy", rows, lambda row: row["id"],
                                lambda content: content or None, first_client, out,
                                lambda row: row["id"], gold_fn=lambda row: "A")
            self.assertEqual(first["failed_n"], 2)
            self.assertEqual(first_client.calls, ["one", "two"])

            second_client = FakeClient(success_result("A"))
            second = pb.run_rows("toy", rows, lambda row: row["id"],
                                 lambda content: content, second_client, out,
                                 lambda row: row["id"], gold_fn=lambda row: "A")
            self.assertEqual(second["failed_n"], 0)
            self.assertEqual(second["correct"], 2)
            self.assertEqual(second_client.calls, ["one", "two"])

            items = pb.read_jsonl(out / "toy.jsonl")
            self.assertEqual(len(items), 2)
            self.assertTrue(all(item["row_sha256"] for item in items))

    def test_atomic_jsonl_is_valid_after_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            pb.jsonl_dump(path, [{"x": 1}, {"x": 2}])
            self.assertEqual(pb.read_jsonl(path), [{"x": 1}, {"x": 2}])
            self.assertFalse(list(Path(directory).glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
