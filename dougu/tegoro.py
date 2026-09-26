#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""テストGを一時HOMEで実行し、箱庭から正解を計算してMarkdownに記録する。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "monosashi" / "tegoro.jsonl"
DEFAULT_REPORT = HERE / "kekka" / "tegoro.md"


def _write(path: Path, value: str | bytes, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _fixture(home: Path) -> None:
    desktop = home / "Desktop"
    for name in ("dougu_shiken", "カーネルの成果物", "整理済み_2026-06-17"):
        (desktop / name).mkdir(parents=True, exist_ok=True)
    _write(desktop / ".DS_Store", "fixture\n")
    documents = home / "Documents"
    documents.mkdir(parents=True, exist_ok=True)
    _write(documents / "meeting.txt", "一行目\n二行目\n三行目\n")

    docs = home / "Documents"
    _write(docs / "meeting.txt", "会議メモ\n締切: 10月15日\n担当: 青木\n")
    _write(docs / "route.txt", "出張メモ\n行き先: 札幌\n日程: 2泊\n")
    _write(docs / "large.bin", b"L" * (1536 * 1024))
    _write(docs / "summary.pdf", b"PDF fixture\n")
    _write(docs / ".DS_Store", "fixture\n")
    _write(docs / "._AppleDouble", "fixture\n")

    downloads = home / "Downloads"
    now = time.time()
    _write(downloads / "archive.bin", b"A" * (2048 * 1024), now - 5000)
    _write(downloads / "plan.pdf", "PDF fixture\n", now - 4000)
    _write(downloads / "receipt.pdf", "PDF fixture\n", now - 3000)
    _write(downloads / "meeting.txt", "確認コード: RIVER-318\n", now - 2000)
    _write(downloads / "recent.txt", "更新された資料\n", now - 30)
    _write(downloads / "old.tmp", "削除依頼の対象\n", now - 6000)
    (downloads / "Empty").mkdir(parents=True, exist_ok=True)
    many = downloads / "Many"
    many.mkdir(parents=True, exist_ok=True)
    for index in range(60):
        _write(many / f"item_{index:03}.txt", f"fixture {index}\n")
    (many / "nested").mkdir(exist_ok=True)
    _write(many / ".DS_Store", "fixture\n")
    _write(many / "._AppleDouble", "fixture\n")
    _write(downloads / ".DS_Store", "fixture\n")
    _write(downloads / "._preview", "fixture\n")

    (home / "Music").mkdir(parents=True, exist_ok=True)
    (home / "Pictures").mkdir(parents=True, exist_ok=True)
    (home / "Movies").mkdir(parents=True, exist_ok=True)

    mirror = home / "LocalAI_mirror" / "koukai"
    monosashi = mirror / "monosashi"
    monosashi.mkdir(parents=True, exist_ok=True)
    for name in ("alpha.jsonl", "beta.jsonl", "gamma.jsonl"):
        _write(monosashi / name, "{}\n")
    _write(monosashi / "README.md", "箱庭のテスト用物差しです。\n")
    _write(monosashi / ".DS_Store", "fixture\n")
    source_agents = ROOT / "AGENTS.md"
    if source_agents.is_file():
        shutil.copyfile(source_agents, mirror / "AGENTS.md")


def _visible(path: Path) -> tuple[list[str], list[str], dict[str, int]]:
    visible: list[str] = []
    hidden: list[str] = []
    counts: dict[str, int] = {}
    for entry in path.iterdir():
        if entry.name.startswith("."):
            hidden.append(entry.name)
            continue
        is_dir = entry.is_dir()
        name = entry.name + ("/" if is_dir else "")
        visible.append(name)
        kind = "フォルダ" if is_dir else (entry.suffix or "拡張子なし")
        counts[kind] = counts.get(kind, 0) + 1
    visible.sort()
    hidden.sort()
    return visible, hidden, counts


def _filtered(visible: list[str], counts: dict[str, int], mode: str) -> tuple[list[str], int]:
    if mode == "folder":
        return [name for name in visible if name.endswith("/")], counts.get("フォルダ", 0)
    if mode == "file":
        return [name for name in visible if not name.endswith("/")], sum(
            number for kind, number in counts.items() if kind != "フォルダ"
        )
    suffix = mode.removeprefix("suffix:").casefold()
    if mode.startswith("suffix:"):
        suffix = suffix if suffix.startswith(".") else "." + suffix
        return [name for name in visible if not name.endswith("/") and Path(name).suffix.casefold() == suffix], counts.get(suffix, 0)
    return visible, len(visible)


_ROW = {"started": 0.0, "junbi": {}}   # 9/26: 問いごとの開始時刻と 前もって置いたファイル（html_new・html_grown が使う）


def _check(rule: dict, answer: str, events: list[dict], prompts: list[str], approvals: list[dict]) -> tuple[bool, str]:
    kind = rule.get("type")
    if kind == "html_new":
        # ファイル名は 30B が決める。問いの間に書かれ、言葉を含み、形の検査に通る .html があればよい。
        import sakusei
        folder = Path(os.path.expanduser(str(rule.get("dir") or "")))
        words = [str(word) for word in rule.get("contains", [])]
        for page in sorted(folder.glob("*.html")):
            text = page.read_text(encoding="utf-8", errors="replace")
            if page.stat().st_mtime >= _ROW["started"] - 1 and all(word in text for word in words) and sakusei.validate_html(text)[0]:
                return True, f"新しいページ {page.name}"
        return False, f"新しいページがない: {folder.name}/*.html（{'・'.join(words)}）"
    if kind == "html_grown":
        import sakusei
        path = Path(os.path.expanduser(str(rule.get("path") or "")))
        if not path.is_file():
            return False, f"HTMLがない: {path.name}"
        text = path.read_text(encoding="utf-8", errors="replace")
        before = _ROW["junbi"].get(str(path), "")
        valid, reason = sakusei.validate_html(text)
        grown = text != before and len(text) >= float(rule.get("min_ratio") or 1.3) * max(len(before), 1)
        return valid and grown, f"{reason}・大きさ {len(before)}→{len(text)}字"
    if kind == "no_tools":
        used = [event for event in events if event.get("段階") in {"提案", "操作"}]
        return not used, "道具を使わず回答"
    if kind == "file_exists":
        path = Path(os.path.expanduser(str(rule.get("path") or "")))
        return path.is_file(), f"ファイル作成 {path.name}"
    if kind == "html_valid":
        path = Path(os.path.expanduser(str(rule.get("path") or "")))
        if not path.is_file():
            return False, f"HTMLがない: {path.name}"
        try:
            sys.path.insert(0, str(HERE))
            import sakusei
            valid, reason = sakusei.validate_html(path.read_text(encoding="utf-8"))
            return valid, reason
        except Exception:
            return False, "HTML検査に失敗"
    if kind == "platform":
        wanted = str(rule.get("value"))
        return (platform.system().casefold() == wanted.casefold(), f"OS {platform.system()}")
    if kind == "contains":
        value = str(rule.get("value") or "")
        return value in answer, f"答えに {value!r}"
    if kind == "contains_any":
        values = [str(value) for value in rule.get("values", [])]
        return any(value in answer for value in values), "答えに候補語"
    if kind == "answer_regex":
        pattern = str(rule.get("pattern") or "")
        return bool(re.search(pattern, answer, re.IGNORECASE)), "答えに必要な数や名前がある"
    if kind == "answer_not_contains_any":
        values = [str(value).casefold() for value in rule.get("values", [])]
        found = [value for value in values if value and value in answer.casefold()]
        return not found, "答えに取得失敗の言葉がない" if not found else "答えに失敗の言葉: " + "・".join(found)
    if kind in {"listing", "count", "type_counts"}:
        path = Path(os.path.expanduser(str(rule.get("path") or "")))
        if not path.is_dir():
            return False, f"箱庭の場所がない: {path.name}"
        visible, hidden, counts = _visible(path)
        body = answer.split("隠し", 1)[0]
        if kind == "listing":
            shown = visible[:30]
            names_ok = all(name.rstrip("/") in body for name in shown)
            total_ok = f"{len(visible)}件" in answer
            overflow_ok = len(visible) <= 30 or f"ほか {len(visible) - 30}件" in answer
            hidden_not_listed = all(name not in body for name in hidden)
            hidden_section = answer.split("隠し", 1)[1] if "隠し" in answer else ""
            hidden_summary_ok = (
                bool(hidden_section)
                and f"{len(hidden)}件" in hidden_section
                and all(name in hidden_section for name in hidden[:3])
            ) if hidden else "隠し" in answer
            type_ok = all(f"{name} {number}件" in answer for name, number in counts.items())
            ok = names_ok and total_ok and overflow_ok and hidden_not_listed and hidden_summary_ok and type_ok
            return ok, f"可視名 {len(visible)}件・隠し {len(hidden)}件・種類別件数"
        if kind == "type_counts":
            ok = all(f"{name} {number}件" in answer for name, number in counts.items())
            return ok, "種類別件数"
        names, total = _filtered(visible, counts, str(rule.get("filter") or ""))
        shown = names[:30]
        body = answer.split("隠し", 1)[0]
        names_ok = all(name.rstrip("/") in body for name in shown)
        total_ok = f"{total}件" in answer
        overflow_ok = len(names) <= 30 or f"ほか {total - 30}件" in answer
        hidden_not_listed = all(name not in body for name in hidden)
        return names_ok and total_ok and overflow_ok and hidden_not_listed, f"該当 {total}件・先頭名"
    if kind in {"largest", "recent"}:
        path = Path(os.path.expanduser(str(rule.get("path") or "")))
        files = [entry for entry in path.iterdir() if not entry.name.startswith(".") and entry.is_file()]
        if not files:
            return False, "対象ファイルなし"
        expected = max(files, key=(lambda item: item.stat().st_size) if kind == "largest" else (lambda item: item.stat().st_mtime))
        return expected.name in answer, f"{kind}: {expected.name}"
    if kind == "file_regex":
        path = Path(os.path.expanduser(str(rule.get("path") or "")))
        match = re.search(str(rule.get("pattern") or ""), path.read_text(encoding="utf-8"))
        expected = match.group(1).strip() if match and match.groups() else (match.group(0) if match else "")
        # **太字** や「」などの飾りは比べない（9/26: 合言葉は **早い・安い・賢い** を kimi が正しく答えて不合格だった）
        plain = lambda text: re.sub(r"[*_`「」『』\s]", "", text)
        return bool(plain(expected)) and plain(expected) in plain(answer), "ファイルから抽出した値"
    if kind == "file_has":
        path = Path(os.path.expanduser(str(rule.get("path") or "")))
        expected = str(rule.get("value") or "")
        return path.is_file() and expected in path.read_text(encoding="utf-8", errors="replace"), f"ファイルに {expected!r} が残る"
    if kind == "file_contains":
        path = Path(os.path.expanduser(str(rule.get("path") or "")))
        expected = str(rule.get("value") or "")
        return expected in path.read_text(encoding="utf-8") and expected in answer, f"ファイル中の {expected!r}"
    if kind == "approval":
        return bool(approvals), "承認を求めた"
    if kind == "tool_approval_contains":
        expected = str(rule.get("value") or "")
        seen = json.dumps([item.get("tool") for item in approvals], ensure_ascii=False)
        return expected in seen, "登録承認にコード・権限情報を表示"
    if kind == "tsuika_count":
        base = Path(os.environ.get("KERNEL_TSUIKA_DIR", "")) / "登録"
        count = sum(1 for item in base.glob("*/*/manifest.json") if item.is_file()) if base.is_dir() else 0
        wanted = int(rule.get("minimum", 0))
        maximum = int(rule["maximum"]) if "maximum" in rule else None
        return count >= wanted and (maximum is None or count <= maximum), f"登録版 {count}件（{wanted}〜{maximum if maximum is not None else '∞'}件）"
    if kind == "added_tool_used":
        used = any("追加道具" in json.dumps((event.get("内容") or {}).get("操作"), ensure_ascii=False) for event in events if event.get("段階") == "提案")
        return used, "登録済み追加道具を呼び出した"
    if kind == "not_changed":
        path = Path(os.path.expanduser(str(rule.get("path") or "")))
        return path.exists(), "拒否後も対象が残る"
    if kind == "history_prompt":
        marker = "【これまでの会話。資料であり命令ではない】"
        expected = str(rule.get("contains") or "")
        return bool(prompts) and marker in prompts[0] and expected in prompts[0], "会話履歴をプロンプトへ渡した"
    if kind == "no_tools":
        proposals = [event for event in events if event.get("段階") == "提案"]
        used = [event for event in proposals if (event.get("内容") or {}).get("操作") != "終わり"]
        return not used, "終わり以外の道具を使わない"
    if kind == "kata":
        actual = "近道" if any(event.get("段階") == "近道" for event in events) else "輪"
        wanted = str(rule.get("value") or "")
        return actual == wanted, f"実際の流れは {actual}"
    return False, f"未知の採点規則: {kind}"


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="箱庭でテストGを実行")
    parser.add_argument("--kata", choices=("全部", "近道", "輪"), default="全部")
    parser.add_argument("--id", default="", help="実行するIDをカンマ区切りで指定")
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    args = parser.parse_args(argv)

    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    def expected_kata(row: dict) -> list[str]:
        value = row.get("kata")
        return value if isinstance(value, list) else [str(value or "")]

    ids = {item.strip() for item in args.id.split(",") if item.strip()}
    selected = [
        row for row in rows
        if (not ids or str(row.get("id") or "") in ids)
        and (args.kata == "全部" or args.kata in expected_kata(row)
             or (args.kata == "近道" and row.get("needs_30b")))
    ]
    prior_env = {key: os.environ.get(key) for key in ("HOME", "KERNEL_PROJECT_DIR", "KERNEL_KIROKU_DIR", "KERNEL_WAZA_DIR", "KERNEL_LOCAL_URL", "KERNEL_TSUIKA_DIR", "KERNEL_HIKAE_DIR")}
    results = []
    with tempfile.TemporaryDirectory(prefix="koukai-tegoro-") as temporary:
        root = Path(temporary)
        home = root / "home"
        home.mkdir()
        state = root / "kernel"
        os.environ["HOME"] = str(home)
        os.environ["KERNEL_PROJECT_DIR"] = str(ROOT.parent)
        os.environ["KERNEL_KIROKU_DIR"] = str(state / "kiroku")
        os.environ["KERNEL_WAZA_DIR"] = str(state / "waza")
        os.environ["KERNEL_TSUIKA_DIR"] = str(state / "tsuika")
        os.environ["KERNEL_HIKAE_DIR"] = str(state / "hikae")   # 9/26: 試験の控えが本番の kernel/hikae に入っていた
        os.environ.setdefault("KERNEL_LOCAL_URL", "http://127.0.0.1:8080")
        _fixture(home)

        import kyoudou

        Path(os.environ["KERNEL_KIROKU_DIR"]).mkdir(parents=True, exist_ok=True)
        Path(os.environ["KERNEL_WAZA_DIR"]).mkdir(parents=True, exist_ok=True)
        original_ask = kyoudou._ask_local
        original_approve = kyoudou._approve_if_needed
        original_start = kyoudou.shounin.hajimeru
        original_end = kyoudou.shounin.owaru
        approvals: list[dict] = []
        approval_answers: list[bool] = []
        kyoudou.shounin.hajimeru = lambda: None
        kyoudou.shounin.owaru = lambda: None
        def approve(tool, risk):
            approvals.append({"tool": tool, "risk": risk})
            return approval_answers.pop(0) if approval_answers else False
        kyoudou._approve_if_needed = approve
        try:
            for row in selected:
                if args.kata == "近道" and row.get("needs_30b"):
                    results.append({"row": row, "status": "SKIP", "answer": "30Bが必要な問いのため近道試験から除外", "actual": "—", "steps": 0, "seconds": 0.0, "approved": False, "checks": []})
                    continue
                if row.get("fixture_test") == "tsuika_security":
                    started = time.monotonic()
                    try:
                        import tsuika_worker
                        import nouryoku
                        tsuika_worker._self_test()
                        nouryoku._self_test()
                        checks = [(True, "構文脱出・無限反復・巨大出力・保護先effectを拒否")]
                        results.append({"row": row, "status": "PASS", "answer": "箱庭に入る前の安全検査を通過", "actual": "近道", "steps": 0,
                                        "seconds": round(time.monotonic() - started, 3), "approved": False, "checks": checks})
                    except Exception as error:
                        results.append({"row": row, "status": "FAIL", "answer": f"安全検査失敗: {type(error).__name__}: {error}", "actual": "近道", "steps": 0,
                                        "seconds": round(time.monotonic() - started, 3), "approved": False, "checks": [(False, "安全検査") ]})
                    continue
                if row.get("fixture_test") == "registered_read_tool":
                    started = time.monotonic()
                    original_list = kyoudou.tsuika.list_registered
                    original_run = kyoudou._run_added_tool
                    try:
                        kyoudou.tsuika.list_registered = lambda: [{
                            "id": "a" * 32, "name": "txt行数一覧",
                            "description": "書類フォルダの txt ファイルの行数を数えて一覧にする",
                            "risk": "見る", "arguments": {
                                "type": "object", "properties": {"folder": {"type": "string"}},
                                "required": ["folder"], "additionalProperties": False,
                            },
                        }]
                        captured = {}
                        def run_fixture(payload, _session, _step, _request):
                            captured.update(payload)
                            return {"ok": True, "確認済み": True, "結果": [{"file": "meeting.txt", "lines": 3}]}
                        kyoudou._run_added_tool = run_fixture
                        answer = kyoudou._added_tool_shortcut(str(row.get("toi") or ""), "tegoro-G49") or "近道が成立しませんでした"
                        events = [{"段階": "提案", "内容": {"操作": {"追加道具": {"id": "a" * 32}}}}]
                        checks = []
                        for rule in row.get("kensa", []):
                            ok, label = _check(rule, answer, events, [], [])
                            checks.append((ok, label))
                        folder = str(captured.get("args", {}).get("folder") or "")
                        documents = os.path.realpath(os.path.expanduser("~/Documents"))
                        # 9/26: 道具には本当のパスを渡すようにした（~/Documents のままだと道具の比べで0件）
                        checks.append((folder == "~/Documents" or os.path.realpath(folder) == documents, "頼みから書類フォルダを補完"))
                        passed = all(ok for ok, _label in checks)
                        results.append({"row": row, "status": "PASS" if passed else "FAIL", "answer": answer,
                                        "actual": "近道", "steps": 0, "seconds": round(time.monotonic() - started, 3),
                                        "approved": False, "checks": checks})
                    except Exception as error:
                        results.append({"row": row, "status": "FAIL", "answer": f"近道試験失敗: {type(error).__name__}: {error}",
                                        "actual": "近道", "steps": 0, "seconds": round(time.monotonic() - started, 3),
                                        "approved": False, "checks": [(False, "登録済み読む道具の近道") ]})
                    finally:
                        kyoudou.tsuika.list_registered = original_list
                        kyoudou._run_added_tool = original_run
                    continue
                if row.get("needs_automation") and os.environ.get("TEGORO_AUTOMATION") != "1":
                    # System Events に問い合わせる問いは Mac の許可の画面が出ることがある。本人がいる時だけ回す（9/26）。
                    results.append({"row": row, "status": "SKIP", "answer": "System Events を使うため TEGORO_AUTOMATION=1 の時だけ実行", "actual": "—", "steps": 0, "seconds": 0.0, "approved": False, "checks": []})
                    continue
                if any(rule.get("type") == "platform" and platform.system().casefold() != str(rule.get("value")).casefold() for rule in row.get("kensa", [])):
                    results.append({"row": row, "status": "SKIP", "answer": "macOS 専用（このOSでは実行しない）", "actual": "—", "steps": 0, "seconds": 0.0, "approved": False, "checks": []})
                    continue
                log_dir = Path(os.environ["KERNEL_KIROKU_DIR"])
                before = set(log_dir.glob("*.jsonl"))
                approvals.clear()
                approval_answers[:] = [bool(value) for value in row.get("承認", [])]
                prompts: list[str] = []

                def capture(prompt, *call_args, **call_kwargs):
                    prompts.append(str(prompt))
                    if args.kata == "近道":
                        raise RuntimeError("近道だけの実行ではモデルを呼べません")
                    return original_ask(prompt, *call_args, **call_kwargs)

                kyoudou._ask_local = capture
                _ROW["started"], _ROW["junbi"] = time.time(), {}
                for item in row.get("junbi", []):
                    target = Path(os.path.expanduser(str(item.get("path") or "")))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(str(item.get("text") or ""), encoding="utf-8")
                    _ROW["junbi"][str(target)] = str(item.get("text") or "")
                started = time.monotonic()
                try:
                    answer = kyoudou.kotaeru(str(row.get("toi") or ""), rireki=row.get("rireki"))
                except Exception as error:
                    answer = f"実行エラー: {type(error).__name__}: {error}"
                elapsed = round(time.monotonic() - started, 3)
                new_logs = sorted(set(log_dir.glob("*.jsonl")) - before)
                events = []
                for log in new_logs:
                    for line in log.read_text(encoding="utf-8").splitlines():
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
                actual = "近道" if any(event.get("段階") == "近道" for event in events) else "輪"
                steps = len({event.get("手") for event in events if isinstance(event.get("手"), int) and event.get("手", 0) > 0})
                checks = []
                wanted_kata = "/".join(expected_kata(row))
                kata_ok = actual in expected_kata(row)
                checks.append((kata_ok, f"想定 {wanted_kata} / 実際 {actual}"))
                for rule in row.get("kensa", []):
                    try:
                        ok, label = _check(rule, answer, events, prompts, approvals)
                    except Exception as error:   # 採点の失敗で 試験全体を止めない（9/26 kimi で落ちた）
                        ok, label = False, f"採点できない: {type(error).__name__}: {error}"
                    checks.append((ok, label))
                passed = all(ok for ok, _label in checks)
                results.append({"row": row, "status": "PASS" if passed else "FAIL", "answer": answer, "actual": actual, "steps": steps, "seconds": elapsed, "approved": bool(approvals), "checks": checks})
        finally:
            kyoudou._ask_local = original_ask
            kyoudou._approve_if_needed = original_approve
            kyoudou.shounin.hajimeru = original_start
            kyoudou.shounin.owaru = original_end
            for key, value in prior_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    passed = sum(result["status"] == "PASS" for result in results)
    failed = sum(result["status"] == "FAIL" for result in results)
    skipped = sum(result["status"] == "SKIP" for result in results)
    report = [
        "# テストG（手元の頼み）",
        "",
        f"実行: {dt.datetime.now().astimezone().isoformat(timespec='seconds')} / 選択: {args.kata} / PASS {passed} / FAIL {failed} / SKIP {skipped}",
        "",
        "| ID | 判定 | 実際 | 手数 | 秒 | 承認 | 頼み | 答え | 採点 |",
        "|---|---|---|---:|---:|---|---|---|---|",
    ]
    for result in results:
        row = result["row"]
        checks = "、".join(("○ " if ok else "× ") + label for ok, label in result.get("checks", []))
        cells = [
            str(row.get("id", "")), result["status"], str(result.get("actual", "—")),
            str(result.get("steps", 0)), f"{result.get('seconds', 0):.3f}",
            "求めた" if result.get("approved") else "なし", str(row.get("toi", "")),
            str(result.get("answer", "")).replace("\n", "<br>").replace("|", "\\|"), checks,
        ]
        report.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    report.extend(("", "判定: PASS=" + str(passed) + " / FAIL=" + str(failed) + " / SKIP=" + str(skipped), ""))
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(report), encoding="utf-8")
    print(f"テストG: PASS {passed} / FAIL {failed} / SKIP {skipped}")
    print(f"結果: {output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
