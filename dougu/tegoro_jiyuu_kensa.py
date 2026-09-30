#!/usr/bin/env python3
"""J系の準備・採点だけを空答えで検査する。モデル・ネットワークは使わない。"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from unittest.mock import patch

import tegoro


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", default="", help="IDをカンマ区切りで指定（既定は全26問）")
    args = parser.parse_args()
    rows = tegoro._jiyuu_rows(args.id)
    if not rows:
        parser.error("該当する問題がありません")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("IDが重複しています")
    passed = 0
    # J09の採点だけは実Macを読むため、空答えに対するFalseへ置換する。
    with tempfile.TemporaryDirectory(prefix="jiyuu-junbi-") as temporary, \
            patch.object(tegoro, "_volume_matches_answer", return_value=False):
        for row in rows:
            home = Path(temporary) / row["id"] / "home"
            home.mkdir(parents=True)
            baseline = tegoro._prepare_jiyuu(home, row)
            ok = tegoro._check_jiyuu(home, row, "", [], [], home / "opened.txt", baseline)
            if ok:
                raise AssertionError(f'{row["id"]}: 未実行なのに合格')
            print(f'{row["id"]}: 準備OK / 空答えFAIL（正常）')
            passed += 1
    print(f"準備・判定: {passed}/{len(rows)}問、モデル・通信・実Mac操作なし")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
