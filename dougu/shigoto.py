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
import os, re, sys, time, shutil, json

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


def _kaku(toi: str, michi: list[str], out_dir: str, mae: str | None, error: str | None, timeout: int) -> tuple[str | None, str]:
    import teachers as T
    p = ["仕事: " + toi.strip()]
    if michi:
        p.append("読んでよい道:\n" + "\n".join("  " + m for m in michi))
    p.append("OUT = %r  # 作るものはこの中に" % out_dir)
    if mae and error:
        p.append("さっきのプログラムはこのエラーで止まった。直して書き直すこと:\n" + error[:600])
        p.append("さっきのプログラム:\n```python\n" + mae[:2500] + "\n```")
    r = T.ask_one("local:main", "\n\n".join(p), system=SYSTEM, timeout=timeout, fukasa=0)
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


def suru(toi: str, iu=None, timeout: int = 150) -> dict:
    """仕事をする。戻り: {"できた": bool, "報告": str, "成果物": [道], "経過": [..], "ミリ秒": int}"""
    import coderun, tempfile
    t0 = time.time()
    say = iu or (lambda s: None)
    michi = _michi(toi)
    room = tempfile.mkdtemp(prefix="shigoto_")
    out_dir = os.path.join(room, "成果物")
    keika, src, err = [], None, None
    for kai in (1, 2):
        say("  仕事: プログラムを書かせる（%d回目）" % kai)
        src, ng = _kaku(toi, michi, out_dir, src, err, timeout)
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
