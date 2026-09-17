# -*- coding: utf-8 -*-
"""こよみ ── 日付の計算を、頭脳に考えさせずに 暦で答える。

  「2026年1月6日の 29日後は 何月何日」 → 2月4日
  「2026年1月11日は 日曜日です。その 50日後は 何曜日」 → 月曜日（言われた曜日から数える）
  「明日は何曜日」「来週の金曜日は何日」「3日後は何月何日」「今日から 10月1日まで何日」

★ なぜ要るか（2026-09-17 の実測）: 120問の物差しで 深さ0 が落とした3問は 全部「○日後」の計算。
  頭脳は 1日ずれる（12月14日 → 12月15日、月 → 火）。深さ2 なら合うが 1問 43秒。
  暦は 0秒で間違えない。**頭脳が苦手なことは 道具に渡す**（掛け算を電卓に渡したのと同じ）。
  文の形が分からなければ None を返し、いつも通り頭脳に回す。
"""
from __future__ import annotations
import datetime as _dt
import re

_YOUBI = "月火水木金土日"
_KAN = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _kazu(s: str) -> int | None:
    """「15」「十五」「二十」→ 15/15/20。"""
    s = (s or "").strip().translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if s.isdigit():
        return int(s)
    n, keta = 0, 0
    for ch in s:
        if ch in _KAN:
            keta = _KAN[ch]
        elif ch == "十":
            n += (keta or 1) * 10; keta = 0
        elif ch == "百":
            n += (keta or 1) * 100; keta = 0
        else:
            return None
    return n + keta if s else None

_SUJI = r"([0-9０-９]+|[〇零一二三四五六七八九十百]+)"
_NEN_TSUKI_HI = re.compile(r"([0-9０-９]{4})\s*年\s*([0-9０-９]{1,2})\s*月\s*([0-9０-９]{1,2})\s*日")
_TSUKI_HI = re.compile(r"(?<![0-9０-９年])([0-9０-９]{1,2})\s*月\s*([0-9０-９]{1,2})\s*日")
_OFFSET = re.compile(_SUJI + r"\s*(日|週間|週|か月|ヶ月|ヵ月|カ月|年)\s*(後|あと|先|前|まえ)")
_IWARETA_YOUBI = re.compile(r"は\s*([月火水木金土日])\s*曜日?\s*(です|でした|だ|である|でしたね)")
_KIKU_YOUBI = re.compile(r"(何|なん)曜日|なんようび|曜日は\s*[？?]?$")
_KIKU_HI = re.compile(r"(何|なん)月\s*(何|なん)日|(何|なん)日(で|に|？|\?|$)|日付は|いつ(です|ですか|？|\?|$)")
_KIKU_KIKAN = re.compile(r"(何|なん)日\s*(間|あります|ありますか|ある|後|あと|残|のこ)|あと\s*(何|なん)日|まで\s*(は)?\s*(何|なん)日|日数")
_AIDA = re.compile(r"から.+まで")
_SOUTAI = {"一昨日": -2, "おととい": -2, "昨日": -1, "きのう": -1, "今日": 0, "きょう": 0, "本日": 0,
           "明日": 1, "あした": 1, "あす": 1, "明後日": 2, "あさって": 2, "明々後日": 3, "しあさって": 3}
_SHUU = re.compile(r"(先々週|先週|今週|来週|再来週)\s*の?\s*([月火水木金土日])曜")
_SHUU_OFS = {"先々週": -2, "先週": -1, "今週": 0, "来週": 1, "再来週": 2}


def _hi(text: str, kyou: _dt.date):
    """文の中の 起点の日付を1つ取り出す。(日付, 文の残り) 。無ければ (None, 文)。"""
    m = _NEN_TSUKI_HI.search(text)
    if m:
        y, mo, d = (_kazu(g) for g in m.groups())
        try:
            return _dt.date(y, mo, d), text[m.end():]
        except ValueError:
            return None, text
    m = _TSUKI_HI.search(text)
    if m:
        mo, d = (_kazu(g) for g in m.groups())
        nen = kyou.year + next((n for go, n in (("再来年", 2), ("来年", 1), ("去年", -1), ("昨年", -1), ("一昨年", -2)) if go in text[:m.start()]), 0)
        try:
            return _dt.date(nen, mo, d), text[m.end():]
        except ValueError:
            return None, text
    m = _SHUU.search(text)
    if m:
        base = kyou - _dt.timedelta(days=kyou.weekday()) + _dt.timedelta(weeks=_SHUU_OFS[m.group(1)])
        return base + _dt.timedelta(days=_YOUBI.index(m.group(2))), text[m.end():]
    for go, n in sorted(_SOUTAI.items(), key=lambda kv: -len(kv[0])):
        i = text.find(go)
        if i >= 0:
            return kyou + _dt.timedelta(days=n), text[i + len(go):]
    return None, text


def _tasu(hi: _dt.date, n: int, tani: str, muki: str) -> _dt.date:
    if muki in ("前", "まえ"):
        n = -n
    if tani == "日":
        return hi + _dt.timedelta(days=n)
    if tani in ("週間", "週"):
        return hi + _dt.timedelta(weeks=n)
    if tani == "年":
        return _tsuki_tasu(hi, 12 * n)
    return _tsuki_tasu(hi, n)


def _tsuki_tasu(hi: _dt.date, n: int) -> _dt.date:
    m0 = hi.year * 12 + hi.month - 1 + n
    y, mo = divmod(m0, 12)
    mo += 1
    for d in range(hi.day, 0, -1):
        try:
            return _dt.date(y, mo, d)
        except ValueError:
            continue
    return hi


def kotae(text: str, kyou: _dt.date | None = None) -> str | None:
    """日付の問いに答える。暦の問いでなければ None。"""
    text = (text or "").strip()
    if not text:
        return None
    kyou = kyou or _dt.date.today()
    kiku_youbi = bool(_KIKU_YOUBI.search(text))
    kiku_hi = bool(_KIKU_HI.search(text))
    kiku_kikan = bool(_KIKU_KIKAN.search(text)) and not _OFFSET.search(text)
    if not (kiku_youbi or kiku_hi or kiku_kikan):
        return None

    # 「A から B まで 何日」
    if kiku_kikan and _AIDA.search(text):
        a, nokori = _hi(text.split("から", 1)[0] or "今日", kyou)
        if a is None and "から" in text:
            a = kyou
        b, _ = _hi(text.split("から", 1)[1], kyou)
        if a is not None and b is not None:
            return "%d日" % (b - a).days
        return None
    if kiku_kikan:
        b, _ = _hi(text, kyou)
        if b is None:
            return None
        n = (b - kyou).days
        return "あと%d日（%s）" % (n, _moji(b)) if n >= 0 else "%d日前（%s）" % (-n, _moji(b))

    hi, nokori = _hi(text, kyou)
    m_ofs = _OFFSET.search(nokori if hi is not None else text)
    if hi is None:
        if m_ofs is None and not (kiku_youbi or kiku_hi):
            return None
        hi, nokori = kyou, text          # 起点が無ければ今日
    saki = hi
    if m_ofs:
        n = _kazu(m_ofs.group(1))
        if n is None:
            return None
        saki = _tasu(hi, n, m_ofs.group(2), m_ofs.group(3))
    # 言われた曜日があれば、暦ではなく それから数える（問いの中の世界に合わせる）
    m_y = _IWARETA_YOUBI.search(text)
    if m_y:
        youbi = _YOUBI[(_YOUBI.index(m_y.group(1)) + (saki - hi).days) % 7]
    else:
        youbi = _YOUBI[saki.weekday()]
    if kiku_youbi and not kiku_hi:
        return youbi + "曜日"
    if kiku_hi and not kiku_youbi:
        return _moji(saki) if saki.year != kyou.year else "%d月%d日" % (saki.month, saki.day)
    return "%s（%s曜日）" % (_moji(saki), youbi)


def _moji(hi: _dt.date) -> str:
    return "%d年%d月%d日" % (hi.year, hi.month, hi.day)


if __name__ == "__main__":
    import sys
    print(kotae(" ".join(sys.argv[1:])))
