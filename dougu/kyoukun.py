#!/usr/bin/env python3
"""成功を確認できた輪の記録から、門番の知らせを教訓カードにする。"""

import argparse
import json
import os
import re
from pathlib import Path


FAILURE_ANSWER = "終わりまでできませんでした"
CHANGE_TOOLS = {"write", "edit", "move", "copy", "trash", "sh"}
DEFAULT_PATH = Path.home() / "Library/Application Support/kernel-ai/kyoukun.json"


def _files(paths, jogai):
    excluded = {str(x).strip().upper() for x in jogai}
    for raw in paths:
        p = Path(raw).expanduser()
        candidates = sorted(p.rglob("jiyuu_*.jsonl")) if p.is_dir() else ([p] if p.is_file() else [])
        for f in candidates:
            if any(part.upper() in excluded for part in f.parts):
                continue
            yield f


def _generalize(value, limit):
    s = str(value or "")
    # Full paths and home-relative locations first, so their filenames are not handled alone.
    s = re.sub(r"(?<![\w*])~/(?:[^\s\"'<>|]*)|(?<![\w*/])/(?:[^\s\"'<>|/]+/)*[^\s\"'<>|/]+", "<場所>", s)
    # 10/3: 「見積.txtとして」のように後ろへ日本語が続いても置き換える（ファイル名ごとに別のカードになっていた）。
    s = re.sub(r"(?<![\w])[\w.-]+\.[A-Za-z0-9]{1,12}(?![A-Za-z0-9])", "<ファイル>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _read_records(path):
    rows = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except (OSError, UnicodeError):
        pass
    return rows


def _successful_after(rows, index):
    latest_tool = ""
    first_tool = ""
    tool_by_hand = {}
    for row in rows[index + 1:]:
        stage = row.get("段階")
        body = row.get("内容") or {}
        if not isinstance(body, dict):
            continue
        if stage == "提案" and body.get("道具"):
            latest_tool = body["道具"]
            if not first_tool:
                first_tool = latest_tool
            tool_by_hand[row.get("手")] = latest_tool
        if stage == "結果" and body.get("ok") is True:
            # An ok result is a qualifying change only when its matching proposal is a change tool.
            tool = tool_by_hand.get(row.get("手"), latest_tool)
            if tool in CHANGE_TOOLS:
                return first_tool or tool
        if stage == "結果" and isinstance(body.get("答え"), str):
            answer = body["答え"].strip()
            if answer and FAILURE_ANSWER not in answer:
                return first_tool or latest_tool
    return None


def atsumeru(paths, jogai=()):
    """集めた記録から、成功後に残す「次」をカード化する。"""
    cards = {}
    for path in _files(paths, jogai):
        rows = _read_records(path)
        request = next((
            (r.get("内容") or {}).get("文") for r in rows
            if r.get("段階") == "依頼" and isinstance(r.get("内容"), dict)
        ), "")
        for i, row in enumerate(rows):
            body = row.get("内容") or {}
            if row.get("段階") != "結果" or not isinstance(body, dict) or not body.get("次"):
                continue
            tool = _successful_after(rows, i)
            if tool is None:
                continue
            notice = _generalize(body["次"], 160)
            if not notice:
                continue
            if notice not in cards:
                cards[notice] = {"知らせ": notice, "道具": str(tool), "頼み": _generalize(request, 120), "数": 0, "頼みたち": []}
            cards[notice]["数"] += 1
            # 10/3: まとめたカードは最初の頼みしか持たず、似た頼みで選ばれなかった。違う頼みを8つまで持つ。
            other = _generalize(request, 120)
            if other and other not in cards[notice]["頼みたち"] and len(cards[notice]["頼みたち"]) < 8:
                cards[notice]["頼みたち"].append(other)
    return list(cards.values())


def _grams(text):
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    return {normalized[i:i + 2] for i in range(max(0, len(normalized) - 1))}


def erabu(request, cards, k=2):
    query = _grams(_generalize(request, 400))   # カードの頼みと同じく場所・ファイル名を伏せて比べる
    if not query or k <= 0:
        return []
    ranked = []
    for order, card in enumerate(cards):
        best = (0, 0.0)
        for asked in [card.get("頼み", "")] + list(card.get("頼みたち") or []):
            grams = _grams(asked)
            common = len(query & grams)
            best = max(best, (common, common / max(len(query), len(grams), 1)), key=lambda x: x[1])
        common, score = best
        if common >= 2 and score >= 0.15:
            ranked.append((score, card.get("数", 0), -order, card))
    ranked.sort(reverse=True, key=lambda x: x[:3])
    return [item[3] for item in ranked[:k]]


def soeru(request, path=None):
    target = Path(path).expanduser() if path else Path(os.environ.get("KERNEL_KYOUKUN_PATH", DEFAULT_PATH)).expanduser()
    try:
        cards = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(cards, list):
            return ""
        selected = erabu(request, cards)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return ""
    if not selected:
        return ""
    prefix = "前に似た頼みで門番に直されたこと: ・"
    parts = []
    for card in selected:
        item = f"{card.get('知らせ', '')}（{card.get('道具', '')}）"
        candidate = prefix + " ・".join(parts + [item])
        if len(candidate) > 300:
            remaining = 300 - len(prefix) - len(" ・".join(parts)) - (2 if parts else 0)
            if remaining > 0:
                parts.append(item[:remaining])
            break
        parts.append(item)
    return prefix + " ・".join(parts) if parts else ""


def _combine(old, fresh):
    by_notice = {}
    for card in old + fresh:
        if not isinstance(card, dict) or not card.get("知らせ"):
            continue
        notice = str(card["知らせ"])
        if notice not in by_notice:
            by_notice[notice] = {
                "知らせ": notice,
                "道具": str(card.get("道具", "")),
                "頼み": str(card.get("頼み", "")),
                "数": 0,
                "頼みたち": [],
            }
        by_notice[notice]["数"] += max(0, int(card.get("数", 1)))
        for asked in card.get("頼みたち") or []:
            if asked not in by_notice[notice]["頼みたち"] and len(by_notice[notice]["頼みたち"]) < 8:
                by_notice[notice]["頼みたち"].append(asked)
    return sorted(by_notice.values(), key=lambda c: c["数"], reverse=True)[:200]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("tsukuru")
    make.add_argument("--logs", nargs="+", required=True)
    make.add_argument("--jogai", default="")
    make.add_argument("--out", required=True)
    show = sub.add_parser("miru")
    show.add_argument("request")
    show.add_argument("--path")
    args = parser.parse_args(argv)
    if args.command == "tsukuru":
        out = Path(args.out).expanduser()
        # 10/3: 記録が正なので毎回作り直す（前の分と足すと、毎晩同じ記録で数が倍になっていた）。
        fresh = atsumeru(args.logs, [x for x in args.jogai.split(",") if x.strip()])
        result = _combine([], fresh)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{len(result)}枚")
        for card in result[:3]:
            print(f"{card['数']}回｜{card['知らせ']}｜{card['道具']}")
    else:
        print(soeru(args.request, args.path))


if __name__ == "__main__":
    main()
