#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manabu.py -- 先生に作らせて、確かめて、次に活かす

  右脳（先生 = LLM）が書く。左脳（web_kensa）が確かめる。
  ここは その間にある「学ぶ所」。

  ────────────────────────────────────────────────
  何を学ぶのか
  ────────────────────────────────────────────────
  先生の中身は変えられない（重みは向こうにある）。
  変えられるのは **こちらの言いつけ** だけ。

  だから学ぶのは 言いつけ。

      先生が書く → 検査で落ちる → 落ちた理由を 言いつけ に変える
      → 次からその言いつけを 前に置く → 一発で通る率が上がる

  4-⑥ で分かったこと（「言葉づかいの決まりが 数え上げより ずっとよく効く」）が
  先生に対しても成り立つなら、これが効くはず。**成り立つかは 測って決める。**

  ────────────────────────────────────────────────
  破らない決めごと
  ────────────────────────────────────────────────
  ・検査を通らなかったものは 置かない。「作った」とも言わない
  ・言いつけは 足せば足すほど良い、ではない。
    入れて 一発合格率が **上がらなかった** 言いつけは 捨てる（4-⑥ の教訓）
  ・比べる時は 同じお題・同じ順で回す（4-⑤ の教訓）
  ・先生は 案を出すだけ。正しさは こちらが決める

  Python 標準ライブラリのみ。
"""
import json
import os
import random
import sys

import teachers
import web_kensa

KIOKU = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sensei_note.json")

# 既定の先生団。ollama（手元）は遅いので 明示した時だけ
GROQ = ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"]
TEMOTO = ["ollama:qwen2.5-coder:3b"]

SYS = ("あなたは HTML を書く職人です。HTML だけを出力します。"
       "説明・前置き・あとがき・コードフェンスは 一切書きません。")

# 練習のお題。**答えを覚えさせないため、毎回 種で選び直す**
ODAI = [
    "一人用のカードゲーム",
    "数当てゲーム（1〜100）",
    "神経衰弱（4×4）",
    "じゃんけん",
    "◯×ゲーム（相手はコンピュータ）",
    "ストップウォッチ",
    "電卓",
    "今日の持ち物チェック表",
    "そうじ当番の割り当て表",
    "簡単な家計のメモ",
    "もぐらたたき",
    "タイピングの練習",
    "サイコロを振る道具",
    "色あてクイズ",
    "単位の変換（cm と inch）",
]

# 難しいお題。
#
#   受け口を直したら 3B が 94%（[5,6,6]／6問）まで上がり、
#   上の ODAI では **天井に張り付いて 何も測れなくなった**。
#   言いつけも 手も、差が出る余地が無い所で測っても 意味がない。
#
#   ここは「状態を持つ」「決まりが多い」「数え間違えやすい」ものを集める。
ODAI_MUZUI = [
    "オセロ（8×8・相手はコンピュータ）",
    "テトリス",
    "スネークゲーム（矢印で動かす）",
    "ブロック崩し",
    "15パズル（4×4・混ぜる所まで）",
    "マインスイーパ（9×9・爆弾10個）",
    "ライフゲーム（20×20・動かせる）",
    "迷路を自動で作って 解く",
    "ソリティア（クロンダイク）",
    "二人で対戦する 五目並べ",
    "電卓（かっこ と 優先順位つき）",
    "予定表（月ごと・前後に動かせる）",
]


# ── 落ちた理由 → 言いつけ への翻訳表 ──────────────────
# 勝手に増やさない。実際に落ちた理由からだけ足す。
HONYAKU = [
    ("外のURL",        "画像・文字の形・部品を 外から読み込まないこと。絵が要るなら 記号か文字か SVG を 直接書くこと。"),
    ("ネットにつなぐ",  "fetch・XMLHttpRequest・WebSocket を 使わないこと。ネットに一切つながないこと。"),
    ("外から取り込む",  "import() を 使わないこと。ひとつのファイルの中だけで 完結させること。"),
    ("こっそり送る",    "sendBeacon などで 外に何かを送らないこと。"),
    ("を押すと例外",    "getElementById で取った物を 使う前に、その id が HTML の中に 実際に書いてあるか 見直すこと。無い id を触らないこと。"),
    ("読み込みで例外",  "読み込んだ時点で 例外が出ないようにすること。使う前に 変数と要素が そろっているか 確かめること。"),
    ("閉じていないタグ", "開いたタグは 必ず閉じること。"),
    ("白紙です",        "画面に 見える物を 必ず置くこと。"),
    ("読み込みで止まり", "文法の誤りを 残さないこと。書いたものを 頭から読み直してから 出すこと。"),
]


def _yomu():
    if os.path.exists(KIOKU):
        try:
            with open(KIOKU, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"言いつけ": [], "記録": []}


def _kaku(n):
    tmp = KIOKU + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(n, f, ensure_ascii=False, indent=1)
    os.replace(tmp, KIOKU)


def saiyou(note):
    """いま採用している言いつけ（試し中も含む）"""
    return [i for i in note["言いつけ"] if i.get("状態") != "捨てた"]


def _honyaku(riyuu):
    for key, iitsuke in HONYAKU:
        if key in riyuu:
            return iitsuke
    return None


# ── 頼みかたの型（手）──────────────────────────────
#
#   言いつけ（禁止事項を並べる）は 測ったら 下がった（-2／ぶれ幅1・2026-08-30）。
#   ならば 別の形を試す。**どれも 勘で入れない。1つずつ ぶれ幅と比べる。**
#
#   3B のしくじりは ほぼ全部 SyntaxError。長く書くほど壊れる、が見立て。
TE = {
    "素": "",
    "小さく": "\n短く 作ってください。100行を超えないこと。"
              "機能は ひとつだけにして、飾りは要りません。",
    "落ち着いて": "\nいきなり書き始めず、まず 何を作るか 頭の中で決めてから、"
                  "一息に 最後まで 書き切ってください。",
}


def _tanomu(dai, iitsuke, naoshi=None, te="素"):
    """先生への 頼みかたを 組み立てる"""
    p = [f"{dai} を、HTML ひとつのファイルで 作ってください。" + TE.get(te, "")]
    if iitsuke:
        p.append("\n【必ず守ること】")
        p += [f"  ・{s}" for s in iitsuke]
    p.append("\nHTML だけを出力してください。説明もコードフェンスも 書かないこと。")
    if naoshi:
        p.append("\n【前に書いたものは ここで落ちました。直してください】")
        p += [f"  ・{s}" for s in naoshi]
        p.append("直した HTML の全体を、もう一度 まるごと出力してください。")
    return "\n".join(p)


def hitotsu(dai, sensei, iitsuke, naosu=2, timeout=None, te="素"):
    """お題ひとつ。先生に書かせ、検査し、落ちたら理由を返して直させる。

    戻り値: {"お題","先生","一発","通った","何回目で通った","理由","html"}
    """
    # 手元の先生は CPU で走るので けた違いに遅い。
    # 実測 47.8 秒（qwen2.5-coder:3b・HTML 2,397 文字・Intel Mac）。
    # ここを短いままにすると、出てくるのは「時間切れ」であって 品質ではない。
    #
    # local:（llama-server・Qwen3-30B-REAP96）も同じ理由で伸ばす。
    # 実測 32.8 秒／HTML 1,162 文字（14 t/s 相当・2026-09-06）。
    # 60 秒のままだと 長いページで **品質ではなく時間切れを測る**ことになる。
    if timeout is None:
        if sensei.startswith("ollama"):
            timeout = 300
        elif sensei.startswith("local"):
            timeout = 240
        else:
            timeout = 60
    rec = {"お題": dai, "先生": sensei, "手": te, "一発": False, "通った": False,
           "何回目で通った": None, "理由": [], "html": None}
    naoshi = None
    for kai in range(1, naosu + 2):
        r = teachers.ask_one(sensei, _tanomu(dai, iitsuke, naoshi, te),
                             system=SYS, timeout=timeout)
        if r.get("error") or not (r.get("text") or "").strip():
            rec["理由"].append("先生が答えませんでした: " + str(r.get("error"))[:80])
            break
        html = r["text"].strip()
        # お題は どれも「動く物」。動かないページを 通してはいけない
        k = web_kensa.kensa(html, f"{dai}／{sensei}", ugoku=True)
        if k["合格"]:
            rec["通った"] = True
            rec["何回目で通った"] = kai
            rec["一発"] = (kai == 1)
            rec["html"] = html
            break
        naoshi = k["だめな所"]
        rec["理由"] += naoshi
    return rec


def _tsukau(note, riyuu_list):
    """落ちた理由から 言いつけを 足す（同じものは 数だけ増やす）"""
    ima = {i["文"]: i for i in note["言いつけ"]}
    for r in riyuu_list:
        s = _honyaku(r)
        if not s:
            continue
        if s in ima:
            ima[s]["出た回数"] = ima[s].get("出た回数", 0) + 1
        else:
            # ima にも入れる。ここを忘れると、同じ回のうちに
            # 同じ言いつけが 何個も積まれる（実測で 2個できた）
            atarashii = {"文": s, "出た回数": 1, "状態": "試し中",
                         "きっかけ": r[:60]}
            note["言いつけ"].append(atarashii)
            ima[s] = atarashii


def keiko(kaisu=10, tane=1, sensei_tachi=None, naosu=2, iitsuke_tsukau=True):
    """稽古。お題を回して、落ちた理由を 言いつけ に変えて貯める。

    戻り値: {"回数","一発","通った","詰まり",...}
    """
    note = _yomu()
    sensei_tachi = sensei_tachi or GROQ
    rnd = random.Random(tane)
    odai = [rnd.choice(ODAI) for _ in range(kaisu)]

    ippatsu = tootta = 0
    kiroku = []
    for i, dai in enumerate(odai):
        sensei = sensei_tachi[i % len(sensei_tachi)]
        iitsuke = [x["文"] for x in saiyou(note)] if iitsuke_tsukau else []
        rec = hitotsu(dai, sensei, iitsuke, naosu=naosu)
        ippatsu += 1 if rec["一発"] else 0
        tootta += 1 if rec["通った"] else 0
        if rec["理由"]:
            _tsukau(note, rec["理由"])
        kiroku.append({k: v for k, v in rec.items() if k != "html"})
        print("  %2d/%d %s [%s] %s"
              % (i + 1, kaisu, dai, sensei.split(":")[-1],
                 ("一発" if rec["一発"] else
                  (f"{rec['何回目で通った']}回目で通った" if rec["通った"]
                   else "通らなかった: " + "／".join(rec["理由"])[:70]))),
              flush=True)

    note["記録"] = (note.get("記録", []) + kiroku)[-300:]
    _kaku(note)
    return {"回数": kaisu, "一発": ippatsu, "通った": tootta,
            "言いつけ数": len(saiyou(note))}


def suteru(riyuu):
    """試し中の言いつけを 捨てる。

    測って上がらなかったものは 残さない。
    ここが無いと ノートは「思いついた事の置き場」になって、
    使われない枠が 間違いを隠す（4-③ と同じ形）。
    """
    note = _yomu()
    n = 0
    for i in note["言いつけ"]:
        if i.get("状態") == "試し中":
            i["状態"] = "捨てた"
            i["捨てた訳"] = riyuu
            n += 1
    _kaku(note)
    return n


def kurabe(kaisu=10, tane=7, sensei_tachi=None, naosu=0, haba=None):
    """言いつけ 無し と 有り を、**同じお題を 同じ順で** 回して比べる。

    naosu=0 にして「一発で通るか」だけを見る。直しが入ると 言いつけの効果が
    直しに隠れてしまう（4-⑤: 比べるものは 同じ状態で取らないと 比べたことにならない）。
    ここで上がらなかった言いつけは、理屈が通っていても 入れない。
    """
    note = _yomu()
    iitsuke = [x["文"] for x in saiyou(note)]
    sensei_tachi = sensei_tachi or GROQ
    rnd = random.Random(tane)
    odai = [rnd.choice(ODAI) for _ in range(kaisu)]

    kekka = {}
    for namae, tsukau in (("言いつけ なし", []), ("言いつけ あり", iitsuke)):
        n = 0
        print(f"\n── {namae}（{len(tsukau)} 個）──", flush=True)
        for i, dai in enumerate(odai):
            sensei = sensei_tachi[i % len(sensei_tachi)]
            rec = hitotsu(dai, sensei, tsukau, naosu=naosu)
            n += 1 if rec["通った"] else 0
            print("  %2d/%d %s [%s] %s" % (i + 1, kaisu, dai,
                  sensei.split(":")[-1],
                  "通った" if rec["通った"] else
                  "✗ " + "／".join(rec["理由"])[:70]), flush=True)
        kekka[namae] = n

    a, b = kekka["言いつけ なし"], kekka["言いつけ あり"]
    sa = b - a
    print(f"\n  言いつけ なし: {a}/{kaisu}")
    print(f"  言いつけ あり: {b}/{kaisu}   （{sa:+d}）")

    # ぶれ幅を渡されていない時は「差がある＝効いた」と読まない。
    # 先生の答えは毎回ちがう。物差しを先に取ること（yure）
    if haba is None:
        print("  ※ ぶれ幅が分かりません。yure() を先に回してください")
        return kekka
    print(f"  ぶれ幅: {haba}（境目は {haba + 1} 以上）")

    # ぶれ幅は 少ない回数で測っているので **過小評価しがち**。
    #   実測: 易しいお題で [2,2] → ぶれ幅0 と出たが、
    #   2回しか回していない。真のぶれ幅が 1 でも おかしくない。
    #   だから「ぶれ幅を超えた」ではなく **「ぶれ幅+1 以上」** を境にする。
    #   固くして 見逃す方が、甘くして 効かないものを 残すより安全（4-⑥）。
    sikii = haba + 1
    if sa >= sikii:
        print("  → 効いた。この言いつけは 残す")
        note = _yomu()
        for i in note["言いつけ"]:
            if i.get("状態") == "試し中":
                i["状態"] = "残す"
                i["測った"] = f"{a}→{b}（ぶれ幅 {haba}）"
        _kaku(note)
    elif sa <= -sikii:
        n = suteru(f"下がった {a}→{b}（ぶれ幅 {haba}）")
        print(f"  → 下がった。**理屈が通っていても 入れない**。{n} 個 捨てました")
    else:
        n = suteru(f"ぶれ幅の内 {a}→{b}（ぶれ幅 {haba}）")
        print(f"  → ぶれ幅の内。効いたとは言えない。{n} 個 捨てました")
    return kekka


def yure(kaisu=8, tane=7, sensei_tachi=None, kai=3, odai_moto=None):
    """**同じ条件で** 何度も回して、先生のぶれ幅を測る。

    ここが無いと、くらべる の数字が読めない。実測でこう出た:

        同じお題・同じ種・同じ先生・言いつけ空 で
        「色あてクイズ」が 1回目は落ち、2回目は 一発で通った

    先生の答えは 毎回ちがう。だから 8回で +1 や +2 の差が出ても、
    それが 言いつけの効果なのか ただのぶれなのか 区別がつかない。
    **ぶれ幅より大きくない差は「効いた」と言わない。**
    """
    sensei_tachi = sensei_tachi or GROQ
    rnd = random.Random(tane)
    odai = [rnd.choice(odai_moto or ODAI) for _ in range(kaisu)]
    dedo = []
    for k in range(kai):
        n = 0
        for i, dai in enumerate(odai):
            rec = hitotsu(dai, sensei_tachi[i % len(sensei_tachi)], [], naosu=0)
            n += 1 if rec["通った"] else 0
        dedo.append(n)
        print("  %d回目: %d/%d" % (k + 1, n, kaisu), flush=True)
    haba = max(dedo) - min(dedo)
    print(f"\n  同じ条件で {kai} 回まわした結果: {dedo}")
    print(f"  ぶれ幅: {haba}（{kaisu} 回中）")
    print(f"  → 言いつけの差が {haba} 以下なら、効いたとは言わない")
    return {"出た値": dedo, "ぶれ幅": haba, "回数": kaisu}


def te_kurabe(te_tachi=None, kaisu=6, tane=7, sensei_tachi=None, haba=1,
              naosu=0, odai_moto=None):
    """頼みかたの型（手）を 同じお題・同じ順で 比べる。

    言いつけ が下がった（-2）ので、別の形を試す。
    ぶれ幅を超えた手だけを 残す。超えなければ 入れない。
    """
    te_tachi = te_tachi or list(TE)
    sensei_tachi = sensei_tachi or GROQ
    rnd = random.Random(tane)
    odai = [rnd.choice(odai_moto or ODAI) for _ in range(kaisu)]

    kekka = {}
    for te in te_tachi:
        n = 0
        print(f"\n── 手『{te}』──", flush=True)
        for i, dai in enumerate(odai):
            rec = hitotsu(dai, sensei_tachi[i % len(sensei_tachi)], [],
                          naosu=naosu, te=te)
            n += 1 if rec["通った"] else 0
            print("  %2d/%d %s %s" % (i + 1, kaisu, dai,
                  "通った" if rec["通った"] else
                  "✗ " + "／".join(rec["理由"])[:60]), flush=True)
        kekka[te] = n

    moto = kekka.get("素", 0)
    print(f"\n  ── まとめ（ぶれ幅 {haba}）──")
    for te, n in kekka.items():
        sa = n - moto
        if te == "素":
            mark = "（もと）"
        elif sa >= haba + 1:
            mark = "← 効いた。残す"
        elif sa <= -(haba + 1):
            mark = "← 下がった。入れない"
        else:
            mark = "← ぶれ幅の内。効いたとは言えない"
        print("  %-6s %d/%d  %+d  %s" % (te, n, kaisu, sa, mark))
    return kekka


def miseru():
    note = _yomu()
    ii = saiyou(note)
    print(f"言いつけ {len(ii)} 個（{KIOKU}）")
    for x in sorted(ii, key=lambda x: -x.get("出た回数", 0)):
        print("  %2d回  %s" % (x.get("出た回数", 0), x["文"]))
    k = note.get("記録", [])
    if k:
        t = sum(1 for r in k if r.get("通った"))
        i = sum(1 for r in k if r.get("一発"))
        print(f"\nこれまで {len(k)} 回 ／ 通った {t} ／ 一発 {i}")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else "みせる"
    if cmd == "けいこ":
        n = int(a[1]) if len(a) > 1 else 10
        tane = int(a[2]) if len(a) > 2 else 1
        print(keiko(n, tane))
    elif cmd == "くらべる":
        n = int(a[1]) if len(a) > 1 else 10
        tane = int(a[2]) if len(a) > 2 else 7
        kurabe(n, tane)
    elif cmd == "て":          # 頼みかたの型を比べる
        n = int(a[1]) if len(a) > 1 else 6
        te_kurabe(kaisu=n)
    elif cmd == "ゆれ":         # 先生のぶれ幅を測る（くらべる の前に必ず）
        n = int(a[1]) if len(a) > 1 else 8
        tane = int(a[2]) if len(a) > 2 else 7
        yure(n, tane)
    elif cmd == "てもと":       # 手元の小さい先生（ollama）で
        n = int(a[1]) if len(a) > 1 else 3
        print(keiko(n, 1, sensei_tachi=TEMOTO))
    else:
        miseru()
