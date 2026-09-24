#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grow.py -- 使いながらカードを育てる

  考え方はひとつだけ。
  「一度うまくいった表引きは、次からカードにしておけば、引かずに済む」

  さらに、辞書を1段だけ辿って、説明に出てきた語も同じ判定にかける。
  「スナップ」を調べたついでに「写真」「撮影」も覚える、ということ。

  育てた分は grown_cards.json に貯まり、種火のカードと同じ扱いになる。
  自信の無いものは覚えない（間違ったカードは、間違った動作になるため）。
"""
import os, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "grown_cards.json")

# 表引きの結果をカードにする最低線。
# 実測で、正しいものは 0.14 以上、間違いは 0.05 以下に分かれた。
# カードは「そのまま採用」されてしまうので、表引きより厳しくする
MIN_SCORE, MIN_MARGIN = 0.12, 0.05

# 動作は「移す/捨てる」を左右する。弱い証拠で覚えてはいけない。
# 時期も外す。「今日」「去年」は説明文にたまたま出てくるだけで、
# 「学校 → 今日」「教育 → 今日」のような札ができてしまった
NEVER = {"動作", "時期"}

# 何にでも薄く似てしまう語。カードにすると必ず誤爆する
SKIP = {"ファイル", "フォルダ", "もの", "こと", "これ", "それ", "あれ",
        "とき", "ため", "場合", "以下", "以上", "一般", "意味", "使用",
        "する", "ある", "いる", "なる", "こう", "そう", "など", "また"}


def load():
    if os.path.exists(STORE):
        try:
            return json.load(open(STORE, encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(d):
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STORE)


def remember(word, slot, value, score, source=""):
    """カードを1枚くわえる。すでにあれば、自信の高い方を残す"""
    if slot in NEVER or word in SKIP or len(word) < 2 or len(word) > 20:
        return False
    d = load()
    old = d.get(word)
    if old and old["自信"] >= score:
        return False
    d[word] = {"枠": slot, "値": value, "自信": round(float(score), 3),
               "出どころ": source,
               "覚えた日": time.strftime("%Y-%m-%d")}
    _save(d)
    return True


def apply_to(SEED):
    """育てたカードを、種火のカードに足す（種火の方を優先する）"""
    n = 0
    for w, v in load().items():
        if w not in SEED:
            SEED[w] = (v["枠"], v["値"])
            n += 1
    return n


# ------------------------------------------------------------------
# 覚え方は「辞書の説明文で裏を取る」。
#
#   最初は表引き（数の近さ）だけで覚えさせたが、
#   「金属 → テキスト」「ショット → テキスト」のような札が生まれた。
#   近さ 0.13 は、当たりと外れの見分けがつく高さではなかった。
#
#   そこで、説明文の中に「すでに知っている札の語」が出てくるかを見る。
#   「スナップ写真」の説明に『写真』が出てくる → 写真は【画像】の札
#   → だから スナップ も【画像】。これは目で確かめられる根拠になる。
# ------------------------------------------------------------------

def from_definition(word, definition, SEED):
    """説明文の中に出てくる、すでに知っている札から、枠と値を決める。

    別々の値が混ざったら、決められないものとして覚えない。
    戻り値: (枠, 値, 根拠の語) または None
    """
    if not definition or word in SKIP or not (2 <= len(word) <= 20):
        return None
    hits = {}
    for key, (slot, val) in SEED.items():
        if slot in NEVER or len(key) < 2:
            continue
        if key in definition:
            hits.setdefault(slot, {}).setdefault(val, set()).add(key)
    for slot, vals in hits.items():
        if len(vals) != 1:
            continue            # 「画像」と「動画」が両方出てきた → 決めない
        val, keys = next(iter(vals.items()))
        return slot, val, sorted(keys)[0]
    return None


def from_words(words, look, SEED, limit=12):
    """語のならびを、辞書を引きながら判定してカードにする。

    look は「語 → 説明文」を返す関数（lookup.Dict().look）。
    これが「調べたついでに、まわりも覚える」の中身。

    根拠に使うのは、最初から持っている札だけ。
    覚えたばかりの札を根拠にすると、間違いが次々に伝染する
    （「モニター → 動画」を根拠に「静止画 → 動価」まで覚えてしまった）
    """
    base = {k: v for k, v in SEED.items() if k not in load()}
    got = []
    for w in list(words)[:limit]:
        if w in SEED or w in SKIP or len(w) < 2:
            continue
        try:
            d = look(w)
        except Exception:
            continue
        r = from_definition(w, d, base)
        if not r:
            continue
        slot, val, why = r
        # 自信は「根拠がある」の意味で固定。数の近さとは別のもの
        if remember(w, slot, val, 1.0, f"辞書：説明に「{why}」"):
            got.append((w, slot, val, why))
    return got
