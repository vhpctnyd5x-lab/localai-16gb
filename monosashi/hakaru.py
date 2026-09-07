#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru.py -- 手元のモデルに問題集を解かせて、段数ごとに点をつける。

★ ○× は **機械が付ける**。LLM に採点させない（引き継ぎ書2 5章(7)）。
★ 正解率だけでなく **秒数と考えた字数** も必ず一緒に出す。
  「賢いが遅すぎて使えない」は改善ではないので、人が決められる形にする。

使いかた:
    python3 hakaru.py --fukasa 0 --out kekka/f0.json
    python3 hakaru.py --fukasa 3 --lora           # LoRA を乗せて測るとき（名札だけ）
"""
import argparse, json, os, re, sys, time, threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))      # 上の kangaeru_fukasa.py を使う
import kangaeru_fukasa as KF

# ★ 答えの上限は **短く**。この問題集の答えはどれも一行なのに、
#   上限を 3500 にすると たまに 4分ぶん 書き続ける問題が出る（実測）。
#   1件の外れ値が 全体の時間を決めてしまうので、ここで縛る。
KOTAE_CAP = 700

SYSTEM = ("あなたは 算数と なぞときの係です。"
          "答えだけを short に書いてください。式や説明は書かないこと。")

ZEN = str.maketrans("０１２３４５６７８９，．", "0123456789,.")


def _seikai(deta, out: str) -> bool:
    r"""出力が正解かどうかを **機械で** 決める。

    ★ ここが物差しの心臓。ゆるすぎても きつすぎても 数字が嘘になる。

    ── 2026-09-07 に見つかって直した3つ（どれも実際に誤判定していた）──

    (1) **小数が読めなかった。** `-?\d+` で拾っていたので "22.5" が
        ['22','5'] に割れ、末尾 '5' を答えとみなして ×。
        → 小数点を含む形で拾う。

    (2) **「最後の数」の拾い方が雑だった。**
        「答えは 31 です (問1)」で末尾の '1' を拾って ×。
        「160円です。次は 5 番」で '5' を拾って ×。
        → **最後の数だけを見ない。** 出てきた数のどれかが答えと一致すれば ○。
          途中の数で偶然当たる心配はあるが、**取りこぼす方が害が大きい**
          （実際、これで 深さ2 の点を 1.7 ポイント低く出していた）。
          ただし「答え」「＝」の直後の数があれば、それを優先して見る。

    (3) **語の部分一致がゆるすぎた。**
        「月」に対し「日月火水木金土のどれか」が ○ になり、
        「パン」に対し「フライパン」が ○ になっていた。
        → 答えの前後が **別の語の一部になっていないか** を見る。
          曜日は「月曜日」を通したいので、後ろに「曜日」が続くのは許す。
    """
    if not out:
        return False
    o = out.translate(ZEN).replace(",", "")
    kotae = deta["答"]

    if deta["答の形"] == "数":
        # 「答え: 」「＝」の直後があれば そこを最優先で見る
        for m in re.finditer(r"(?:答え?\s*[:：]?\s*|[=＝]\s*)(-?\d+(?:\.\d+)?)", o):
            if _kazu_onaji(m.group(1), kotae):
                return True
        kazu = re.findall(r"-?\d+(?:\.\d+)?", o)
        if not kazu:
            return False
        # 最後の数を第一候補にしつつ、どれか一致すれば ○
        if _kazu_onaji(kazu[-1], kotae):
            return True
        return any(_kazu_onaji(k, kotae) for k in kazu)

    if re.match(r"^\d+月\d+日$", kotae):
        m, d = re.match(r"^(\d+)月(\d+)日$", kotae).groups()
        return bool(re.search(r"%s\s*月\s*%s\s*日" % (m, d), o))

    # 語。前後が別の語の一部になっていないか見る（フライパン を弾く）
    #   ★ ひらがなは助詞・語尾なので **くっついていてよい**（パン**です** は正解）。
    #     別の語になるのは カタカナ・漢字・英数字がくっついたとき
    #     （フライ**パン** / 日**月**火水木金土）。
    #     ただし「月」→「月曜日」だけは通す。
    TSUZUKI = re.compile(r"[ァ-ヶ一-龥A-Za-z0-9]")
    for m in re.finditer(re.escape(kotae), o):
        mae = o[m.start() - 1] if m.start() > 0 else ""
        ato = o[m.end()] if m.end() < len(o) else ""
        if mae and TSUZUKI.match(mae):
            continue
        if ato and TSUZUKI.match(ato) and not o[m.end():].startswith("曜日"):
            continue
        return True
    return False


def _kazu_onaji(a, b):
    """数の文字列どうしを、小数の書き方のゆらぎを吸って比べる"""
    try:
        return abs(float(a) - float(b)) < 1e-9
    except ValueError:
        return a == b


def hitotsu(deta, fukasa, timeout):
    t0 = time.time()
    r = KF.kiku(deta["問"], system=SYSTEM, fukasa=fukasa, timeout=timeout,
                kotae_cap=KOTAE_CAP)
    out = (r.get("text") or "").strip()
    return {"id": deta["id"], "段": deta["段"], "型": deta["型"],
            "問": deta["問"], "答": deta["答"], "出力": out[:400],
            "○": _seikai(deta, out), "秒": round(time.time() - t0, 1),
            "考えた字数": r.get("考えた字数", 0), "回数": r.get("回数", 0),
            "しくじり": r.get("error")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fukasa", type=int, default=0)
    ap.add_argument("--mondai", default=os.path.join(HERE, "mondai.jsonl"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--narabi", type=int, default=2)   # llama-server の -np と同じ
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--nafuda", default="")            # 記録に残す名札（LoRAあり等）
    ap.add_argument("--kagiri", type=int, default=0)   # 試すときに件数を絞る
    a = ap.parse_args()

    mondai = [json.loads(l) for l in open(a.mondai, encoding="utf-8") if l.strip()]
    if a.kagiri:
        mondai = mondai[:a.kagiri]
    out = a.out or os.path.join(HERE, "kekka", "f%d%s.json" % (
        a.fukasa, ("_" + a.nafuda) if a.nafuda else ""))
    os.makedirs(os.path.dirname(out), exist_ok=True)

    t0 = time.time()
    sumi = [0]
    lock = threading.Lock()

    def work(d):
        r = hitotsu(d, a.fukasa, a.timeout)
        with lock:
            sumi[0] += 1
            if sumi[0] % 10 == 0:
                print("  %d/%d  %.0f秒" % (sumi[0], len(mondai), time.time() - t0),
                      flush=True)
        return r

    with ThreadPoolExecutor(max_workers=a.narabi) as ex:
        kekka = list(ex.map(work, mondai))

    matome = {"深さ": a.fukasa, "深さの名": KF.FUKASA[a.fukasa]["名"],
              "名札": a.nafuda, "件数": len(kekka),
              "全体秒": round(time.time() - t0, 1)}
    for dan in (1, 2, 3):
        g = [k for k in kekka if k["段"] == dan]
        if g:
            matome["段%d" % dan] = {
                "件": len(g),
                "正解率": round(100.0 * sum(k["○"] for k in g) / len(g), 1),
                "平均秒": round(sum(k["秒"] for k in g) / len(g), 1)}
    matome["正解率"] = round(100.0 * sum(k["○"] for k in kekka) / len(kekka), 1)
    matome["平均秒"] = round(sum(k["秒"] for k in kekka) / len(kekka), 1)
    matome["平均考えた字数"] = round(sum(k["考えた字数"] for k in kekka) / len(kekka))
    matome["しくじり件数"] = sum(1 for k in kekka if k["しくじり"])

    json.dump({"まとめ": matome, "一件ずつ": kekka},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(matome, ensure_ascii=False, indent=1))
    print("→", out)


if __name__ == "__main__":
    main()
