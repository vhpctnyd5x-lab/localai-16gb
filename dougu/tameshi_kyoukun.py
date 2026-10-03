#!/usr/bin/env python3
"""夜の教訓カードの一時記録による自己試験。"""

import json
import tempfile
from pathlib import Path

import kyoukun


def main():
    passed = 0
    total = 10

    def check(condition, label):
        nonlocal passed
        if not condition:
            raise AssertionError(label)
        passed += 1

    with tempfile.TemporaryDirectory(prefix="kyoukun-") as temp:
        root = Path(temp) / "logs"
        def record(j, filename, rows):
            folder = root / "0928_0000" / j
            folder.mkdir(parents=True, exist_ok=True)
            (folder / filename).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
        def ev(stage, content, hand=1):
            return {"時刻": "2026-09-28T00:00:00+09:00", "手": hand, "段階": stage, "内容": content}

        successful = [
            ev("依頼", {"文": "~/Desktop/報告.txt に結果を書いて"}, 0),
            ev("結果", {"次": "絶対パス /Users/a/Desktop/報告.txt を指定してください"}),
            ev("提案", {"道具": "write", "入力": {"path": "/Users/a/Desktop/報告.txt"}}),
            ev("結果", {"ok": True, "結果": "書き込み済み"}),
            ev("結果", {"答え": "完了しました"}, 2),
        ]
        record("J01", "jiyuu_a.jsonl", successful)
        record("J02", "jiyuu_b.jsonl", successful)
        record("J03", "jiyuu_c.jsonl", successful[:-2] + [ev("結果", {"ok": False}, 1), ev("結果", {"答え": "終わりまでできませんでした"}, 2)])
        record("J04", "jiyuu_d.jsonl", successful[:-2] + [ev("提案", {"道具": "read"}), ev("結果", {"ok": True})])
        cards = kyoukun.atsumeru([root])
        check(len(cards) == 1 and cards[0]["数"] == 2, "成功のみ集計して知らせをまとめる")
        check("<場所>" in cards[0]["知らせ"] and "<ファイル>" not in cards[0]["頼み"] and "報告.txt" not in cards[0]["知らせ"], "場所とファイル名の置換")
        check(cards[0]["道具"] == "write", "知らせ後に提案された道具")
        check(kyoukun._generalize("glob **/old.tmp", 160) == "glob **/<ファイル>", "glob内のファイル名置換")
        excluded = kyoukun.atsumeru([root], {"J01", "J02", "J03", "J04"})
        check(excluded == [], "jogai除外")
        selected = kyoukun.erabu("デスクトップに報告を書いてください", cards)
        check(len(selected) == 1 and selected[0]["数"] == 2, "2-gram類似選択")
        check(not kyoukun.erabu("買い物の天気を知りたい", cards), "閾値")
        saved = Path(temp) / "cards.json"
        saved.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
        check("前に似た頼みで門番に直されたこと:" in kyoukun.soeru("デスクトップに報告を書いて", saved), "soeru")
        broken = Path(temp) / "broken.json"
        broken.write_text("{", encoding="utf-8")
        check(kyoukun.soeru("報告を書いて", broken) == "", "壊れたカードファイル")
        left = kyoukun.atsumeru([root], {"J01", "J03", "J04"})
        check(len(left) == 1 and left[0]["数"] == 1, "特定J番号のみ除外")

    print(f"kyoukun 自己試験: {passed}/{total} PASS")


if __name__ == "__main__":
    main()
