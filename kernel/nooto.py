#!/usr/bin/env python3
"""nooto.py — 学習ノート。事前学習で読んだ記事ごとに「要点・面白さ・つながり」を書いて、知識を自分の物にする。

10/3 本人:「事前学習で習ったことをパッと出せばいいだけなのに、知識を探してばかりで意味が無い」。
  記事を箱に貯めるだけで、読んだ中身を消化していなかった。人が本を読んでノートを取るのと同じことをする。
- 書き手: NVIDIA の API（公開の Wikipedia の文だけを送る。本人のファイルは送らない）。鍵が無ければ何もしない
  （~/.nvidia.env。キーチェーンの承認が出る道は使わない＝裏で窓を出さない）。
- 1回で4記事をまとめて頼む（呼ぶ回数を減らす）。
- 使い道: 「何が面白かった？」は面白さの高いノートから答える。ふつうの問いも、合うノートの要点を先に添える。

  python3 nooto.py umeru --kazu 100    … ノートの無い記事を100件ぶん埋める
  python3 nooto.py miru                … 面白さの高い順に10件
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
MODEL = os.environ.get("KERNEL_NOOTO_MODEL", "ultra")   # 10/3: super と gpt-oss は 410（提供終了）
BATCH = 4


def _db_path():
    return Path(os.environ.get("KERNEL_GAKUSHUU_DIR", Path.home() / "Library/Application Support/kernel-ai/gakushuu")) / "chishiki.sqlite3"


def _open(path=None):
    db = sqlite3.connect(path or _db_path(), timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS nooto(title TEXT PRIMARY KEY, youten TEXT NOT NULL, omoshirosa INTEGER NOT NULL,"
               " tsunagari TEXT NOT NULL, model TEXT NOT NULL, added TEXT NOT NULL)")
    return db


def _ask_default(prompt):
    import nvidia
    if not nvidia.key():   # 鍵ファイルが無い時は、承認の窓が出る道（nv）へ行かずに止める
        raise RuntimeError("NVIDIA の鍵がありません")
    return nvidia.ask(prompt, model=MODEL, max_tokens=6000, timeout=180, temperature=0.3)


def _prompt(items, known):
    parts = [f"【記事{i}】題: {title}\n{text[:1500]}" for i, (title, text) in enumerate(items, 1)]
    return ("次の百科事典の記事を読み、記事ごとに学習ノートを書いてください。\n"
            "- 要点: 記事に書いてある事実だけで、2〜3文の日本語。記事に無いことは足さない。\n"
            "- 面白さ: 1〜5（意外さ・ほかの知識とのつながり・役に立つか。人名や作品の一覧のような記事は低め）\n"
            "- つながり: 下の『既に読んだ題』から、内容が本当に関係する題を0〜3個（無理に選ばない）\n"
            "答えは JSON の配列だけ: [{\"題\": \"…\", \"要点\": \"…\", \"面白さ\": 3, \"つながり\": [\"…\"]}]\n\n"
            "既に読んだ題: " + "、".join(known[:60]) + "\n\n" + "\n\n".join(parts))


def _parse(raw, titles, known):
    rows = None
    # 考えの文が前に付くことがある（ultra・fast）。後ろから、題を含む JSON の配列を探す。
    for match in reversed(list(re.finditer(r"\[\s*\{.*?\}\s*\]", raw or "", re.S))):
        try:
            rows = json.loads(match.group(0))
            break
        except ValueError:
            continue
    if rows is None:
        return []
    known_set, out = set(known), []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("題") not in titles:
            continue
        youten = str(row.get("要点", "")).strip()[:300]
        try:
            score = max(1, min(5, int(row.get("面白さ", 3))))
        except (TypeError, ValueError):
            score = 3
        links = [t for t in row.get("つながり", []) if isinstance(t, str) and t in known_set and t != row["題"]][:3]
        if youten:
            out.append((row["題"], youten, score, links))
    return out


def umeru(kazu=BATCH, ask=None, path=None, wait=1.0, workers=3):
    """ノートの無い記事を kazu 件まで埋める。書けた数を返す。
    10/3: 1回（4記事）に約80秒かかり、全部で14時間になるので、3つ同時に頼む（NVIDIA の無料枠は毎分40回まで）。"""
    from concurrent.futures import ThreadPoolExecutor
    ask = ask or _ask_default
    db = _open(path)
    done = 0
    try:
        known = [r[0] for r in db.execute("SELECT title FROM nooto ORDER BY added DESC LIMIT 200")]
        while done < kazu:
            items = db.execute("SELECT c.title, c.text FROM chishiki c WHERE c.title NOT IN (SELECT title FROM nooto)"
                               " AND length(c.text) >= 300 LIMIT ?", (min(BATCH * workers, kazu - done),)).fetchall()
            if not items:
                break
            groups = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]

            def one(group):
                try:
                    return group, _parse(ask(_prompt(group, known)), {t for t, _ in group}, known)
                except Exception:
                    return group, None   # つながらない時は印を付けず、次の回にもう一度
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(one, groups))
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            failed = 0
            for group, notes in results:
                if notes is None:
                    failed += 1
                    continue
                for title, youten, score, links in notes:
                    db.execute("INSERT OR REPLACE INTO nooto VALUES (?,?,?,?,?,?)",
                               (title, youten, score, json.dumps(links, ensure_ascii=False), MODEL, stamp))
                    known.insert(0, title)
                for title in {t for t, _ in group} - {n[0] for n in notes}:   # 書けなかった記事は印だけ付け、同じ所で止まらない
                    db.execute("INSERT OR IGNORE INTO nooto VALUES (?,?,?,?,?,?)", (title, "", 0, "[]", MODEL, stamp))
            db.commit()
            if failed == len(groups):
                break   # 全部つながらない（鍵・ネット・枠切れ）。今回はやめる
            done += len(items)
            time.sleep(wait)
    finally:
        db.close()
    return done


def ichiban(n=5, path=None):
    """面白さの高いノート（同点は新しい順）。"""
    try:
        db = _open(path)
        rows = db.execute("SELECT title, youten, omoshirosa FROM nooto WHERE youten != ''"
                          " ORDER BY omoshirosa DESC, added DESC LIMIT ?", (n,)).fetchall()
        db.close()
        return rows
    except sqlite3.Error:
        return []


def au(terms, n=3, path=None):
    """問いの言葉が題に入っているノート。"""
    terms = [t for t in terms if len(t) >= 2][:20]
    if not terms:
        return []
    try:
        db = _open(path)
        rows = db.execute("SELECT title, youten FROM nooto WHERE youten != ''").fetchall()
        db.close()
    except sqlite3.Error:
        return []
    hits = [(sum(t in title for t in terms), title, youten) for title, youten in rows]
    return [(title, youten) for score, title, youten in sorted(hits, reverse=True) if score][:n]


def kazu(path=None):
    try:
        db = _open(path)
        total = db.execute("SELECT count(*) FROM chishiki").fetchone()[0]
        written = db.execute("SELECT count(*) FROM nooto WHERE youten != ''").fetchone()[0]
        db.close()
        return written, total
    except sqlite3.Error:
        return 0, 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("umeru"); p.add_argument("--kazu", type=int, default=40)
    sub.add_parser("miru")
    args = parser.parse_args()
    if args.cmd == "umeru":
        print("書いた", umeru(args.kazu), "件｜ノート/記事", kazu())
    else:
        for title, youten, score in ichiban(10):
            print(score, title, "—", youten[:80])


if __name__ == "__main__":
    main()
