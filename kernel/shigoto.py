#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shigoto.py -- 「頭脳が1回でプログラムを書き、カーネルが安全な部屋で走らせて、成果物を届ける」道具。

  ★ なぜこの形か（2026-09-12 実測）
    道具の輪（頭脳が道具を選ぶ → 結果 → また選ぶ）は、この機械では 1回 40〜70秒 × 最大6回 = 1課題 76〜409秒。
    しかも頭脳は道具を自分から使わない。→ **輪をまわさない。** 頭脳の仕事は「短いプログラムを1回書く」だけ。
    数え上げ（kazoeru.py）でこの型が当たった。CSVの集計・文章の作成・HTML・整理も同じ型で済む。

  ★ 安全（道具より先に決めること）
    ・走るのは coderun の使い捨ての部屋。書けるのは部屋の中だけ。ネットに出ない。
    ・成果物は部屋の「成果物」フォルダに書かせ、**カーネルが** ~/Desktop/カーネルの成果物/日時/ へ運ぶ。
      あなたのファイルには **1バイトも触れない**（読むだけ。上書きも移動もしない）。
    ・読んでよいのは Desktop / Downloads / 書類 と、頼み文で名指しされた道（📄📁で選んだもの）。
    ・失敗したら エラーを見せて1回だけ書き直させる（考える→走らせる→結果を見る→直す の最小の輪）。
"""
from __future__ import annotations
import os, re, sys, time, shutil, json, io

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

HOME = os.path.expanduser("~")
YOMERU = [os.path.join(HOME, d) for d in ("Desktop", "Downloads", "Documents")]
TODOKE = os.path.join(HOME, "Desktop", "カーネルの成果物")

# この道に入る合図: 表・文章・HTML・整理 の仕事で、対象の道かファイルの気配があるとき
_AIZU = re.compile(r"csv|excel|xlsx|エクセル|表|集計|合計|平均|並べ替え|html|ページ|作って|書いて|まとめて|一覧に|抜き出|数えて|変換|直して", re.I)
_MICHI = re.compile(r"(/Users/[^\s　'\"]+|~/[^\s　'\"]+)")

_KIKEN = re.compile(r"\b(subprocess|os\.system|os\.remove|os\.unlink|shutil\.rmtree|shutil\.move|os\.rename|socket|urllib|requests|http\.client|eval\s*\(|exec\s*\(|__import__)")

SYSTEM = ("あなたは Python を書く係。頼まれた仕事をする **短い Python プログラム** を1つ書いてください。"
          "考えを書かず、```python と ``` で囲んだプログラムだけを書くこと。"
          "読んでよいファイルは、頼み文にある道だけ。作るものは 変数 OUT のフォルダの中に保存すること。"
          "標準ライブラリ（csv, json, re, pathlib, statistics, collections, datetime）だけを使う。"
          "最後に、何をしたかを print で1〜3行、日本語で出すこと。")

_FENCE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)


_TSUKURU = re.compile(r"(html|ページ|csv|表|ファイル|文章|メモ|一覧|台本|手紙|レポート|json|テキスト).{0,12}(作っ|作成|書い|まとめ|変換|出力|生成)|(作っ|書い|まとめ).{0,6}(html|ページ|csv|表|ファイル|文章|メモ|一覧)", re.I)


def aizu(text: str) -> bool:
    """この道に入るか: (道が名指しされていて 表・文章の仕事) か (何かを作る頼み)"""
    t = text or ""
    if _MICHI.search(t) and _AIZU.search(t):
        return True
    if "csv" in t.lower() and _AIZU.search(t):
        return True
    return bool(_TSUKURU.search(t))


def _michi(text: str) -> list[str]:
    """頼み文の中の道を拾い、読んでよい場所の中のものだけ返す"""
    out = []
    for m in _MICHI.findall(text or ""):
        p = os.path.realpath(os.path.expanduser(m.rstrip("。、,.)）")))
        if any(p == y or p.startswith(y + os.sep) for y in YOMERU) and os.path.exists(p):
            out.append(p)
    return out


def _anzen(src: str) -> str | None:
    if not src or len(src) > 8000:
        return "長すぎる"
    if _KIKEN.search(src):
        return "許していない書きかた（消す・動かす・ネット・外のプログラム）"
    return None


def _kaku(toi: str, michi: list[str], out_dir: str, mae: str | None, error: str | None, timeout: int,
          betsu: bool = False, fukasa: int = 0) -> tuple[str | None, str]:
    import teachers as T
    p = ["仕事: " + toi.strip()]
    if betsu:
        p.append("（さっきとは **別の書き方** で。使う関数やループの組み方を変えること。答えは同じになるはず）")
    if michi:
        p.append("読んでよい道:\n" + "\n".join("  " + m for m in michi))
        # ★ 頭脳は中身を見ずにプログラムを書いていた（列の名前や型を知らないまま）。
        #   「個数が3より多い行」を「列が3つより多い行」と読むような取り違えが 2/10 出た。
        #   → 文字のファイルは 先頭5行 を見せる。列の名前と型が分かれば、取り違えは減る。
        for m in michi:
            try:
                if os.path.isfile(m) and os.path.getsize(m) < 1_000_000:
                    with io.open(m, encoding="utf-8", errors="replace") as f:
                        atama = [next(f).rstrip("\n") for _ in range(5)]
            except StopIteration:
                pass
            except Exception:
                continue
            else:
                p.append("%s の先頭:\n" % os.path.basename(m) + "\n".join("  " + a[:200] for a in atama))
    # ★ 「OUT はフォルダ」を明記。open(OUT, "w") と書いて IsADirectoryError で2回止まった課題があった（表 #3）。
    p.append("OUT = %r  # フォルダ。作るものは os.path.join(OUT, \"名前\") に保存する。OUT そのものを open しない" % out_dir)
    if mae and error:
        if "IsADirectoryError" in error:
            error += "\n（OUT はフォルダです。open(OUT) ではなく open(os.path.join(OUT, \"ファイル名\"), \"w\") に直すこと）"
        p.append("さっきのプログラムはこのエラーで止まった。直して書き直すこと:\n" + error[:700])
        p.append("さっきのプログラム:\n```python\n" + mae[:2500] + "\n```")
    r = T.ask_one("local:main", "\n\n".join(p), system=SYSTEM, timeout=timeout, fukasa=fukasa)
    if r.get("error"):
        return None, "頭脳のエラー: " + r["error"]
    text = r.get("text") or ""
    m = _FENCE.findall(text)
    src = m[-1].strip() if m else None
    if not src:
        # teachers は返事の ``` を取り除いて返す。フェンスが無ければ本文がそのままプログラム
        if re.search(r"^\s*(import |from |with open|print\()", text, re.M):
            src = text.strip()
    if not src:
        return None, "プログラムが取れなかった: %r" % text[:120]
    ng = _anzen(src)
    if ng:
        return None, "危ない: " + ng
    # OUT の定義を先頭に必ず入れる（頭脳が書き忘れても部屋の外に書けない）
    src = "OUT = %r\nimport os; os.makedirs(OUT, exist_ok=True)\n" % out_dir + src
    return src, ""


_KAZU_TOI = re.compile(r"何行|何件|いくつ|何個|何通り|何人|何回|合計|平均|最大|最小|数えて|いくら")
_KAZU = re.compile(r"(?<![\d.])-?\d+(?:\.\d+)?(?![\d.])")


def _kazu_dake(text: str) -> list[str]:
    """報告の中の数。ただし「3より多い」「5以上」のような条件の写しは数えない"""
    t = re.sub(r"\d+(?:\.\d+)?(?:より|以上|以下|未満|桁|列目|行目|番目)", " ", text or "")
    return _KAZU.findall(t)


def suru(toi: str, iu=None, timeout: int = 150) -> dict:
    """仕事をする。戻り: {"できた": bool, "報告": str, "成果物": [道], "経過": [..], "ミリ秒": int, "確かめ": str}
    ★ 数を答える仕事は、書き方を変えた2本目を走らせて **数が一致したときだけ「確かめた」**（kazoeru と同じ型）。
      実測: 1本だけだと 表の課題で「7行」（正しくは3）「個数の合計→行数」のような取り違えが 10問中2問出た。"""
    r1 = _ichido(toi, iu, timeout, betsu=False)
    if not _KAZU_TOI.search(toi) or not r1["できた"]:
        r1["確かめ"] = "" if not r1["できた"] else "作るだけ（確かめ無し）"
        return r1
    k1 = _kazu_dake(r1["報告"] + " " + _naka(r1["成果物"]))
    if not k1:
        r1["確かめ"] = "数が出ていない"
        return r1
    say = iu or (lambda s: None)
    say("  仕事: 別の書き方でもう1本（数を確かめる）")
    r2 = _ichido(toi, None, timeout, betsu=True)
    k2 = _kazu_dake(r2["報告"] + " " + _naka(r2["成果物"])) if r2["できた"] else []
    if k2 and (k1[-1] == k2[-1] or set(k1) & set(k2)):
        r1["確かめ"] = "別の書き方の2本が一致"; r1["ミリ秒"] += r2["ミリ秒"]
        return r1
    say("  仕事: 食い違い（%s / %s）→ 深く考えて3本目" % (k1[-1:], k2[-1:]))
    r3 = _ichido(toi, None, timeout, betsu=False, fukasa=2)
    k3 = _kazu_dake(r3["報告"] + " " + _naka(r3["成果物"])) if r3["できた"] else []
    for ra, ka, rb, kb in ((r1, k1, r3, k3), (r2, k2, r3, k3)):
        if ka and kb and ka[-1] == kb[-1]:
            ra["確かめ"] = "3本中2本が一致"; ra["ミリ秒"] = r1["ミリ秒"] + r2["ミリ秒"] + r3["ミリ秒"]
            return ra
    r1["できた"] = False
    r1["確かめ"] = "3本とも食い違った（%s / %s / %s）。自信がない" % (k1[-1:], k2[-1:], k3[-1:])
    r1["報告"] = "答えが定まりませんでした（%s）。問題の書き方を少し変えてもらえますか。" % r1["確かめ"]
    r1["ミリ秒"] = r1["ミリ秒"] + r2["ミリ秒"] + r3["ミリ秒"]
    return r1


def _naka(paths):
    s = ""
    for p_ in paths or []:
        try:
            s += io.open(p_, encoding="utf-8").read()[:3000]
        except Exception:
            pass
    return s


def _ichido(toi: str, iu=None, timeout: int = 150, betsu: bool = False, fukasa: int = 0) -> dict:
    import coderun, tempfile
    t0 = time.time()
    say = iu or (lambda s: None)
    michi = _michi(toi)
    room = tempfile.mkdtemp(prefix="shigoto_")
    out_dir = os.path.join(room, "成果物")
    keika, src, err = [], None, None
    for kai in (1, 2):
        say("  仕事: プログラムを書かせる（%d回目）" % kai)
        src, ng = _kaku(toi, michi, out_dir, src, err, timeout, betsu=betsu, fukasa=fukasa)
        if not src:
            keika.append("%d回目: %s" % (kai, ng)); say("    " + ng)
            break
        # force=True: coderun の「書き込みは危ない」検査は飛ばす。書ける場所は sandbox-exec が部屋の中に縛っている。
        #   本当に危ないもの（消す・動かす・ネット・外のプログラム）は上の _anzen で先に落としてある。
        try:
            r = coderun.run(src, lang="python", timeout=60, force=True)
        except Exception as e:
            r = {"出力": "", "エラー": "走らせられなかった: %s" % e}
        out = (r.get("出力") or "").strip(); err = (r.get("エラー") or "").strip()
        keika.append("%d回目: %s" % (kai, (out or err)[:300]))
        if not err or out:
            break
        say("    エラー → 直させる: " + err.splitlines()[-1][:80] if err else "")
    # 成果物を運ぶ（作るだけ。上書きしない）
    seika = []
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        dst = os.path.join(TODOKE, time.strftime("%Y-%m-%d_%H%M%S"))
        os.makedirs(dst, exist_ok=True)
        for n in sorted(os.listdir(out_dir)):
            s_ = os.path.join(out_dir, n)
            if os.path.isfile(s_):
                shutil.copy2(s_, os.path.join(dst, n)); seika.append(os.path.join(dst, n))
    shutil.rmtree(room, ignore_errors=True)
    dekita = bool(seika) or (bool(src) and not err)
    houkoku = (out if src else "") or ("" if dekita else "できませんでした")
    return {"できた": dekita, "報告": houkoku[:600], "成果物": seika, "経過": keika,
            "ミリ秒": int((time.time() - t0) * 1000), "エラー": (err or "")[:300] if not dekita else ""}


if __name__ == "__main__":
    q = " ".join(sys.argv[1:])
    r = suru(q, iu=print)
    print(json.dumps(r, ensure_ascii=False, indent=1))
