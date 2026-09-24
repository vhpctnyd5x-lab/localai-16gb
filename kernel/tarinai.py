#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tarinai.py -- 足りない部品を、失敗から言い当てる

  【なぜ これを先にやるか】
  棚に無いことはできない。では何を棚に足すのか。
  勘で決めると外す。今日だけで3回外した
  （文字予想を繋いで差ゼロ／ツェットリンが負け／練習で悪化）。

  そこで、勘をやめる。
  詰まったときに「何を頼まれて、どこで詰まったか」を控えておき、
  よく詰まる順に並べる。作るのは、その順に。

  控えるだけ。何も壊さない。何も外に出さない。
"""
import datetime, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHO = os.path.join(HERE, "tarinai.json")
MAX = 2000


def _yomu():
    if os.path.exists(CHO):
        try:
            return json.load(open(CHO, encoding="utf-8"))
        except Exception:
            pass
    return {"記録": []}


def _kaku(d):
    d["記録"] = d["記録"][-MAX:]
    json.dump(d, open(CHO, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))


def tsumazuita(text, slots=None, riyuu="", tokoro=""):
    """詰まったことを控える

    text  : 言われたこと
    slots : そこまでに引けた札
    riyuu : なぜ駄目だったか
    tokoro: どこで（札引き／組み立て／実行）
    """
    d = _yomu()
    d["記録"].append({
        "いつ": datetime.datetime.now().isoformat(timespec="seconds"),
        "言われたこと": str(text)[:120],
        "引けた札": dict(slots or {}),
        "理由": str(riyuu)[:120],
        "ところ": tokoro,
    })
    _kaku(d)


def matome(n=12):
    """よく詰まる順に並べる"""
    d = _yomu()
    kaz, rei = {}, {}
    for r in d["記録"]:
        s = r.get("引けた札") or {}
        # 何が足りなかったかで束ねる。
        #   動作が引けていない → その言い方に当たる札が無い
        #   動作は引けたが解けない → その動作を実行する部品が無い
        if not s.get("動作"):
            k = ("札がない", r["言われたこと"][:20])
        else:
            k = ("部品がない", s["動作"])
        kaz[k] = kaz.get(k, 0) + 1
        rei.setdefault(k, []).append(r["言われたこと"])
    out = sorted(kaz.items(), key=lambda kv: -kv[1])[:n]
    return [{"何が": a, "対象": b, "回数": c, "例": rei[(a, b)][:3]}
            for (a, b), c in out]


def hyouji(n=12):
    m = matome(n)
    if not m:
        return "まだ詰まった記録はありません。"
    d = _yomu()
    out = [f"詰まった記録 {len(d['記録'])} 件 ／ よく詰まる順に {len(m)} 件", ""]
    for r in m:
        out.append(f"  {r['回数']:>3} 回  【{r['何が']}】 {r['対象']}")
        for e in r["例"]:
            out.append(f"           例: {e}")
    out.append("")
    out.append("  ここに出た順に部品を足すと、いちばん無駄がありません。")
    return "\n".join(out)


if __name__ == "__main__":
    print(hyouji(int(sys.argv[1]) if len(sys.argv) > 1 else 12))
