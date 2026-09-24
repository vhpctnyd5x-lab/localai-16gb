#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""再開可能で監査可能な公開ベンチマーク実行器。

外部ライブラリなしで、HF の公開データまたはキャッシュを固定し、
OpenAI 互換の llama-server に問題を送る。回答・試行履歴・データハッシュ・
実行条件を保存するため、通信失敗からの再開と後からの検証ができる。

例::

  python3 kernel/public_bench.py --bench mmlu --mmlu-per-category 10
  python3 kernel/public_bench.py --bench gpqa --gpqa-limit 50
  python3 kernel/public_bench.py --bench aime humaneval --out-dir /tmp/run

Qwen3.5 では ``--think`` を付けない限り
``chat_template_kwargs.enable_thinking=false`` を送る。``/no_think`` を
プロンプトへ追加する方式ではない。
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


HARNESS_VERSION = "2.1.0"
USER_AGENT = f"LocalAI-public-bench/{HARNESS_VERSION}"
HF_ROWS = "https://datasets-server.huggingface.co/rows?"
DEFAULT_URL = "http://127.0.0.1:8080/v1/chat/completions"
MMLU_LETTERS = "ABCDEFGHIJ"
RETRYABLE_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}
DATA_FETCH_RETRIES = 3


class OutputTruncatedError(ValueError):
    """思考だけでmax_tokensを使い切り、可視回答が無い応答。"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_obj(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write(path: Path, data: str) -> None:
    """同一ファイルシステム上の一時ファイルから原子的に置き換える。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                     dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def json_dump(path: Path, obj: Any) -> None:
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def jsonl_dump(path: Path, rows: Iterable[dict]) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    atomic_write(path, text)


def _quarantine(path: Path, reason: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.name}.corrupt-{stamp}-{os.getpid()}")
    os.replace(path, dest)
    print(f"  cache quarantine: {path.name} -> {dest.name} ({reason})",
          file=sys.stderr, flush=True)
    return dest


def read_jsonl(path: Path, *, quarantine: bool = False,
               strict: bool = False) -> list[dict]:
    """JSONLを読む。キャッシュの破損は退避して再取得できる。"""
    try:
        rows = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line, strict=strict))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"line {number}: {exc}") from exc
        return rows
    except Exception as exc:
        if quarantine and path.exists():
            _quarantine(path, str(exc))
            return []
        raise


def _download(url: str, timeout: int = 120,
              retries: int = DATA_FETCH_RETRIES) -> bytes:
    """データ取得にも限定リトライを適用し、最終失敗の本文を残す。"""
    last_error = None
    for attempt in range(1, retries + 2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            body = _response_body(exc)
            last_error = RuntimeError(
                f"HTTP {exc.code} for {redact_url(url)}: {body[:512]}")
            retryable = exc.code in RETRYABLE_HTTP_STATUS
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = RuntimeError(f"{type(exc).__name__} for {redact_url(url)}: {exc}")
            retryable = True
        if attempt <= retries and retryable:
            time.sleep(0.5 * (2 ** (attempt - 1)))
            continue
        raise last_error
    raise RuntimeError("unreachable")


def get_json(url: str, timeout: int = 120):
    return json.loads(_download(url, timeout).decode("utf-8"))


def _cache_rows(cache: Path) -> list[dict] | None:
    if not cache.exists():
        return None
    try:
        return read_jsonl(cache, strict=False)
    except Exception as exc:
        _quarantine(cache, str(exc))
        return None


def _safe_cache_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def fetch_rows(dataset: str, config: str, split: str, out: Path,
               limit: int = 0) -> list[dict]:
    """HF rows APIから取得し、破損キャッシュだけを退避して再取得する。"""
    key = _safe_cache_name(f"{dataset}__{config}__{split}")
    cache = out / "datasets" / f"{key}.jsonl"
    cached = _cache_rows(cache)
    if cached is not None:
        return cached[:limit] if limit else cached

    rows: list[dict] = []
    offset = 0
    page = 100
    total = None
    while total is None or offset < total:
        length = min(page, limit - offset) if limit else page
        if length <= 0:
            break
        query = urllib.parse.urlencode({
            "dataset": dataset, "config": config, "split": split,
            "offset": offset, "length": length,
        })
        data = get_json(HF_ROWS + query)
        total = int(data.get("num_rows_total", len(rows)))
        batch = [x["row"] for x in data.get("rows", [])]
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
        print(f"  dataset {dataset}: {offset}/{total}", flush=True)
        if len(batch) < length:
            break
    jsonl_dump(cache, rows)
    return rows[:limit] if limit else rows


def fetch_url_jsonl(url: str, out: Path, name: str) -> list[dict]:
    cache = out / "datasets" / name
    cached = _cache_rows(cache)
    if cached is not None:
        return cached
    text = _download(url, 120).decode("utf-8")
    # 公開データにC1制御文字が混ざる場合があるため strict=False。
    rows = [json.loads(line, strict=False) for line in text.splitlines()
            if line.strip()]
    jsonl_dump(cache, rows)
    return rows


def fetch_hf_parquet(repo: str, filename: str, out: Path, name: str) -> list[dict]:
    """Hugging Face Parquetを取得する（キャッシュ破損時は再取得）。"""
    cache = out / "datasets" / name
    cached = _cache_rows(cache)
    if cached is not None:
        return cached
    try:
        from huggingface_hub import hf_hub_download
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet読み込みには huggingface_hub と pyarrow が必要です"
        ) from exc
    local = hf_hub_download(repo, filename, repo_type="dataset",
                            local_dir=str(out / "hf"))
    rows = pq.read_table(local).to_pylist()
    jsonl_dump(cache, rows)
    return rows


def _row_key(row: dict, id_fn: Callable[[dict], str] | None = None) -> str:
    if id_fn is not None:
        return str(id_fn(row))
    return sha256_obj(row)


def _validate_unique_ids(rows: list[dict], id_fn: Callable[[dict], str]) -> None:
    ids = [str(id_fn(row)) for row in rows]
    if len(ids) != len(set(ids)):
        duplicate = next(value for value, count in collections.Counter(ids).items()
                         if count > 1)
        raise ValueError(f"duplicate row id: {duplicate}")


def stratified(rows: list[dict], field: str, per_group: int, seed: int,
               id_fn: Callable[[dict], str] | None = None) -> list[dict]:
    """各グループから同数を、入力順に依存せず決定的に選ぶ。"""
    if not per_group:
        return list(rows)
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        groups[str(row.get(field, ""))].append(row)
    picked: list[dict] = []
    for group in sorted(groups):
        xs = sorted(groups[group], key=lambda x: _row_key(x, id_fn))
        rng = random.Random(f"{seed}:{field}:{group}")
        chosen = rng.sample(xs, min(per_group, len(xs)))
        picked.extend(sorted(chosen, key=lambda x: _row_key(x, id_fn)))
    return picked


def balanced_sample(rows: list[dict], field: str, limit: int, seed: int,
                    id_fn: Callable[[dict], str] | None = None) -> list[dict]:
    """グループ間の差を最大1にして、要求数を必ず満たす。"""
    if not limit or limit >= len(rows):
        return list(rows)
    if limit < 0:
        raise ValueError("limit must be non-negative")
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        groups[str(row.get(field, ""))].append(row)
    names = sorted(groups)
    quotas = {name: 0 for name in names}
    remaining = min(limit, len(rows))
    while remaining:
        candidates = [name for name in names if quotas[name] < len(groups[name])]
        if not candidates:
            break
        min_quota = min(quotas[name] for name in candidates)
        for name in candidates:
            if remaining <= 0:
                break
            if quotas[name] == min_quota:
                quotas[name] += 1
                remaining -= 1
    picked: list[dict] = []
    for name in names:
        xs = sorted(groups[name], key=lambda x: _row_key(x, id_fn))
        rng = random.Random(f"{seed}:{field}:{name}")
        chosen = rng.sample(xs, quotas[name])
        picked.extend(sorted(chosen, key=lambda x: _row_key(x, id_fn)))
    return picked


def extract_letter(text: str, letters: str) -> str | None:
    if not text:
        return None
    end = letters[-1]
    patterns = [
        rf"(?:answer|答案)\s*(?:is|:|：)?\s*\(?([A-{end}])\)?",
        rf"\\boxed\s*\{{\s*([A-{end}])\s*\}}",
        rf"\b([A-{end}])\b",
    ]
    for pattern in patterns:
        found = re.findall(pattern, text, flags=re.IGNORECASE)
        if found:
            return found[-1].upper()
    return None


def extract_integer(text: str) -> str | None:
    if not text:
        return None
    boxed = re.findall(r"\\boxed\s*\{\s*(\d{1,3})\s*\}", text)
    marked = re.findall(
        r"(?:answer|答案|final)\s*(?:is|:|：)?\s*[^0-9]{0,4}(\d{1,3})\b",
        text, re.IGNORECASE)
    nums = boxed or marked or re.findall(r"\b(\d{1,3})\b", text)
    if not nums:
        return None
    return str(int(nums[-1]))


def mmlu_prompt(row: dict) -> str:
    opts = "\n".join(f"{MMLU_LETTERS[i]}. {x}"
                      for i, x in enumerate(row["options"]))
    return (
        "The following is a multiple-choice question. Do not explain your reasoning. "
        "Return only the answer letter (A-J).\n\n"
        f"Question: {row['question']}\nOptions:\n{opts}\nAnswer:"
    )


def gpqa_prompt(row: dict) -> str:
    return (
        "Answer the following multiple-choice question. Do not explain your reasoning. "
        "Return only the letter A, B, C, or D.\n\n" + row["problem"]
    )


def aime_prompt(problem: str) -> str:
    return (
        "Solve this AIME problem. Do not explain your reasoning. "
        "Return only the final integer answer from 000 to 999.\n\n" + problem
    )


def redact_url(url: str) -> str:
    try:
        p = urllib.parse.urlsplit(url)
        netloc = p.netloc.rsplit("@", 1)[-1]
        return urllib.parse.urlunsplit((p.scheme, netloc, p.path, "", ""))
    except Exception:
        return "<invalid-url>"


def _response_body(exc: urllib.error.HTTPError, limit: int = 4096) -> str:
    try:
        return exc.read(limit).decode("utf-8", errors="replace")[:limit]
    except Exception:
        return ""


class LocalClient:
    """llama-server client with bounded retries and an auditable error trail."""

    def __init__(self, url: str, think: bool, max_tokens: int, timeout: int,
                 retries: int = 3, retry_backoff: float = 0.5,
                 seed: int = 0, opener=None):
        if retries < 0:
            raise ValueError("retries must be non-negative")
        self.url = url
        self.think = think
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.retries = retries
        self.retry_backoff = max(0.0, retry_backoff)
        self.seed = seed
        self.opener = opener or urllib.request.urlopen

    def call(self, prompt: str, item_id: str = "", *,
             think: bool | None = None, max_tokens: int | None = None,
             temperature: float | None = None, seed: int | None = None,
             timeout: int | None = None, retries: int | None = None) -> dict:
        """1回の呼び出しを行う。

        既存の呼び出し互換を保ったまま、適応型ランナーが問題ごとに
        推論モード・生成上限・乱数種・タイムアウトを切り替えられるように
        している。値を省略した場合はコンストラクタの既定値を使う。
        """
        call_think = self.think if think is None else bool(think)
        call_max_tokens = self.max_tokens if max_tokens is None else int(max_tokens)
        call_temperature = (0.0 if temperature is None and not self.think
                            else (temperature if temperature is not None else 0.0))
        call_seed = self.seed if seed is None else int(seed)
        call_timeout = self.timeout if timeout is None else int(timeout)
        call_retries = self.retries if retries is None else int(retries)
        if call_max_tokens <= 0 or call_timeout <= 0 or call_retries < 0:
            raise ValueError("max_tokens and timeout must be positive")
        body = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": call_temperature,
            "top_p": 0.95,
            "max_tokens": call_max_tokens,
            "stream": False,
            "seed": call_seed,
        }
        if not call_think:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        attempts: list[dict] = []
        started = time.monotonic()
        response: dict[str, Any] = {}
        final_error: str | None = None
        final_type: str | None = None
        final_status: int | None = None
        final_body = ""

        for attempt_no in range(1, call_retries + 2):
            attempt_started = time.monotonic()
            status = None
            body_excerpt = ""
            try:
                req = urllib.request.Request(
                    self.url, data=json.dumps(body).encode("utf-8"),
                    headers={"Content-Type": "application/json",
                             "User-Agent": USER_AGENT},
                )
                with self.opener(req, timeout=call_timeout) as r:
                    status = int(r.getcode() or getattr(r, "status", 200))
                    raw = r.read()
                body_excerpt = raw[:4096].decode("utf-8", errors="replace")
                if status >= 400:
                    raise RuntimeError(f"HTTP status {status}")
                response = json.loads(raw.decode("utf-8"))
                choices = response.get("choices") or []
                if not choices or not isinstance(choices[0], dict):
                    raise ValueError("response has no choices")
                message = choices[0].get("message") or {}
                if not isinstance(message, dict):
                    raise ValueError("response message is not an object")
                if not (message.get("content") or "").strip():
                    finish_reason = choices[0].get("finish_reason")
                    if finish_reason in {"length", "max_tokens"} or \
                            (message.get("reasoning_content") or ""):
                        raise OutputTruncatedError(
                            "empty visible answer after reasoning/token limit")
                    raise ValueError("empty model response")
                attempts.append({"attempt": attempt_no, "status": status,
                                 "elapsed_sec": time.monotonic() - attempt_started})
                final_error = None
                final_type = None
                final_status = status
                final_body = ""
                break
            except urllib.error.HTTPError as exc:
                status = exc.code
                body_excerpt = _response_body(exc)
                final_error = f"HTTPError: HTTP Error {exc.code}"
                final_type = "http_error"
                final_status = exc.code
                final_body = body_excerpt
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                final_error = f"{type(exc).__name__}: {exc}"
                final_type = type(exc).__name__
                final_status = status
                final_body = body_excerpt
            except json.JSONDecodeError as exc:
                final_error = f"JSONDecodeError: {exc}"
                final_type = "json_error"
                final_status = status
                final_body = body_excerpt
            except Exception as exc:
                final_error = f"{type(exc).__name__}: {exc}"
                final_type = type(exc).__name__
                final_status = status
                final_body = body_excerpt

            attempts.append({
                "attempt": attempt_no, "status": status,
                "elapsed_sec": time.monotonic() - attempt_started,
                "error": final_error, "body_excerpt": body_excerpt,
            })
            # 5xx/接続失敗だけでなく、200で壊れたJSONを返す一時的な
            # サーバー応答も再試行する。400系の恒久的な入力エラーは除く。
            retryable = (
                status is None
                or status in RETRYABLE_HTTP_STATUS
                or (status < 400 and final_type in {"json_error", "ValueError"})
            )
            if attempt_no <= call_retries and retryable:
                time.sleep(self.retry_backoff * (2 ** (attempt_no - 1)))
                continue
            break

        choices = response.get("choices") or [{}]
        message = choices[0].get("message") or {} if choices else {}
        content = message.get("content", "") or ""
        return {
            "item_id": item_id,
            "prompt_hash": sha256_bytes(prompt.encode("utf-8")),
            "content": content,
            "reasoning_chars": len(message.get("reasoning_content", "") or ""),
            "elapsed_sec": time.monotonic() - started,
            "timings": response.get("timings") or {},
            "usage": response.get("usage"),
            "model": response.get("model"),
            "error": final_error,
            "error_type": final_type,
            "http_status": final_status,
            "error_body": final_body,
            "attempts": attempts,
            "retry_count": max(0, len(attempts) - 1),
            "finish_reason": ((response.get("choices") or [{}])[0].get(
                "finish_reason") if response.get("choices") else None),
            "request": {
                "think": call_think,
                "max_tokens": call_max_tokens,
                "temperature": call_temperature,
                "seed": call_seed,
                "timeout": call_timeout,
                "retries": call_retries,
            },
        }


@dataclass(frozen=True)
class RequestProfile:
    """問題の難度に応じて割り当てる1回分の推論予算。"""

    name: str
    think: bool
    max_tokens: int
    timeout: int
    temperature: float = 0.0


class AdaptiveClient:
    """タスク別予算・自己整合性投票・任意の最終検証を行うクライアント。

    CPU上で「全問を長考」にすると、簡単な問題まで数分単位になり、
    サーバーのキュー詰まりや途中停止が起きやすい。そこで既定の adaptive
    では MMLU/HumanEval を fast、GPQA を deep、AIME を max に割り当てる。
    ``policy=max`` は比較用に全問題を max へ固定する。
    """

    def __init__(self, base: LocalClient, task_name: str, policy: str,
                 profiles: dict[str, RequestProfile],
                 answer_fn: Callable[[str], Any], *, samples: int = 1,
                 sample_temperature: float = 0.35, verify: bool = False,
                 max_requests: int = 0, deadline: float = 0.0,
                 shared_state: dict[str, Any] | None = None):
        if policy not in {"fixed", "adaptive", "max"}:
            raise ValueError(f"unknown policy: {policy}")
        if samples <= 0:
            raise ValueError("samples must be positive")
        if not profiles or "fixed" not in profiles:
            raise ValueError("profiles must include fixed")
        self.base = base
        self.task_name = task_name
        self.policy = policy
        self.profiles = profiles
        self.answer_fn = answer_fn
        self.samples = samples
        self.sample_temperature = max(0.0, float(sample_temperature))
        self.verify = bool(verify)
        self.max_requests = max(0, int(max_requests))
        self.shared_state = shared_state or {"request_count": 0}
        if "deadline" not in self.shared_state:
            self.shared_state["deadline"] = (
                time.monotonic() + deadline if deadline > 0 else 0.0)
        self.deadline = self.shared_state["deadline"]

    def _profile_name(self, prompt: str) -> str:
        if self.policy == "fixed":
            return "fixed"
        if self.policy == "max":
            return "max"
        if self.task_name == "aime":
            return "max"
        if self.task_name == "gpqa_diamond":
            return "deep"
        return "fast"

    def _can_request(self) -> tuple[bool, str | None]:
        if self.max_requests and self.shared_state["request_count"] >= self.max_requests:
            return False, "max_requests_exceeded"
        if self.deadline and time.monotonic() >= self.deadline:
            return False, "max_runtime_exceeded"
        return True, None

    @staticmethod
    def _key(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text.upper() if text else None

    def _parse(self, content: str) -> str | None:
        try:
            return self._key(self.answer_fn(content))
        except Exception:
            return None

    def _call_profile(self, prompt: str, item_id: str,
                      profile: RequestProfile, seed_offset: int = 0) -> dict:
        allowed, reason = self._can_request()
        if not allowed:
            return {
                "content": "", "error": reason, "error_type": reason,
                "http_status": None, "error_body": "", "attempts": [],
                "retry_count": 0, "elapsed_sec": 0.0, "timings": {},
                "usage": None, "model": None,
                "request": {"profile": profile.name},
            }
        self.shared_state["request_count"] += 1
        effective_prompt = prompt
        if profile.think:
            # Qwen3.5 IQ2_Sは背景説明を長く反芻しやすく、上限到達時に
            # 可視回答を失う。思考を切らず、結論を先に出すための短い制約だけを
            # 追加する（ベンチごとの答え形式は元のpromptで保持する）。
            effective_prompt += (
                "\n\nInternal reasoning guidance: stay focused on the given "
                "problem, do not restate general background, and reach the "
                "required final answer before the token limit."
            )
        result = self.base.call(
            effective_prompt, item_id,
            think=profile.think,
            max_tokens=profile.max_tokens,
            temperature=profile.temperature,
            seed=self.base.seed + seed_offset,
            timeout=profile.timeout,
            retries=0 if self.max_requests else None,
        )
        result["profile"] = profile.name
        return result

    def _verification_prompt(self, prompt: str,
                             candidates: list[dict]) -> str:
        drafts = []
        for index, candidate in enumerate(candidates, 1):
            content = str(candidate.get("content") or "").strip()
            if len(content) > 5000:
                content = content[-5000:]
            drafts.append(f"Draft {index}:\n{content or '[no answer]'}")
        if self.task_name == "aime":
            answer_rule = "Return only the final integer answer from 000 to 999."
        elif self.task_name == "gpqa_diamond":
            answer_rule = "Return only one letter: A, B, C, or D."
        else:
            answer_rule = "Return only the required final answer."
        return (
            "Independently verify the problem below. The drafts are fallible and "
            "may all be wrong; recompute the answer when needed. " + answer_rule +
            "\n\nProblem:\n" + prompt + "\n\nDrafts:\n" +
            "\n\n".join(drafts) + "\n\nVerified answer:"
        )

    def call(self, prompt: str, item_id: str = "") -> dict:
        profile_name = self._profile_name(prompt)
        profile = self.profiles[profile_name]
        candidates: list[dict] = []
        sample_count = self.samples
        for index in range(sample_count):
            sample_profile = profile
            if sample_count > 1:
                sample_profile = RequestProfile(
                    profile.name, profile.think, profile.max_tokens,
                    profile.timeout, self.sample_temperature)
            candidates.append(self._call_profile(
                prompt, f"{item_id}::sample-{index + 1}", sample_profile,
                seed_offset=index))

        # 適応型では回答形式の失敗・空応答だけをmaxへ昇格する。
        valid = [x for x in candidates
                 if not x.get("error") and (x.get("content") or "").strip()]
        parsed = [self._parse(x.get("content", ""))
                  if not x.get("error") and (x.get("content") or "").strip()
                  else None for x in candidates]
        need_fallback = not valid or (valid and not any(parsed))
        fallback_name = None
        if self.policy in {"adaptive", "max"} and need_fallback:
            # native thinkingが上限で切れた場合、同じmaxを再送しても同じ
            # 失敗になりやすい。deep/maxからの救済はfast、fastの短答抽出
            # 失敗はfastの生成上限だけ少し増やし、native thinkingへ昇格しない。
            fallback_name = "fast" if profile.name in {"deep", "max"} else "fast"
            fallback_profile = self.profiles[fallback_name]
            if profile.name == "fast":
                fallback_profile = RequestProfile(
                    "fast-retry", False,
                    max(profile.max_tokens * 2, profile.max_tokens + 256),
                    profile.timeout, 0.0)
            fallback = self._call_profile(
                prompt, f"{item_id}::fallback-{fallback_name}",
                fallback_profile,
                seed_offset=sample_count + 1)
            candidates.append(fallback)
            if not fallback.get("error") and (fallback.get("content") or "").strip():
                valid.append(fallback)
                parsed.append(self._parse(fallback.get("content", "")))

        votes = collections.Counter(value for value in parsed if value is not None)
        winner = votes.most_common(1)[0][0] if votes else None
        chosen = next((x for x, value in zip(candidates, parsed)
                       if value == winner and not x.get("error")), None)
        if chosen is None:
            chosen = next((x for x in candidates if not x.get("error")),
                          candidates[0] if candidates else {
                              "content": "", "error": "no_candidate",
                          })

        verification = None
        # 同じモデルを使う検証なので、既定では明示的に --verify した時だけ行う。
        # HumanEvalはコード実行器で検証するため、ここでは二重に呼ばない。
        if self.verify and self.task_name != "humaneval" and valid:
            # 検証は同じモデルの短い独立パスにする。native thinkingを再度
            # 回すと「検証中に上限到達」しやすいため、長考は候補生成側に限定。
            verify_profile = self.profiles.get("fast", self.profiles["max"])
            verification = self._call_profile(
                self._verification_prompt(prompt, valid),
                f"{item_id}::verify", verify_profile, seed_offset=sample_count + 2)
            verified_key = self._parse(verification.get("content", ""))
            if not verification.get("error") and verified_key:
                # 多数票が明確なら、同じモデルの一回の見直しで多数を
                # 上書きしない。候補が1本、同数、または検証が一致した時だけ採用。
                winning_votes = votes.get(winner, 0) if winner else 0
                ambiguous = not winner or winning_votes * 2 <= len(valid)
                accepted = ambiguous or self.samples == 1 or verified_key == winner
                verification["accepted"] = accepted
                verification["verified_key"] = verified_key
                if accepted:
                    chosen = verification
                    winner = verified_key

        result = dict(chosen)
        selected_elapsed = float(result.get("elapsed_sec", 0) or 0)
        total_elapsed = sum(float(x.get("elapsed_sec", 0) or 0)
                            for x in candidates)
        if verification:
            total_elapsed += float(verification.get("elapsed_sec", 0) or 0)
        result.update({
            "strategy": self.policy,
            "profile": result.get("profile", profile.name),
            "winner": winner,
            "vote_counts": dict(votes),
            "request_count": len(candidates) + (1 if verification else 0),
            "selected_elapsed_sec": selected_elapsed,
            "elapsed_sec": total_elapsed,
            "total_reasoning_chars": sum(
                int(x.get("reasoning_chars", 0) or 0) for x in candidates),
            "candidates": [
                {
                    "profile": x.get("profile"),
                    "content": x.get("content", ""),
                    "error": x.get("error"),
                    "pred": self._parse(x.get("content", "")),
                    "elapsed_sec": x.get("elapsed_sec", 0),
                    "reasoning_chars": x.get("reasoning_chars", 0),
                    "request": x.get("request", {}),
                }
                for x in candidates
            ],
            "verification": verification,
            "fallback_used": any(str(x.get("item_id", "")).endswith(
                "::fallback-fast") for x in candidates),
            "fallback_profile": fallback_name,
        })
        return result


def _result_id(item: dict) -> str | None:
    value = item.get("id") or item.get("task_id")
    return str(value) if value is not None else None


def _read_result_map(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    result: dict[str, dict] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            rid = _result_id(item)
            if rid is not None:
                result[rid] = item
        except (ValueError, TypeError) as exc:
            print(f"  ignoring malformed result line {number}: {exc}",
                  file=sys.stderr)
    return result


def _has_success(item: dict | None, expected_hash: str) -> bool:
    if not item or item.get("error"):
        return False
    content = item.get("content") or item.get("raw") or ""
    if not str(content).strip():
        return False
    # 旧ハーネスには行ハッシュがないため、正常な既存回答だけは移行可能にする。
    return not item.get("row_sha256") or item.get("row_sha256") == expected_hash


def _ordered_results(rows: list[dict], id_fn: Callable[[dict], str],
                     result_map: dict[str, dict]) -> list[dict]:
    ordered = []
    known = set()
    for row in rows:
        rid = str(id_fn(row))
        if rid in result_map:
            ordered.append(result_map[rid])
            known.add(rid)
    # 対象外の旧行は捨てずに残すが、集計対象にはしない。
    ordered.extend(item for rid, item in result_map.items() if rid not in known)
    return ordered


def _mmlu_gold(row: dict) -> str | None:
    answer = row.get("answer")
    if isinstance(answer, int):
        return MMLU_LETTERS[answer] if 0 <= answer < len(MMLU_LETTERS) else None
    return extract_letter(str(answer or ""), MMLU_LETTERS)


def _gpqa_gold(row: dict) -> str | None:
    return extract_letter(str(row.get("solution") or row.get("answer") or ""), "ABCD")


def _aime_gold(row: dict) -> str | None:
    return extract_integer(str(row.get("answer", "")))


def run_rows(name: str, rows: list[dict], prompt_fn: Callable[[dict], str],
             answer_fn: Callable[[str], Any], client: LocalClient, out: Path,
             id_fn: Callable[[dict], str], limit_note: str = "",
             gold_fn: Callable[[dict], Any] | None = None,
             include_row: bool = True, manifest_path: str | None = None) -> dict:
    """問題を実行する。成功済みだけをスキップし、失敗済みは再試行する。"""
    _validate_unique_ids(rows, id_fn)
    path = out / f"{name}.jsonl"
    result_map = _read_result_map(path)
    expected = {str(id_fn(row)): sha256_obj(row) for row in rows}
    legacy_ids = {
        str(id_fn(row)) for row in rows
        if result_map.get(str(id_fn(row)))
        and not result_map[str(id_fn(row))].get("row_sha256")
        and _has_success(result_map[str(id_fn(row))], expected[str(id_fn(row))])
    }
    # 旧形式の正常回答は再生成せず、ハッシュと監査用の既定値だけ付けて移行する。
    for rid in legacy_ids:
        item = dict(result_map[rid])
        item.update({
            "harness_version": HARNESS_VERSION,
            "row_sha256": expected[rid],
            "legacy_migrated": True,
            "error_type": item.get("error_type"),
            "http_status": item.get("http_status"),
            "error_body": item.get("error_body", ""),
            "attempts": item.get("attempts") or [],
            "retry_count": item.get("retry_count", 0),
        })
        result_map[rid] = item
    todo = [row for row in rows
            if not _has_success(result_map.get(str(id_fn(row))),
                                expected[str(id_fn(row))])]
    legacy = len(legacy_ids)
    print(f"{name}: {len(rows)}問 / 既存成功 {len(rows)-len(todo)}"
          f"（旧形式 {legacy}）/ 再試行 {len(todo)} {limit_note}", flush=True)

    for index, row in enumerate(todo, 1):
        rid = str(id_fn(row))
        row_hash = expected[rid]
        try:
            prompt = prompt_fn(row)
            result = client.call(prompt, rid)
            pred = answer_fn(result.get("content", ""))
            if gold_fn is not None:
                gold = gold_fn(row)
            elif name.startswith("mmlu"):
                gold = _mmlu_gold(row)
            elif name.startswith("gpqa"):
                gold = _gpqa_gold(row)
            elif name.startswith("aime"):
                gold = _aime_gold(row)
            else:
                gold = None
            complete = not result.get("error") and bool((result.get("content") or "").strip())
            correct = (bool(complete and gold is not None and pred == gold)
                       if gold is not None and complete else None)
            item = {
                "id": rid,
                "row_sha256": row_hash,
                "gold": gold,
                "pred": pred,
                "correct": correct,
                "content": result.get("content", ""),
                "reasoning_chars": result.get("reasoning_chars", 0),
                "elapsed_sec": result.get("elapsed_sec", 0),
                "timings": result.get("timings") or {},
                "usage": result.get("usage"),
                "model": result.get("model"),
                "error": result.get("error"),
                "error_type": result.get("error_type"),
                "http_status": result.get("http_status"),
                "error_body": result.get("error_body", ""),
                "attempts": result.get("attempts") or [],
                "retry_count": result.get("retry_count", 0),
                "prompt_hash": result.get("prompt_hash"),
            }
            # 適応型ランナーの監査情報。固定クライアントでは空欄のまま。
            for key in ("strategy", "profile", "winner", "vote_counts",
                        "request_count", "candidates", "verification",
                        "fallback_used", "selected_elapsed_sec",
                        "fallback_profile", "total_reasoning_chars", "request"):
                if key in result:
                    item[key] = result[key]
        except Exception as exc:
            item = {
                "id": rid, "row_sha256": row_hash, "gold": None, "pred": None,
                "correct": None, "content": "", "reasoning_chars": 0,
                "elapsed_sec": 0.0, "timings": {}, "usage": None,
                "error": f"harness: {type(exc).__name__}: {exc}",
                "error_type": "harness", "http_status": None, "error_body": "",
                "attempts": [], "retry_count": 0, "prompt_hash": None,
            }
        if include_row:
            item["row"] = row
        result_map[rid] = item
        # 1行ずつ原子的にチェックポイント化する。
        jsonl_dump(path, _ordered_results(rows, id_fn, result_map))
        if index == 1 or index % 10 == 0 or index == len(todo):
            print(f"  {index}/{len(todo)}  {float(item.get('elapsed_sec', 0)):.1f}s"
                  f"  pred={item.get('pred')!r}"
                  f"  error={item.get('error') or '-'}", flush=True)

    # 既存成功だけで todo が空でも、現行形式へ整列・原子的に正規化する。
    jsonl_dump(path, _ordered_results(rows, id_fn, result_map))
    failures = []
    all_items = []
    for row in rows:
        rid = str(id_fn(row))
        item = result_map.get(rid)
        all_items.append(item)
        if not item or not _has_success(item, expected[rid]):
            failures.append(item or {"id": rid, "error": "missing_result"})
    scored = [x for x in all_items if x and x.get("correct") is not None]
    total_sec = sum(float((x or {}).get("elapsed_sec", 0) or 0) for x in all_items)
    correct = sum(bool(x.get("correct")) for x in scored)
    tps = [float((x.get("timings") or {}).get("predicted_per_second", 0) or 0)
           for x in all_items if x and (x.get("timings") or {}).get("predicted_per_second")]
    error_counts = collections.Counter(
        str((x or {}).get("error_type") or "missing_result") for x in failures)
    summary = {
        "harness_version": HARNESS_VERSION,
        "name": name,
        "n": len(rows),
        "completed_n": len(rows) - len(failures),
        "failed_n": len(failures),
        "scored_n": len(scored),
        "correct": correct,
        "accuracy": correct / len(scored) if scored else None,
        "sum_generation_sec": total_sec,
        "mean_sec": total_sec / len(rows) if rows else None,
        "mean_predicted_tps": sum(tps) / len(tps) if tps else None,
        "error_counts": dict(error_counts),
        "request_count": sum(int((x or {}).get("request_count", 1) or 1)
                             for x in all_items if x),
        "profile_counts": dict(collections.Counter(
            str((x or {}).get("profile") or "fixed")
            for x in all_items if x)),
        "verification_n": sum(bool((x or {}).get("verification"))
                               for x in all_items if x),
        "fallback_n": sum(bool((x or {}).get("fallback_used"))
                           for x in all_items if x),
        "file": str(path),
        "manifest": manifest_path,
    }
    json_dump(out / f"{name}.summary.json", summary)
    if scored:
        print(f"=> {name}: {correct}/{len(scored)} = {100*summary['accuracy']:.1f}%"
              f"（失敗 {len(failures)}）", flush=True)
    else:
        print(f"=> {name}: score unavailable（失敗 {len(failures)}）", flush=True)
    return summary


def write_dataset_manifest(out: Path, name: str, source_paths: list[Path],
                           all_rows: list[dict], selected_rows: list[dict],
                           id_fn: Callable[[dict], str], selection: dict) -> Path:
    _validate_unique_ids(selected_rows, id_fn)
    def entry(row: dict) -> dict:
        return {"id": str(id_fn(row)), "row_sha256": sha256_obj(row)}

    manifest = {
        "harness_version": HARNESS_VERSION,
        "name": name,
        "created_at": now_iso(),
        "source_files": [
            {"path": str(p), "sha256": sha256_file(p)}
            for p in source_paths if p.exists()
        ],
        "all_n": len(all_rows),
        "all_rows_sha256": sha256_obj([sha256_obj(row) for row in all_rows]),
        "selected_n": len(selected_rows),
        "selected_rows_sha256": sha256_obj([sha256_obj(row) for row in selected_rows]),
        "selection": selection,
        "rows": [entry(row) for row in selected_rows],
    }
    path = out / f"{name}.manifest.json"
    json_dump(path, manifest)
    return path


def human_eval(client: LocalClient, out: Path, data: Path, limit: int,
               manifest_path: str | None = None) -> dict:
    problems = read_jsonl(data)
    if limit:
        problems = problems[:limit]
    return run_rows(
        "humaneval", problems,
        lambda p: (
            "Complete this Python function. Return only the code needed to complete it, "
            "without explanation.\n\n```python\n" + p["prompt"] + "```"
        ),
        lambda content: content, client, out,
        lambda p: str(p.get("task_id") or p.get("id")),
        limit_note="（評価は he_eval.py で全タスクを分母にする）",
        include_row=False, manifest_path=manifest_path,
    )


def _get_json_optional(url: str, timeout: int) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(16384)
            return {"status": int(r.getcode() or 200),
                    "json": json.loads(raw.decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "error": f"HTTPError: {exc}",
                "body_excerpt": _response_body(exc)}
    except Exception as exc:
        return {"status": None, "error": f"{type(exc).__name__}: {exc}"}


def collect_server_metadata(url: str, timeout: int = 5) -> dict:
    p = urllib.parse.urlsplit(url)
    base = urllib.parse.urlunsplit((p.scheme, p.netloc, "", "", ""))
    result = {"url": redact_url(url), "endpoints": {}}
    for endpoint in ("/health", "/v1/models"):
        result["endpoints"][endpoint] = _get_json_optional(base + endpoint, timeout)
    models = result["endpoints"].get("/v1/models", {}).get("json", {})
    if isinstance(models, dict):
        result["models"] = [x.get("id") for x in models.get("data", [])
                             if isinstance(x, dict) and x.get("id")]
    return result


def _sysctl(name: str) -> str | None:
    if not shutil.which("sysctl"):
        return None
    try:
        p = subprocess.run(["sysctl", "-n", name], capture_output=True,
                           text=True, timeout=2, check=False)
        return p.stdout.strip() if p.returncode == 0 else None
    except Exception:
        return None


def collect_runtime_metadata() -> dict:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "sysctl_cpu_brand": _sysctl("machdep.cpu.brand_string"),
        "sysctl_memsize": _sysctl("hw.memsize"),
        "hostname": platform.node(),
    }


def _validate_config(path: Path, current: dict, allow_mismatch: bool) -> None:
    if not path.exists():
        return
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"既存 config.json を読めません: {exc}") from exc
    keys = ("bench", "url", "think", "max_tokens", "temperature", "top_p",
            "seed", "mmlu_per_category", "gpqa_limit", "aime_limit",
            "humaneval_limit", "humaneval_data", "policy",
            "fast_max_tokens", "deep_max_tokens", "max_thinking_tokens",
            "fast_timeout", "deep_timeout", "max_timeout",
            "samples", "sample_temperature", "verify", "max_requests",
            "max_runtime")
    mismatch = {key: (old.get(key), current.get(key)) for key in keys
                if key in old and old.get(key) != current.get(key)}
    if mismatch and not allow_mismatch:
        raise RuntimeError(
            "既存結果と実行条件が違います。別の --out-dir を使うか "
            "--allow-config-mismatch を指定してください: " + repr(mismatch)
        )
    if mismatch:
        print("warning: config mismatch allowed: " + repr(mismatch),
              file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", nargs="+", choices=["mmlu", "gpqa", "aime", "humaneval"],
                    required=True)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--policy", choices=["fixed", "adaptive", "max"],
                    default="fixed",
                    help="fixed=従来条件、adaptive=問題別、max=全問thinking")
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--fast-max-tokens", type=int, default=512)
    ap.add_argument("--deep-max-tokens", type=int, default=2048)
    ap.add_argument("--max-thinking-tokens", type=int, default=4096,
                    help="maxモードの上限。CPUでは4096程度が安全")
    ap.add_argument("--fast-timeout", type=int, default=0)
    ap.add_argument("--deep-timeout", type=int, default=0)
    ap.add_argument("--max-timeout", type=int, default=0)
    ap.add_argument("--samples", type=int, default=1,
                    help="自己整合性用の候補数（CPUでは1〜3推奨）")
    ap.add_argument("--sample-temperature", type=float, default=0.35)
    ap.add_argument("--verify", action=argparse.BooleanOptionalAction, default=False,
                    help="候補の後に同じモデルで独立検証を1回行う")
    ap.add_argument("--max-requests", type=int, default=0,
                    help="実行全体のHTTP要求上限（0=無制限）")
    ap.add_argument("--max-runtime", type=float, default=0.0,
                    help="実行全体の秒数上限（0=無制限）")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--retry-backoff", type=float, default=0.5)
    ap.add_argument("--mmlu-per-category", type=int, default=10)
    ap.add_argument("--gpqa-limit", type=int, default=50)
    ap.add_argument("--aime-limit", type=int, default=0)
    ap.add_argument("--humaneval-limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--metadata-timeout", type=int, default=5)
    ap.add_argument("--allow-config-mismatch", action="store_true")
    ap.add_argument("--humaneval-data", default=str(
        Path(__file__).resolve().parents[1] / "LocalAI改良/tools/ops/humaneval/HumanEval.jsonl"))
    args = ap.parse_args()
    positive_values = {
        "--max-tokens": args.max_tokens,
        "--timeout": args.timeout,
        "--fast-max-tokens": args.fast_max_tokens,
        "--deep-max-tokens": args.deep_max_tokens,
        "--max-thinking-tokens": args.max_thinking_tokens,
    }
    if any(value <= 0 for value in positive_values.values()):
        ap.error("生成上限とtimeoutは正数が必要です")
    if args.retries < 0 or args.retry_backoff < 0:
        ap.error("--retries と --retry-backoff は0以上が必要です")
    if args.samples <= 0 or args.sample_temperature < 0:
        ap.error("--samples は正数、--sample-temperature は0以上が必要です")
    if args.max_requests < 0 or args.max_runtime < 0:
        ap.error("--max-requests と --max-runtime は0以上が必要です")
    fast_timeout = args.fast_timeout or args.timeout
    deep_timeout = args.deep_timeout or args.timeout
    # MAX推論だけは、通常の短いtimeoutを指定しても途中で切れにくくする。
    max_timeout = args.max_timeout or max(args.timeout, 1200)
    if min(fast_timeout, deep_timeout, max_timeout) <= 0:
        ap.error("profileのtimeoutは正数が必要です")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out_dir or (Path(__file__).resolve().parent / "bench_results" / stamp))
    out.mkdir(parents=True, exist_ok=True)
    config = {
        "harness_version": HARNESS_VERSION,
        "created_at": now_iso(),
        "argv": sys.argv,
        "bench": sorted(set(args.bench)),
        "url": redact_url(args.url),
        "policy": args.policy,
        "think": args.think,
        "max_tokens": args.max_tokens,
        "fast_max_tokens": args.fast_max_tokens,
        "deep_max_tokens": args.deep_max_tokens,
        "max_thinking_tokens": args.max_thinking_tokens,
        "temperature": 0.0,
        "top_p": 0.95,
        "timeout": args.timeout,
        "fast_timeout": fast_timeout,
        "deep_timeout": deep_timeout,
        "max_timeout": max_timeout,
        "samples": args.samples,
        "sample_temperature": args.sample_temperature,
        "verify": args.verify,
        "max_requests": args.max_requests,
        "max_runtime": args.max_runtime,
        "retries": args.retries,
        "retry_backoff": args.retry_backoff,
        "mmlu_per_category": args.mmlu_per_category,
        "gpqa_limit": args.gpqa_limit,
        "aime_limit": args.aime_limit,
        "humaneval_limit": args.humaneval_limit,
        "humaneval_data": str(Path(args.humaneval_data).resolve()),
        "seed": args.seed,
        "runtime": collect_runtime_metadata(),
        "server": collect_server_metadata(args.url, args.metadata_timeout),
    }
    _validate_config(out / "config.json", config, args.allow_config_mismatch)
    json_dump(out / "config.json", config)

    client = LocalClient(args.url, args.think, args.max_tokens, args.timeout,
                         retries=args.retries, retry_backoff=args.retry_backoff,
                         seed=args.seed)
    profiles = {
        "fixed": RequestProfile("fixed", args.think, args.max_tokens,
                                 args.timeout, 0.0),
        "fast": RequestProfile("fast", False, args.fast_max_tokens,
                                fast_timeout, 0.0),
        "deep": RequestProfile("deep", True, args.deep_max_tokens,
                                deep_timeout, 0.0),
        "max": RequestProfile("max", True, args.max_thinking_tokens,
                               max_timeout, 0.0),
    }
    adaptive_options = {
        "profiles": profiles,
        "samples": args.samples,
        "sample_temperature": args.sample_temperature,
        "verify": args.verify,
        "max_requests": args.max_requests,
        "deadline": args.max_runtime,
    }
    adaptive_state = {"request_count": 0}

    def task_client(task_name: str, answer_fn: Callable[[str], Any],
                    *, code: bool = False):
        if args.policy == "fixed":
            return client
        # コードは文字列一致投票ではなく、he_eval.pyの実行結果で選ぶため、
        # このハーネスでは候補を増やさない。生成自体は適応／maxを使える。
        options = dict(adaptive_options)
        if code:
            options["samples"] = 1
            options["verify"] = False
        options["shared_state"] = adaptive_state
        return AdaptiveClient(client, task_name, args.policy, answer_fn=answer_fn,
                              **options)
    summaries: list[dict] = []

    if "mmlu" in args.bench:
        rows_all = fetch_hf_parquet(
            "TIGER-Lab/MMLU-Pro", "data/test-00000-of-00001.parquet",
            out, "mmlu_pro_test.jsonl")
        id_fn = lambda x: f"mmlu/{x['question_id']}"
        rows = stratified(rows_all, "category", args.mmlu_per_category, args.seed, id_fn)
        manifest = write_dataset_manifest(
            out, "mmlu_pro", [out / "datasets/mmlu_pro_test.jsonl"], rows_all, rows,
            id_fn, {"method": "stratified", "field": "category",
                    "per_group": args.mmlu_per_category, "seed": args.seed})
        summaries.append(run_rows("mmlu_pro", rows, mmlu_prompt,
                                  lambda x: extract_letter(x, MMLU_LETTERS),
                                  task_client("mmlu_pro",
                                              lambda x: extract_letter(x, MMLU_LETTERS)), out,
                                  id_fn, manifest_path=str(manifest)))

    if "gpqa" in args.bench:
        rows_all = fetch_hf_parquet(
            "hendrydong/gpqa_diamond_mc", "data/test-00000-of-00001.parquet",
            out, "gpqa_diamond_mc_test.jsonl")
        id_fn = lambda x: "gpqa/" + sha256_bytes(
            x["problem"].encode("utf-8"))[:16]
        rows = balanced_sample(rows_all, "domain", args.gpqa_limit, args.seed, id_fn)
        manifest = write_dataset_manifest(
            out, "gpqa_diamond", [out / "datasets/gpqa_diamond_mc_test.jsonl"],
            rows_all, rows, id_fn,
            {"method": "balanced", "field": "domain", "limit": args.gpqa_limit,
             "seed": args.seed})
        summaries.append(run_rows("gpqa_diamond", rows, gpqa_prompt,
                                  lambda x: extract_letter(x, "ABCD"),
                                  task_client("gpqa_diamond",
                                              lambda x: extract_letter(x, "ABCD")), out,
                                  id_fn, manifest_path=str(manifest)))

    if "aime" in args.bench:
        a24 = fetch_hf_parquet(
            "HuggingFaceH4/aime_2024", "data/train-00000-of-00001.parquet",
            out, "aime_2024.jsonl")
        a25a = fetch_url_jsonl(
            "https://huggingface.co/datasets/opencompass/AIME2025/resolve/main/aime2025-I.jsonl",
            out, "aime2025-I.jsonl")
        a25b = fetch_url_jsonl(
            "https://huggingface.co/datasets/opencompass/AIME2025/resolve/main/aime2025-II.jsonl",
            out, "aime2025-II.jsonl")
        rows_all = (
            [{"id": f"aime24/{x['id']}", "problem": x["problem"],
              "answer": str(x["answer"])} for x in a24]
            + [{"id": f"aime25/{i}", "problem": x["question"],
                "answer": str(x["answer"])} for i, x in enumerate(a25a + a25b)]
        )
        rows = rows_all[:args.aime_limit] if args.aime_limit else rows_all
        id_fn = lambda x: str(x["id"])
        manifest = write_dataset_manifest(
            out, "aime", [out / "datasets/aime_2024.jsonl",
                          out / "datasets/aime2025-I.jsonl",
                          out / "datasets/aime2025-II.jsonl"],
            rows_all, rows, id_fn,
            {"method": "source_order", "limit": args.aime_limit,
             "seed": args.seed})
        summaries.append(run_rows("aime", rows,
                                  lambda x: aime_prompt(x["problem"]),
                                  extract_integer,
                                  task_client("aime", extract_integer), out, id_fn,
                                  manifest_path=str(manifest)))

    if "humaneval" in args.bench:
        data = Path(args.humaneval_data)
        problems_all = read_jsonl(data)
        problems = problems_all[:args.humaneval_limit] if args.humaneval_limit else problems_all
        id_fn = lambda x: str(x.get("task_id") or x.get("id"))
        manifest = write_dataset_manifest(
            out, "humaneval", [data], problems_all, problems, id_fn,
            {"method": "source_order", "limit": args.humaneval_limit})
        summaries.append(human_eval(task_client("humaneval", lambda x: x,
                                               code=True),
                                    out, data, args.humaneval_limit,
                                    str(manifest)))

    finished = now_iso()
    json_dump(out / "summary.json", {
        "harness_version": HARNESS_VERSION,
        "finished_at": finished,
        "config": str(out / "config.json"),
        "summaries": summaries,
    })
    config["finished_at"] = finished
    config["summary"] = str(out / "summary.json")
    json_dump(out / "config.json", config)
    print(f"結果: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
