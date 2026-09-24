#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grammar.py -- 日本語の文法で、文の骨組みを取り出す

  いままでは、文の中に「片付」という字があるかどうかだけを見ていた。
  それだと「AをBに移動して」の A と B が区別できず、
  手書きの正規表現でその場しのぎをしていた。

  ここでは、国語の授業で習うやり方をそのまま使う。

    ① 文節に切る       … 「机の上の / 去年の / 写真を / 片付けて」
    ② 述語を見つける   … 文のいちばん後ろの、動きを表す言葉 =「片付けて」
    ③ 格を割りふる     … 助詞を見て、それぞれが述語の何にあたるかを決める

  ③ で使う「格」は、こういう対応：

    ヲ格 (を)     何を        写真を 片付けて
    ニ格 (に・へ) どこへ／いつ  フォルダに 入れて
    デ格 (で)     どこで／何で  デスクトップで 探して
    カラ格(から)  どこから      ダウンロードから 移して
    ノ格 (の)     どんな        去年の 写真
    ハ・ガ格      主題          写真は 何個

  この考え方は「格文法」といって、1968年からある古い理論。
  日本語の解析では、いまでも基礎になっている。
"""
import re

# ------------------------------------------------------------------
# 助詞の表。長いものから先に見る（「までに」を「まで」で切らないため）
# ------------------------------------------------------------------
PARTICLES = [
    ("までに", "マデ"), ("からは", "カラ"), ("には", "ニ"), ("では", "デ"),
    ("への", "ニ"), ("との", "ト"), ("から", "カラ"), ("まで", "マデ"),
    ("より", "ヨリ"), ("だけ", "ダケ"), ("など", "ナド"), ("ばかり", "ダケ"),
    ("を", "ヲ"), ("に", "ニ"), ("へ", "ニ"), ("で", "デ"),
    ("の", "ノ"), ("は", "ハ"), ("が", "ガ"), ("と", "ト"), ("や", "ヤ"),
    ("も", "モ"),
]

# 文の切れ目。ファイル名の中の「.」で切らないよう、
# 前後が英数字の「.」は切れ目にしない
_CUT = re.compile(r"[、。，，\s　！？!?]+|(?<![A-Za-z0-9])[.,](?![A-Za-z0-9])")

# 述語らしい語尾。ここで終わっていれば動きを表す言葉とみなす
_PRED_TAIL = (
    "して", "しといて", "してね", "してよ", "しろ", "せよ", "します",
    "って", "て", "で", "た", "だ", "る", "う", "い", "よ", "ね",
    "ください", "くれ", "ほしい", "たい", "みて", "ちょうだい",
)

# 打ち消し。「〜ない」「〜ません」「〜ず」
_NEG = re.compile(r"(ない|ません|なかった|ずに|ないで|除いて|のぞいて|以外|いがい)")

# 「〜以外」「〜を除く」は、ヲ格ではなく「のぞく」という別あつかい
_EXCEPT_TAIL = re.compile(r"(以外|いがい|を除|をのぞ|じゃない|ではない)")


def _split_particle(chunk):
    """ひとかたまりを「内容 + 助詞」に切る。助詞が無ければ (内容, None)"""
    for p, case in PARTICLES:
        if chunk.endswith(p) and len(chunk) > len(p):
            return chunk[:-len(p)], case, p
    return chunk, None, None


def bunsetsu(text, protect=()):
    """文を文節に切る。

    protect には「切ってはいけない語」を渡す（ファイル名など）。
    渡さないと「旅行1.jpg」が 旅行1 と jpg に割れてしまう。

    戻り値: [{"語": 内容, "格": ヲ/ニ/…, "助詞": を/に/…, "生": もとの形}, …]
    """
    protect = sorted([p for p in protect if p], key=len, reverse=True)
    out = []
    for piece in _CUT.split(text):
        piece = piece.strip()
        if not piece:
            continue
        # ひとつの塊の中に助詞が複数あるので、助詞のたびに区切る
        buf = ""
        i = 0
        while i < len(piece):
            # 守る語の途中では、絶対に切らない
            skipped = False
            for keep in protect:
                if piece.startswith(keep, i):
                    buf += keep
                    i += len(keep)
                    skipped = True
                    break
            if skipped:
                continue
            hit = None
            for p, case in PARTICLES:
                if piece.startswith(p, i) and buf:
                    hit = (p, case)
                    break
            if hit:
                p, case = hit
                out.append({"語": buf, "格": case, "助詞": p, "生": buf + p})
                buf = ""
                i += len(p)
            else:
                buf += piece[i]
                i += 1
        if buf:
            out.append({"語": buf, "格": None, "助詞": None, "生": buf})
    return out


def find_predicate(chunks):
    """述語（文のいちばん後ろの、動きを表す言葉）を探す。

    後ろから見て、助詞が付いていない塊で、述語らしい語尾のものを採る。
    """
    for c in reversed(chunks):
        if c["格"] is not None:
            continue
        w = c["語"]
        if len(w) >= 2 and w.endswith(_PRED_TAIL):
            return c
    # 語尾で決まらなければ、いちばん後ろの助詞なしの塊
    for c in reversed(chunks):
        if c["格"] is None and len(c["語"]) >= 2:
            return c
    return None


# ------------------------------------------------------------------
# 述語ごとの「格フレーム」
#   その述語が、どの格を何として受け取るか
# ------------------------------------------------------------------
FRAMES = {
    # 動作      ヲ格の役      ニ格の役      デ格の役
    "移動":   {"ヲ": "対象", "ニ": "行き先", "デ": "場所", "カラ": "場所"},
    "数える": {"ヲ": "対象", "ニ": "場所",   "デ": "場所", "カラ": "場所"},
    "一覧":   {"ヲ": "対象", "ニ": "場所",   "デ": "場所", "カラ": "場所"},
    "作成":   {"ヲ": "対象", "ニ": "場所",   "デ": "場所"},
    "ごみばこ": {"ヲ": "対象", "ニ": "場所", "デ": "場所"},
    "改名":   {"ヲ": "対象", "ニ": "新しい名前", "デ": "場所"},
    "重複":   {"ヲ": "対象", "ニ": "場所",   "デ": "場所"},
    "大きさ": {"ヲ": "対象", "ニ": "場所",   "デ": "場所"},
    "HTML":   {"ヲ": "対象", "ニ": "場所",   "デ": "場所"},
}
# 述語が分からないときの、無難な割りあて
DEFAULT_FRAME = {"ヲ": "対象", "ニ": "場所", "デ": "場所", "カラ": "場所"}


# 「PDFというフォルダに」= PDF が名前、フォルダに が役
_IU = re.compile(r"^(?:いう|言う|いった|言った)(.*)$")
# 「という」が丸ごと次の文節の頭に来た形（間に空白があるとこうなる）
_TOIU_HEAD = re.compile(r"^(?:という|といった|と言う|と言った)(.*)$")


def _merge_toiu(chunks):
    """「X という Y に」を1つにまとめる。

    そのままだと X が ト格、「いうY」が ニ格になってしまい、
    行き先の名前が「いうフォルダ」になっていた。

    ★ 2026-09-06 に ② を足した。
      「デスクトップに 試験用 というフォルダをつくる」のように
      **間に空白がある**と「試験用」に助詞が付かず、ト格にならない。
      すると「という」が丸ごと次の文節の頭に来て、ヲ格が「というフォルダ」になる。
      その結果、**本物のデスクトップに「というフォルダ」という名前の
      フォルダが出来た**（実際に起きた）。
      しかも一度できると、それが「実在するフォルダ名」として最優先で
      守られるので、**間違いが正解として固定される**。
    """
    out, i = [], 0
    while i < len(chunks):
        c = chunks[i]
        nxt = chunks[i + 1] if i + 1 < len(chunks) else None
        if nxt:
            # ① 「PDFと / いうフォルダに」… と が助詞として切れた形
            if c["格"] == "ト":
                m = _IU.match(nxt["語"])
                if m:
                    out.append({"語": c["語"], "格": nxt["格"],
                                "助詞": nxt["助詞"],
                                "生": c["語"] + "という" + nxt["語"],
                                "名前": True, "種別": m.group(1) or None})
                    i += 2
                    continue
            # ② 「試験用 / というフォルダを」… と が切れなかった形
            m2 = _TOIU_HEAD.match(nxt["語"])
            # 「「試験用」というフォルダ」… 括弧は名前の一部ではないので外す。
            # 外さないと「「試験用」」という名前のフォルダが出来てしまう。
            namae = c["語"]
            for a, b in ("「」", "『』", '""', "''", "（）", "()"):
                if len(namae) >= 3 and namae[0] == a and namae[-1] == b:
                    namae = namae[1:-1].strip()
                    break
            if (m2 and c["格"] in (None, "主題", "ノ")
                    and 1 <= len(namae) <= 24
                    and namae not in ("それ", "これ", "あれ", "そう", "こう")):
                kind = m2.group(1) or None
                out.append({"語": namae, "格": nxt["格"], "助詞": nxt["助詞"],
                            "生": namae + "という" + (kind or ""),
                            "名前": True, "種別": kind})
                i += 2
                continue
        out.append(c)
        i += 1
    return out


def _join_no_chain(chunks):
    """「机 の 上 の 写真」の「机の上」をひとまとまりに戻す。

    助詞で切ると 机／上 に割れてしまうが、
    「机の上」で1つの場所を指しているので、つないだ形も残しておく。
    """
    out, i = [], 0
    while i < len(chunks):
        c = chunks[i]
        if c["格"] == "ノ" and i + 1 < len(chunks):
            nxt = chunks[i + 1]
            joined = c["語"] + "の" + nxt["語"]
            # つないだ形も候補として持たせる（カード引きが見つけやすいように）
            c = dict(c, 連結=joined)
        out.append(c)
        i += 1
    return out


def analyze(text, protect=()):
    """文を読んで、骨組みを返す。

    戻り値:
      {"述語": str|None,
       "格":   {"ヲ": [語, …], "ニ": [語, …], …},
       "修飾": [語, …],        ← 「〜の」で前に付いていたもの
       "除く": 語|None,        ← 「〜以外」
       "打ち消し": bool}
    """
    chunks = _join_no_chain(_merge_toiu(bunsetsu(text, protect)))
    pred = find_predicate(chunks)

    cases = {}
    modifiers = []
    excepted = None
    named = []

    for c in chunks:
        if c is pred:
            continue
        w, case = c["語"], c["格"]
        if not w:
            continue
        if _EXCEPT_TAIL.search(c["生"]) or w.endswith(("以外", "いがい")):
            excepted = re.sub(r"(以外|いがい)$", "", w) or None
            continue
        if c.get("名前"):
            named.append({"名前": w, "役": case, "種別": c.get("種別")})
            cases.setdefault(case, []).append(w)
            continue
        if case == "ノ":
            modifiers.append(w)          # 「机の上の写真」の「机の上」
            if c.get("連結"):
                modifiers.append(c["連結"])
            continue
        if case in (None, "ハ", "ガ", "モ", "ダケ", "ナド"):
            # 主題や強調。役としては「対象」の候補にしておく
            if w and w != (pred or {}).get("語"):
                cases.setdefault("主題", []).append(w)
            continue
        cases.setdefault(case, []).append(w)

    return {
        "述語": pred["語"] if pred else None,
        "格": cases,
        "修飾": modifiers,
        "除く": excepted,
        "打ち消し": bool(_NEG.search(text)),
        "名前": named,
        "文節": chunks,
    }


def roles(text, act=None):
    """格を「役」に読みかえて返す。

    act（動作）が分かっていれば、その述語の格フレームを使う。
    分からなければ無難な割りあてを使う。

    戻り値: {"対象": [語…], "行き先": [語…], "場所": [語…], "修飾": [語…], …}
    """
    a = analyze(text)
    frame = FRAMES.get(act, DEFAULT_FRAME)
    out = {}
    for case, words in a["格"].items():
        role = frame.get(case)
        if role:
            out.setdefault(role, []).extend(words)
    if a["修飾"]:
        out["修飾"] = list(a["修飾"])
    if a["格"].get("主題"):
        out.setdefault("主題", []).extend(a["格"]["主題"])
    if a["除く"]:
        out["除く"] = [a["除く"]]
    for n in a.get("名前", []):
        out.setdefault("名前", []).append(n["名前"])
    out["_述語"] = a["述語"]
    out["_打ち消し"] = a["打ち消し"]
    return out


def explain(text):
    """画面に見せる用。どう読んだかを人が確かめられるように"""
    a = analyze(text)
    lines = [f"  述語 : {a['述語'] or '（見つからない）'}"]
    for c in a["文節"]:
        if c is None:
            continue
        mark = f"{c['助詞']}（{c['格']}格）" if c["格"] else "—"
        lines.append(f"  {c['語']:<12} {mark}")
    for n in a.get("名前", []):
        lines.append(f"  名前 : {n['名前']}"
                     + (f"（{n['種別']}）" if n["種別"] else ""))
    if a["除く"]:
        lines.append(f"  除く : {a['除く']}")
    if a["打ち消し"]:
        lines.append("  打ち消しあり")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    for t in (sys.argv[1:] or [
            "机の上の去年の写真を片付けて",
            "デスクトップのメモ.txtをPDFというフォルダに入れて",
            "デスクトップの画像以外を数えて",
            "ダウンロードから書類をデスクトップに移して",
    ]):
        print(f"\n入力: {t}")
        print(explain(t))
