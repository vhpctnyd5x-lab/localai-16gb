#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kernel.py -- 掛け算をしない、育つ、パソコン操作エンジン (v0)

  (1) カードの箱 : 言葉のブレを吸収して「概念」に寄せる
  (2) 部品の箱   : できることの最小単位
  (3) 組み立て役 : 部品を1つずつ置いて、実行して、確かめて進む
  (4) ノート     : うまくいった手順を覚える。次からは即答

使い方:
    python3 kernel.py --demo                     デモ用のファイルを作る
    python3 kernel.py "デスクトップの写真まとめて"
    python3 kernel.py --note                     ノートの中身を見る
"""

import os, sys, json, time, shutil, datetime, argparse, functools
import re as _re

HERE     = os.path.dirname(os.path.abspath(__file__))
NOTEBOOK = os.path.join(HERE, "notebook.json")


def notebook_path():
    """練習用と本物で、覚えることを分ける。

    フォルダの深さが違うので、同じ手順が通用しない
    （練習用で覚えた「さがす」を本物で使い、0件になる事故があった）
    """
    return (os.path.join(HERE, "notebook_real.json") if ROOT == "real"
            else NOTEBOOK)
# 練習用フォルダは、本体ディスクに置く。
#
# 外付けSSD(exFAT)に置いていたら、フォルダが壊れた。
# 一覧には名前が出るのに、開こうとすると「無い」と言われ、
# 親フォルダは「中身がある」と言って消せない、という状態になった。
# exFAT は macOS の「._」ファイルと相性が悪く、
# 削除が途中で失敗するとこうなる。
# 記憶ファイル(memory.db)を本体に置いているのと同じ理由。
_DATA = os.path.join(os.path.expanduser("~"), "Library",
                     "Application Support", "kernel-ai")
SANDBOX = os.path.join(_DATA, "sandbox")
os.makedirs(_DATA, exist_ok=True)

# ============================================================
# (1) カードの箱 -- 言葉 → 概念
# ============================================================
# 「見出しの言葉」→ (スロット, 値)
# これは種火。あとで「数えて作ったカード」に置き換えられる。
SEED = {
    # --- 動作 ---
    "移動":("動作","移動"), "まとめ":("動作","移動"), "うつ":("動作","移動"),
    "整理":("動作","移動"), "片付":("動作","移動"), "ひとつに":("動作","移動"),
    "わけ":("動作","移動"), "分け":("動作","移動"), "寄せ":("動作","移動"),
    "入れて":("動作","移動"), "しまっ":("動作","移動"), "放り込":("動作","移動"),
    "集め":("動作","移動"), "あつめ":("動作","移動"), "一箇所":("動作","移動"),
    "数え":("動作","数える"), "いくつ":("動作","数える"), "何個":("動作","数える"),
    "何枚":("動作","数える"), "カウント":("動作","数える"),
    "html":("動作","HTML"), "ホームページ":("動作","HTML"),
    "ウェブページ":("動作","HTML"), "webページ":("動作","HTML"),
    "一覧":("動作","一覧"), "見せ":("動作","一覧"), "教えて":("動作","一覧"),
    "リスト":("動作","一覧"), "並べ":("動作","一覧"),
    # --- 場所 ---
    "デスクトップ":("場所","Desktop"), "desktop":("場所","Desktop"),
    "机の上":("場所","Desktop"), "デスク":("場所","Desktop"),
    "ダウンロード":("場所","Downloads"), "downloads":("場所","Downloads"),
    "ドキュメント":("場所","Documents"), "書類フォルダ":("場所","Documents"),
    # --- 種類 ---
    "写真":("種類","画像"), "画像":("種類","画像"), "イメージ":("種類","画像"),
    "スクショ":("種類","画像"), "スクリーンショット":("種類","画像"),
    "撮っ":("種類","画像"), "撮った":("種類","画像"), "とった写真":("種類","画像"),
    "pdf":("種類","PDF"), "資料":("種類","PDF"),
    "動画":("種類","動画"), "ムービー":("種類","動画"), "ビデオ":("種類","動画"),
    "テキスト":("種類","テキスト"), "メモ":("種類","テキスト"),
    # 「書類」は場所(Documents)ではなく種類。ここを場所にしていたため
    # 「デスクトップの書類を整理して」で場所が埋まり済みとなり、
    # 種類が空のまま全部が移動する事故が起きた
    "書類":("種類","書類"), "ドキュメント類":("種類","書類"),
    "音楽":("種類","音楽"), "曲":("種類","音楽"), "オーディオ":("種類","音楽"),
    "圧縮":("種類","圧縮"), "zip":("種類","圧縮"),
    # --- 時期 ---
    "去年":("時期","去年"), "昨年":("時期","去年"),
    "今年":("時期","今年"), "本年":("時期","今年"),
    "今月":("時期","今月"), "先月":("時期","先月"), "前の月":("時期","先月"),
    "今日":("時期","今日"), "きょう":("時期","今日"),
    "さっき":("時期","最近"), "最近":("時期","最近"), "この前":("時期","最近"),
    "今週":("時期","最近"), "ここ数日":("時期","最近"),
}

LEARNED = os.path.join(HERE, "learned_cards.json")

def load_grown():
    """使いながら育てたカードを、種火に足す"""
    try:
        import grow
        return grow.apply_to(SEED)
    except Exception:
        return 0


def load_learned():
    """先生から教わったカードを読み込んで、種火に足す"""
    if os.path.exists(LEARNED):
        try:
            with open(LEARNED, encoding="utf-8") as f:
                for w, (slot, val) in json.load(f).items():
                    SEED.setdefault(w, (slot, val))
        except Exception:
            pass

def save_learned(new):
    """教わったカードを書き足す"""
    cur = {}
    if os.path.exists(LEARNED):
        try:
            with open(LEARNED, encoding="utf-8") as f: cur = json.load(f)
        except Exception: pass
    for w, (slot, val) in new.items():
        cur[w] = [slot, val]
        SEED[w] = (slot, val)
    with open(LEARNED, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)

EXT = {
    "画像":     {".png",".jpg",".jpeg",".gif",".heic",".webp"},
    "PDF":      {".pdf"},
    "動画":     {".mp4",".mov",".avi",".mkv"},
    "テキスト": {".txt",".md",".rtf"},
    "書類":     {".pdf",".txt",".md",".rtf",".doc",".docx",".pages",
                 ".xls",".xlsx",".numbers",".csv",".ppt",".pptx",".key"},
    "音楽":     {".mp3",".m4a",".wav",".aac",".flac",".aiff"},
    "圧縮":     {".zip",".tar",".gz",".7z",".rar",".dmg"},
}

def bigrams(s):
    s = s.lower()
    return set(s[i:i+2] for i in range(len(s)-1)) or {s}

def sim(a, b):
    """文字のかさなり具合で「近さ」を測る。0.0〜1.0"""
    A, B = bigrams(a), bigrams(b)
    return len(A & B) / len(A | B) if (A | B) else 0.0

# ファイル名・フォルダ名の「芯」。ここを見つけて左右に広げる
# 「.txt」「_2026-06-17」のような、記号を含む芯だけを狙う
_NAME_CORE = _re.compile(r"[A-Za-z0-9]*[._\-][A-Za-z0-9._\-]*")
# ここに当たったら名前の切れ目とみなす（助詞・記号・空白）
_STOP = set("のをにへとがはでやかも、。，．,.！？!?　 \t\"'「」『』（）()[]{}:：;；/\\")


# 「〜という」の直前は名前。ただし助詞をまたがない。
# 「って」は「作って」のような動詞語尾に当たるので使わない
_TOIU = _re.compile(r"([^\s、。，．,」』）)にをのはがでともやへ]{2,24})(?:という|といった|と言う)")


def _mask_names(text):
    """「整理済み_2026-06-17」のような固有名を伏せる。

    伏せないと、中の「整理」を動作だと誤読して、
    質問なのにファイルを動かす事故が起きる（実際に起きた）
    """
    names, out = [], list(text)

    # 「作業用というフォルダ」→ 作業用 が名前
    for m in _TOIU.finditer(text):
        w = m.group(1).strip()
        if 2 <= len(w) <= 24 and w not in ("それ", "これ", "あれ", "こう", "そう"):
            names.append(w)
            for i in range(m.start(1), m.end(1)):
                out[i] = "\uf000"

    for m in _NAME_CORE.finditer(text):
        core = m.group(0)
        if not any(c.isalnum() for c in core):
            continue                      # 記号だけは名前ではない
        if out[m.start()] == "\uf000":     # すでに覆われている
            continue
        a, b = m.start(), m.end()
        while a > 0 and text[a - 1] not in _STOP:
            a -= 1
        while b < len(text) and text[b] not in _STOP:
            b += 1
        w = text[a:b]
        if len(w) < 3:
            continue
        names.append(w)
        for i in range(a, b):
            out[i] = "\uf000"            # カードに引っかからない文字で覆う
    return "".join(out), names


# 端末にファイルをドラッグすると、こういう絶対パスが貼られる
_ABSPATH = _re.compile(r"(?:/(?:Users|Volumes|Applications|opt|private|tmp)"
                       r"(?:/[^\s\u3000\"\']+)+)")


# 「AをBに移動させて」の B は、探す相手ではなく行き先。
# ここを名前スロットに入れていたため、行き先フォルダの中を探しに行って
# 「1個も見つからない」で全滅していた
_DEST = _re.compile(
    r"(?:を|は)?\s*([^\sをはがのにへ、。]{1,30}?)\s*(?:という|といった)?\s*"
    r"(?:フォルダ|ファイル|ところ|とこ)?\s*(?:に|へ)\s*"
    r"(?:移動|移し|移す|うつ|入れ|いれ|まとめ|しまっ|しまう|放り込)")

# 「AをBに移動」の A（動かす相手）
_TARGET = _re.compile(r"(?:^|[\s　])([^\s　、。]{1,30}?)を(?=[^をはがの]*(?:に|へ)"
                      r"[^をはがの]*(?:移動|移し|移す|うつ|入れ|いれ|まとめ))")


# 「画像以外」「PDF以外の」→ 何を除くのか
_EXCEPT = _re.compile(r"([^\s　、。をはがのにへ]{1,12})\s*(?:以外|いがい|じゃない|"
                      r"ではない|を除|をのぞ)")


def _except_in(text):
    """「◯◯以外」の ◯◯ を返す。無ければ None"""
    m = _EXCEPT.search(text)
    return m.group(1).strip("　 「」") if m else None


def _move_pair(text):
    """「AをBに移動させて」から (A, B) を取り出す。取れなければ (None, None)"""
    md = _DEST.search(text)
    if not md:
        return None, None
    dest = md.group(1).strip("　 「」『』")
    mt = _TARGET.search(text[:md.start(1)] or text)
    tgt = mt.group(1).strip("　 「」『』") if mt else None
    # 「ファイル」「フォルダ」そのものは行き先の名前ではない。
    # 「PDFというデスクトップのファイルに移動」で行き先が「ファイル」に
    # なってしまっていた
    if dest in ("それ", "そこ", "ここ", "あそこ", "ファイル", "フォルダ",
                "ところ", "とこ", "もの", "やつ", "中", "なか") or len(dest) < 1:
        dest = None
    if tgt and (tgt == dest or len(tgt) < 2):
        tgt = None
    return tgt, dest


def _from_grammar(g, slots, verbose=False):
    """格解析の結果を、スロットに読みかえる。

    戻り値: (動かす相手, 行き先, 出発点)
    """
    act = slots.get("動作")
    tgt = dest = src = None

    # 「〜という名前」が付いていれば、その格の中身は名前
    for n in g.get("名前", []):
        if n["役"] == "ニ" and act in (None, "移動"):
            dest = n["名前"]
        elif n["役"] in ("ヲ", "ハ", "ガ", None):
            tgt = n["名前"]
        if verbose:
            print(f"      文法：「{n['名前']}」は名前"
                  f"（{n['役']}格{'・' + n['種別'] if n['種別'] else ''}）")

    cases = g.get("格", {})

    # カラ格 = 出発点。「ダウンロードから…」
    for w in cases.get("カラ", []):
        v = _place_of(w)
        if v:
            src = v
            if verbose:
                print(f"      文法：「{w}」から（カラ格）→ 出発点 {v}")

    # ニ格 = 移動なら行き先、それ以外なら場所
    for w in cases.get("ニ", []):
        if dest and w == dest:
            continue
        v = _place_of(w)
        if act == "移動":
            if v and "場所" in slots and slots["場所"] != v:
                dest = dest or v          # 行き先も場所名でありうる
            elif not v and not dest and len(w) >= 2:
                dest = w                  # 場所カードに無い名前 = 新しいフォルダ名
            if verbose and dest == w:
                print(f"      文法：「{w}」に（ニ格）→ 行き先")
        elif v and "場所" not in slots:
            slots["場所"] = v

    # ヲ格 = 動かす相手。名前らしければ拾う
    if not tgt:
        for w in cases.get("ヲ", []):
            if _place_of(w) or _kind_of(w):
                continue                  # 種類や場所は、別のスロットで扱う
            if 2 <= len(w) <= 30:
                tgt = w
                if verbose:
                    print(f"      文法：「{w}」を（ヲ格）→ 動かす相手")
                break
    return tgt, dest, src


@functools.lru_cache(maxsize=1)
def _pred_table():
    """述語の表。活用は規則で作る（conjugate.py）

    1,112個ある。これを普通のカードに混ぜてはいけない。
    「思い出す」の中の「出す」を一覧と読むような誤りが出る。
    文のいちばん後ろに来た語（＝述語）を引くときだけ使う。
    """
    try:
        import conjugate
        return conjugate.build()
    except Exception:
        return {}


def _act_of(pred):
    """述語から動作を引く。まず活用表をそのまま照合する"""
    t = _pred_table()
    if pred in t:
        return t[pred]
    # 「〜してみて」「〜しといてよ」のような、後ろに何か付いた形
    for n in range(len(pred), 1, -1):
        if pred[:n] in t:
            return t[pred[:n]]
    p = pred.lower()
    for k, (slot, val) in SEED.items():
        if slot == "動作" and len(k) >= 2 and k.lower() in p:
            return val
    best, score = None, 0.0
    for k, (slot, val) in SEED.items():
        if slot != "動作" or len(k) < 2:
            continue
        sc = sim(k, pred)
        if sc > score:
            best, score = val, sc
    return best if score >= 0.5 else None


def _place_of(w):
    """その語が場所カードなら、その値を返す"""
    for k, (slot, val) in SEED.items():
        if slot == "場所" and (k.lower() in w.lower() or w.lower() in k.lower()):
            return val
    return None


def _kind_of(w):
    """その語が種類カードなら、その値を返す"""
    for k, (slot, val) in SEED.items():
        if slot == "種類" and len(k) >= 2 and k.lower() in w.lower():
            return val
    return None


def _paths_in(text):
    """入力に混ざっている本物の絶対パスを拾う"""
    out = []
    for m in _ABSPATH.finditer(text):
        q = m.group(0).rstrip("。、,.")
        if os.path.exists(q):
            out.append(q)
    return out


def draw_cards(text, verbose=False):
    """入力の文から、カードを引いて概念スロットを埋める"""
    raw_text = text
    paths = _paths_in(text)
    for q in paths:                      # パスの中の語をカードに引かせない
        text = text.replace(q, " ")
    text, _names = _mask_names(text)
    low   = text.lower()
    slots = {}
    trace = []
    _ex_raw = _except_in(text) or ""
    for key, (slot, val) in SEED.items():
        if slot in slots:
            continue
        # 「画像以外」の「画像」を、種類として拾ってはいけない
        if slot == "種類" and key in _ex_raw:
            continue
        if key.lower() in low:                       # そのまま入っていた
            slots[slot] = val
            trace.append((key, val, 1.00))
            continue
        best = 0.0                                   # 入っていない → 近さで探す
        n = len(key)
        for w in range(max(2, n-1), n+3):
            for i in range(0, max(1, len(text)-w+1)):
                best = max(best, sim(key, text[i:i+w]))
        if best >= 0.55:
            slots[slot] = val
            trace.append((key, val, round(best, 2)))
    if verbose:
        for k, v, s in trace:
            mark = "そのまま" if s == 1.0 else f"近さ {s}"
            print(f"      カード「{k}」→ 【{v}】   ({mark})")

    # 「画像以外」は、画像を種類として採ってはいけない。除くものとして扱う
    ex = _except_in(raw_text)
    if ex:
        for key, (slot, val) in SEED.items():
            if slot == "種類" and key in ex:
                slots["除く"] = val
                break

    # ---- 文法で骨組みを取る（格文法）------------------------------
    # 「AをBに移動して」の A と B を、助詞から見分ける。
    # これまでは手書きの正規表現で拾っていたので、
    # 「PDFというデスクトップのファイルに」で行き先が「ファイル」になった
    g = None
    try:
        import grammar
        # 伏せた固有名は、文法解析でも切らせない
        g = grammar.analyze(raw_text, protect=_names + paths)
    except Exception:
        g = None

    tgt, dest = _move_pair(raw_text)
    if g:
        # 述語から動作を決める。ここが文法を入れたいちばんの目的
        if "動作" not in slots and g.get("述語"):
            a = _act_of(g["述語"])
            if a:
                slots["動作"] = a
                if verbose:
                    print(f"      述語「{g['述語']}」→ 動作【{a}】")

        tgt2, dest2, src2 = _from_grammar(g, slots, verbose)
        tgt = tgt2 or tgt
        dest = dest2 or dest
        # カラ格（〜から）は出発点。ほかの言い方より優先する
        if src2:
            slots["場所"] = src2
    # 「Xというフォルダに移動」なら、X が行き先。
    # 総称語しか取れなかった時は、「〜という」で伏せた名前を行き先に回す
    if dest is None and _names and _DEST.search(raw_text):
        dest = _names[0]
        _names = _names[1:]
        slots.pop("名前", None)
    if dest:
        # 行き先に使った名前は、動かす相手の候補から外す
        _names = [n for n in _names if n != dest]
        slots["行き先"] = dest
        if verbose:
            print(f"      行き先として受け取った： 「{dest}」")
    if tgt and "名前" not in slots:
        slots["名前"] = tgt
        _names = [tgt]
        if verbose:
            print(f"      動かす相手として受け取った： 「{tgt}」")

    if paths:
        slots["パス"] = paths
        slots.pop("名前", None)          # パスがあるなら名前で探す必要はない
        if verbose:
            for q in paths:
                print(f"      本物のパスとして受け取った： {q}")

    if _names and "名前" not in slots:
        slots["名前"] = _names[0]
        if verbose:
            print(f"      固有名として保護： 「{_names[0]}」→ 【名前】")

    # 種火が使い切った語は、もう他のスロットには使わせない。
    # さらに、札に載っている語は「たまたま当たっただけ」の流用も禁じる。
    # 「一覧」は動作の札なのに、動作が埋まっていたせいで表引きに回され、
    # 近さ 0.104 で【今月】になっていた（時期を言われていないのに絞られた）
    used = set(k for k, _v, _s in trace)
    low_all = text.lower()
    used |= set(k for k in SEED if len(k) >= 2 and k.lower() in low_all)

    # 種火で埋まらなかったスロットは、抜いてきた表・数えた表に聞く
    missing = [k for k in ("動作", "場所", "種類", "時期") if k not in slots]
    if missing:
        try:
            u = _unified()
            vt = vocab_table()
            for slot in missing:
                if slot == "動作":
                    # 動作は「消す/移す」を左右する。弱い証拠で決めない
                    continue
                cands = vt.get(slot)
                if not cands:
                    continue
                best, sc, src = None, 0.0, ""
                for w in _words_in(text):
                    if w in _TOO_GENERIC:
                        continue
                    # 大文字小文字をそろえて比べる。そろえていなかったので
                    # 札の「html」と入力の「HTML」が別物と見なされ、
                    # 同じ語が表引きにも回って【テキスト】にされていた
                    wl = w.lower()
                    if any(k.lower() in wl or wl in k.lower() for k in used):
                        continue
                    b, s2, sr = u.nearest(w, cands)
                    if b and s2 > sc:
                        best, sc, src, hit = b, s2, sr, w
                if best and sc >= 0.03:
                    slots[slot] = best
                    used.add(hit)
                    if verbose:
                        print(f"      表引き「{hit}」→ 【{best}】   (近さ {sc:.3f}, {src})")
                    # ここで表引きの結果をそのままカードにしてはいけない。
                    # 一度やってみたところ「金属→テキスト」のような札ができた。
                    # 覚えるのは、辞書の説明で裏が取れたものだけ（grow.py）
        except Exception:
            pass
    return slots


@functools.lru_cache(maxsize=1)
def _unified():
    from cards_unified import UnifiedCards
    return UnifiedCards()


# 助詞・記号で切る。またぐ断片（「去年のスナッ」等）を作らせない
_SEP = _re.compile(r"[のをにへとがはでや、。，．,.\s　！？!?（）()「」\[\]"
                   r"だけとか　]+")

# 総称語。何にでも薄く似てしまうので、種類や場所の判定に使わない
_TOO_GENERIC = {
    "ファイル", "ふぁいる", "もの", "やつ", "データ", "中身", "なかみ",
    "全部", "ぜんぶ", "いろいろ", "何か", "なにか", "こと", "とこ", "ところ",
    "フォルダ", "ふぉるだ", "ディレクトリ", "アイテム", "中の", "たち",
    # 人称・指示語。表では何にでも薄く似てしまう
    "あなた", "あんた", "きみ", "おまえ", "自分", "わたし", "わたく",
    "これ", "それ", "あれ", "どれ", "ここ", "そこ", "あそこ", "どこ",
    "今の", "さっき", "本当", "ほんと", "普通", "感じ", "とき", "ため",
}


def _words_in(text):
    """入力から、語になりうるまとまりだけを切り出す"""
    out = []
    for chunk in _SEP.split(text):
        chunk = chunk.strip()
        if len(chunk) < 2:
            continue
        out.append(chunk)
        # 語尾の活用を落とした形も試す（片付けといて → 片付け）
        # ただし2文字以上は残す。短くしすぎると別語に化ける
        for n in range(len(chunk) - 1, max(2, len(chunk) - 3), -1):
            out.append(chunk[:n])
    seen, uniq = set(), []
    for w in out:
        if w not in seen:
            seen.add(w); uniq.append(w)
    return uniq[:60]

# ============================================================
# (2) 部品の箱 -- できることの最小単位
# ============================================================
def _period_range(name):
    n = datetime.datetime.now()
    if name == "今日":  s = n.replace(hour=0, minute=0, second=0, microsecond=0)
    elif name == "最近": s = n - datetime.timedelta(days=7)
    elif name == "今月": s = n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif name == "先月":
        first = n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        s = (first - datetime.timedelta(days=1)).replace(day=1)
        return s.timestamp(), first.timestamp()
    elif name == "今年": s = n.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif name == "去年":
        s = n.replace(year=n.year-1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        e = n.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return s.timestamp(), e.timestamp()
    else: return 0, 9e18
    return s.timestamp(), 9e18

ROOT = None          # None なら sandbox。安全層を通すと本物のフォルダになる

def place_dir(place):
    """場所名 → 実際のフォルダ。本番では安全層の関所を必ず通す"""
    if ROOT == "real":
        from safety import Guard
        return _guard().resolve(place)
    return os.path.join(SANDBOX, place)


@functools.lru_cache(maxsize=1)
def _guard():
    from safety import Guard
    return Guard()


def dig_into(d, slots):
    if slots.get("動作") == "作成":
        return d
    """名前を言われていて、それがフォルダなら、その中を見る

    「整理済み_2026-06-17 というフォルダに何がある？」に答えるため
    """
    name = slots.get("名前")
    if not name or not os.path.isdir(d):
        return d
    if os.path.isdir(os.path.join(d, name)):
        return os.path.join(d, name)
    # 完全一致しなければ、名前を含むフォルダを探す
    for e in sorted(os.listdir(d)):
        if name in e and os.path.isdir(os.path.join(d, e)):
            return os.path.join(d, e)
    # フォルダが無いなら、それはファイル名の指定。ここでは何もせず、
    # あとで「しぼる(名前)」に任せる。以前はここで例外にしていたため、
    # 「第4回テキストを…」のような指定が全部エラーになっていた
    return None


def p_search(st, slots):
    """さがす : 場所の中のファイルを全部あつめる"""
    base = place_dir(slots["場所"])
    d = dig_into(base, slots) or base
    if not os.path.isdir(d):
        raise Exception(f"{d} が無い")
    fs = [os.path.join(d, f) for f in os.listdir(d)
          if os.path.isfile(os.path.join(d, f)) and not f.startswith(".")]
    return {**st, "files": fs, "src": d}

def p_filter_kind(st, slots):
    """しぼる(種類) : 写真だけ、PDFだけ、に絞る"""
    exts = EXT[slots["種類"]]
    fs = [f for f in st["files"] if os.path.splitext(f)[1].lower() in exts]
    return {**st, "files": fs}

def p_filter_time(st, slots):
    """しぼる(時期) : 去年のだけ、今月のだけ、に絞る"""
    a, b = _period_range(slots["時期"])
    fs = [f for f in st["files"] if a <= os.path.getmtime(f) < b]
    return {**st, "files": fs}

def p_count(st, slots):
    """かぞえる : 数を出す"""
    return {**st, "answer": f"{len(st['files'])} 個"}

def p_list(st, slots):
    """ならべる : 名前順に一覧を出す"""
    names = sorted(os.path.basename(f) for f in st["files"])
    return {**st, "answer": "\n".join("  - " + n for n in names)}

def p_mkdir(st, slots):
    """つくる : 行き先のフォルダを作る

    行き先が「デスクトップ」のような場所の名前だったときは、
    新しいフォルダを作るのではなく、その場所そのものへ移す。
    ここを見ていなかったので、Downloads の中に
    「デスクトップ」という名前のフォルダができていた。
    """
    if slots.get("行き先"):
        known = _place_of(slots["行き先"])
        if known and known != slots.get("場所"):
            dest = place_dir(known)
            if not st.get("dry", True):
                os.makedirs(dest, exist_ok=True)
            return {**st, "dest": dest, "dest_is_place": True}
        name = slots["行き先"]
    else:
        tag  = slots.get("時期", "") + slots.get("種類", "")
        name = (tag or "まとめ")
    dest = os.path.join(st["src"], name)
    if not st.get("dry", True): os.makedirs(dest, exist_ok=True)
    return {**st, "dest": dest}

def p_move(st, slots):
    """うつす : 行き先へ移す"""
    moved, pairs = [], []
    for f in st["files"]:
        t = os.path.join(st["dest"], os.path.basename(f))
        if not st.get("dry", True): shutil.move(f, t)
        moved.append(t); pairs.append((f, t))
    names = sorted(os.path.basename(f) for f, _t in pairs)
    return {**st, "files": moved, "moved": len(moved),
            "pairs": st.get("pairs", []) + pairs,
            "answer": f"{len(moved)} 個を {os.path.basename(st['dest'])} へ移しました\n"
                      + "\n".join("  - " + n for n in names)}

def p_direct(st, slots):
    """じかに : パスを直接わたされたときは、探さずにそれを対象にする"""
    fs = [f for f in slots["パス"] if os.path.isfile(f)]
    if not fs:
        raise Exception("そのパスにファイルが無い")
    return {**st, "files": fs, "src": os.path.dirname(fs[0])}


def p_sort_kind(st, slots):
    """しわけ : 種類ごとのフォルダに分けて入れる（＝「整理して」の中身）

    絞り込みを言われている時にこれを使うと、言われていないものまで
    動かしてしまう。だからその時は自分から降りる。
    """
    if any(k in slots for k in ("種類", "時期", "名前")):
        raise Exception("絞り込みがあるので仕分けは使わない")
    groups = {}
    for f in st["files"]:
        ext = os.path.splitext(f)[1].lower()
        kind = next((k for k, v in EXT.items() if ext in v), "その他")
        groups.setdefault(kind, []).append(f)
    if len(groups) <= 1 and "その他" in groups:
        raise Exception("分けられる種類が無い")
    moved, lines, pairs = [], [], []
    for kind, fs in sorted(groups.items()):
        dest = os.path.join(st["src"], kind)
        if not st.get("dry", True):
            os.makedirs(dest, exist_ok=True)
        for f in fs:
            t = os.path.join(dest, os.path.basename(f))
            if not st.get("dry", True):
                shutil.move(f, t)
            moved.append(t); pairs.append((f, t))
        lines.append(f"  - {kind}/ へ {len(fs)} 個")
    return {**st, "files": moved, "moved": len(moved), "sorted": len(groups),
            "pairs": st.get("pairs", []) + pairs,
            "answer": f"{len(moved)} 個を種類ごとに分けました\n" + "\n".join(lines)}


PARTS = {
    "じかに":       dict(fn=p_direct,      needs=["パス"], uses_files=False, terminal=False),
    "しわけ":       dict(fn=p_sort_kind,   needs=[],       uses_files=True,  terminal=True),
    "さがす":       dict(fn=p_search,      needs=["場所"], uses_files=False, terminal=False),
    "しぼる(種類)": dict(fn=p_filter_kind, needs=["種類"], uses_files=True,  terminal=False),
    "しぼる(時期)": dict(fn=p_filter_time, needs=["時期"], uses_files=True,  terminal=False),
    "つくる":       dict(fn=p_mkdir,       needs=[],       uses_files=True,  terminal=False),
    "かぞえる":     dict(fn=p_count,       needs=[],       uses_files=True,  terminal=True),
    "ならべる":     dict(fn=p_list,        needs=[],       uses_files=True,  terminal=True),
    "うつす":       dict(fn=p_move,        needs=[],       uses_files=True,  terminal=True),
}

# 追加部品があれば取り込む（無くても動く）
try:
    from parts_more import PARTS_EXTRA, SEED_EXTRA
    PARTS.update(PARTS_EXTRA); SEED.update(SEED_EXTRA)
except Exception:
    pass

# ============================================================
# (3) 組み立て役 -- 置いて、実行して、確かめて進む
# ============================================================
# 動作 → その動作を成立させる終端の部品。
# ここに載っていない動作で、ものを動かす部品を通った案は認めない。
#
# 【なぜ表にしたか】
#   前は if を並べていて「ごみばこ」の行が抜けていた。抜けた動作は
#   最後の「答えが出ていればよい」に落ちるので、
#   「デスクトップを消して」に対して “仕分け” が答えを出し、それで合格した。
#   言われていない操作が、黙って実行されていた。
ACT_PART = {
    "数える":   "かぞえる",
    "一覧":     "ならべる",
    "重複":     "かさなり",
    "大きさ":   "おおきさ",
    "HTML":     "HTMLをつくる",
    "ごみばこ": "ごみばこ",
    "改名":     "なまえかえ",
}


def goal_reached(st, slots, path):
    # 言われた条件を、ちゃんと使ったか？（使っていなければ、答えは間違い）
    if "除く" in slots and "のぞく(種類)" not in path: return False
    if "行き先" in slots and "つくる" not in path: return False
    if "種類" in slots and "しぼる(種類)" not in path: return False
    if "時期" in slots and "しぼる(時期)" not in path: return False

    act = slots.get("動作")

    if act == "作成":
        return st.get("created") is not None

    if act == "移動":
        # 何も絞られていない「整理して」で全部を一箇所に放り込むと、
        # 何が動いたか本人にも分からなくなる（実際に起きた）。
        # その時は種類ごとの仕分けだけを正解とする
        if not any(k in slots for k in ("種類", "時期", "名前", "行き先")):
            return st.get("sorted") is not None
        if "名前" in slots and "しぼる(名前)" not in path:
            return False
        return st.get("moved") is not None

    if act in ACT_PART:
        return ACT_PART[act] in path

    # 知らない動作。ここで「答えがあればよい」と通すと、
    # 頼まれていない操作まで正解になってしまう。
    # 読むだけの案なら通し、ものを動かす案は通さない
    if any(p in DESTRUCTIVE for p in path):
        return False
    return "answer" in st


def verify(st, name, slots=None):
    """確かめる。おかしければ理由を返す

    ただし「数える」「一覧」なら 0 件も立派な答えなので、枝を切らない
    """
    zero_ok = slots and slots.get("動作") in ("数える", "一覧")
    if name == "さがす" and not st["files"]:
        return None if zero_ok else "1個も見つからない"
    if name.startswith("しぼる") and not st["files"]:
        return None if zero_ok else "しぼったら0個になった"
    if name == "うつす" and st.get("moved", 0) == 0:
        return "1個も移せなかった"
    return None

@functools.lru_cache(maxsize=1)
def _policy():
    from policy import Policy
    return Policy(os.path.join(HERE, "policy.json"))


def solve(slots, verbose=True, allow=None):
    """見込みの高い手から試す。実績が無ければ、これまで通り幅優先

    allow を渡すと、その部品だけを使う（読み取り専用にする時に使う）
    """
    try:
        pol = _policy()
    except Exception:
        pol = None
    start = ({"files": None, "dry": True}, [])
    queue = [start]
    seen  = set()          # 通った「道すじ」
    reached = set()        # たどり着いた「結果」。順番違いの同じ結果を切る
    tried = 0
    shown = 0              # 画面に出した行数。出しすぎると読めなくなる
    MAX_TRY, MAX_SHOW = 300, 60
    # 0件で終わる案は「答えではある」が弱い。もっと良い案が無い時だけ使う
    fallback = None
    while queue:
        if tried >= MAX_TRY:
            if verbose:
                print(f"    → {MAX_TRY} 通り試して見つからないので、ここで打ち切ります")
            break
        if pol:            # 見込みの高い枝から取り出す（最良優先）
            queue.sort(key=lambda q: -pol.rank(slots, q[1]))
        st, path = queue.pop(0)
        if len(path) >= 6:
            continue
        names = [n for n in PARTS if allow is None or n in allow]
        if pol:
            names = pol.order(names, slots, path)
        for name in names:
            spec = PARTS[name]
            if name in path:                          continue
            if any(n not in slots for n in spec["needs"]): continue
            if spec["uses_files"] and st["files"] is None: continue
            # 「探す系」は最初の一手にしか置けない。
            # 途中で置くと、それまでの絞り込みを台無しにしてしまう
            if not spec["uses_files"] and path:        continue
            key = tuple(path + [name])
            if key in seen: continue
            seen.add(key)
            tried += 1
            indent = "  " * (len(path) + 1)

            def _show(line):
                """出しすぎ防止。以前は同じ行が200回以上流れて読めなかった"""
                nonlocal shown
                if not verbose:
                    return
                shown += 1
                if shown <= MAX_SHOW:
                    print(line)
                elif shown == MAX_SHOW + 1:
                    print("    …（途中経過が長いので、ここから先は省略します）")
            try:
                nst = PARTS[name]["fn"](st, slots)
            except Exception as e:
                _show(f"{indent}{name} を置く → 失敗（{e}） ✗")
                if pol: pol.lose(slots, path, name, str(e)[:40])
                continue
            bad = verify(nst, name, slots)
            if bad:
                _show(f"{indent}{name} を置く → 確かめる → {bad} ✗")
                if pol: pol.lose(slots, path, name, bad)
                continue
            # 「しぼる(種類)→しぼる(時期)」と「しぼる(時期)→しぼる(種類)」は
            # 結果が同じ。道すじだけで覚えていたので、順番違いが全部残り、
            # 枝が爆発して250行の途中経過が流れていた
            rk = (frozenset(nst.get("files") or []), nst.get("dest"),
                  "answer" in nst, tuple(sorted(path + [name])))
            if rk in reached:
                continue
            reached.add(rk)

            got = (f"{len(nst['files'])}個" if nst.get("files") is not None else "")
            _show(f"{indent}{name} を置く → 確かめる → {got} ✓")
            npath = path + [name]
            if PARTS[name].get("terminal"):
                if goal_reached(nst, slots, npath):
                    if not nst.get("files"):
                        # 0件の答えは常に保留。非0件の案が見つからなければ最後に使う
                        if fallback is None:
                            fallback = (npath, nst)
                            _show(f"{indent}  → 0件。保留して探索を続ける")
                        continue
                    if verbose: print(f"{indent}★ できた（{tried}回ためした）")
                    if pol: pol.win(slots, npath)
                    return npath, nst
                _show(f"{indent}  → 条件を使い切っていない ✗")
                if pol: pol.lose(slots, path, name, "条件を使い切っていない")
                continue
            if goal_reached(nst, slots, npath):
                if not nst.get("files"):
                    if fallback is None:
                        fallback = (npath, nst)
                    queue.append((nst, npath))
                    continue
                if verbose: print(f"{indent}★ できた（{tried}回ためした）")
                if pol: pol.win(slots, npath)
                return npath, nst
            queue.append((nst, npath))
    if fallback:
        if verbose: print(f"  ★ 0件の答えを採用（{tried}回ためした）")
        if pol: pol.win(slots, fallback[0])
        return fallback
    return None, None

# 読むだけで済む動作。聞かれているときも、そのまま活かしてよい
READ_ACTS = {"数える", "一覧", "重複", "大きさ", "もぐる"}

DESTRUCTIVE = {"うつす", "しわけ", "なまえかえ", "ごみばこ", "HTMLをつくる",
               "ファイルをつくる", "フォルダをつくる"}

def preview_plan(plan, slots):
    """本番の前に、下見でどうなるか見ておく"""
    st = {"files": None, "dry": True}
    for name in plan:
        st = PARTS[name]["fn"](st, slots)
    return st


def run_plan(plan, slots, guarded=None):
    """ノートの手順を、本番モードで実行する

    変更を伴う手順は、実行前に必ず関所を通す（本物のフォルダの時）
    """
    if guarded is None:
        guarded = (ROOT == "real")
    if guarded and any(p in DESTRUCTIVE for p in plan):
        g = _guard()
        pv = preview_plan(plan, slots)
        v = g.check_plan(plan, slots, pv)
        print(f"\n  ── 関所 ── {v['level']}： {v['summary']}")
        for r in v.get("reasons", []):
            print(f"     ・{r}")
        if not v["ok"]:
            raise PermissionError("関所が止めました: " + "; ".join(v.get("reasons", [])))
        if v["level"] != "安全" and not g.confirm(v):
            raise PermissionError("実行しませんでした")
    st = {"files": None, "dry": False}
    for name in plan:
        st = PARTS[name]["fn"](st, slots)

    # 実行「後」に、実際に動いた分だけを記録する。
    # 以前は下見の結果を書いていたので items が空になり、取り消せなかった
    if st.get("pairs"):
        _guard().journal("plan", {
            "plan": plan, "slots": {k: v for k, v in slots.items()},
            "src": st.get("src", ""), "dest": st.get("dest", ""),
            "items": [{"from": a, "to": b} for a, b in st["pairs"]],
            "note": ("本物" if ROOT == "real" else "練習用")})
    return st

def vocab_table():
    """スロットごとに、選べる値の一覧。先生に「この中から選べ」と示すため"""
    v = {}
    for _, (slot, val) in SEED.items():
        v.setdefault(slot, set()).add(val)
    return {k: sorted(x) for k, x in v.items()}

def parts_desc():
    """部品の説明。fn の docstring をそのまま使う"""
    return {n: (sp["fn"].__doc__ or "").strip().split("\n")[0]
            for n, sp in PARTS.items()}

def try_plan(plan, slots):
    """先生の案を、下見モードで実際に実行して確かめる。ダメなら理由を返す"""
    st = {"files": None, "dry": True}
    for name in plan:
        if name not in PARTS:
            return None, f"そんな部品は無い: {name}"
        try:
            st = PARTS[name]["fn"](st, slots)
        except Exception as e:
            return None, f"{name} で失敗: {e}"
        bad = verify(st, name, slots)
        if bad:
            return None, f"{name} の後: {bad}"
    if not goal_reached(st, slots, plan):
        return None, "最後まで行っても目的を満たしていない"
    return st, None

# ============================================================
# (4) ノート
# ============================================================
def load_note():
    p = notebook_path()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f: return json.load(f)
        except Exception:
            pass
    return {}

def save_note(nb):
    with open(notebook_path(), "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=2)

def shape_of(slots):
    """スロットの「形」。中身ではなく、どの種類が埋まっているか"""
    return "+".join(sorted(slots.keys())) + " / " + slots.get("動作", "?")

# ============================================================
# 入口
# ============================================================
def handle(text, readonly=False, quiet=False):
    """readonly=True なら、ものを動かす部品は一切使わない（問い合わせ用）

    quiet=True なら、組み立ての途中経過を出さず、答えだけを見せる。
    戻り値は答えの文字列（会話の流れに残して、あとで聞き返せるようにする）
    """
    load_learned(); load_grown()
    _p = (lambda *a, **k: None) if quiet else print
    print(f"\n入力： 「{text}」")
    _p("─" * 58)

    t0 = time.time()
    _p("[1] カードを引く")
    slots = draw_cards(text, verbose=not quiet)
    _p(f"    → {slots if slots else '（何も引けなかった）'}")

    if readonly:
        # 問いには答えを見せるだけ。ものを動かす部品は最初から使わない
        allow = set(PARTS) - DESTRUCTIVE
        # 「同じファイルある？」「ぜんぶで何メガ？」は、聞かれてはいるが
        # 一覧でも数えるでもない。ここで潰していたので、部品があるのに
        # 届かず、ただのファイル一覧が返っていた
        if slots.get("動作") not in READ_ACTS:
            want_count = any(w in text for w in
                             ("いくつ", "何個", "何枚", "何件", "どれだけ", "何件"))
            slots["動作"] = "数える" if want_count else "一覧"
            _p(f"    聞かれているので、動作は【{slots['動作']}】として扱います")
    else:
        allow = None

    # 作成のときの名前は「これから作る名前」なので、探しに行ってはいけない
    if (slots.get("名前") and slots.get("場所")
            and slots.get("動作") != "作成"):
        try:
            if dig_into(place_dir(slots["場所"]), slots) is not None:
                # 名前はフォルダだった → 場所として使い切ったので、
                # 絞り込みの条件としては残さない
                slots.pop("名前", None)
        except Exception as e:
            print("─" * 58)
            _p(f"答え： {e}")
            return

    if "パス" in slots and ROOT != "real":
        print("─" * 58)
        _p("答え： これは本物のファイルのパスです。今は練習モードなので触りません。")
        _p("      本気でやるなら /mode 本番 にしてください。")
        return

    # 場所を言わずに「さっき撮ったやつを見せて」と言われることがある。
    # 種類か時期がはっきりしているなら、デスクトップのことだと受け取る。
    # 分からないまま外の先生に聞くと3秒かかって、しかも答えが出なかった
    if ("場所" not in slots and "パス" not in slots
            and "動作" in slots and ("種類" in slots or "時期" in slots)):
        slots["場所"] = "Desktop"
        _p("    場所を言われていないので、デスクトップのことだと受け取ります")

    if "動作" not in slots or ("場所" not in slots and "パス" not in slots):
        _p("\n[1b] カードでは足りない → 先生に相談する")
        import consult
        cands, err = consult.ask_slots(text, vocab_table())
        if err: print(f"    {err}")
        for who, got, words in cands:
            merged = {**got, **slots}          # カードで分かった分を優先
            if "動作" in merged and "場所" in merged:
                _p(f"    {who} の案を採用： {got}")
                slots = merged
                new = {w: v for w, v in words.items() if w not in SEED}
                if new:
                    save_learned(new)
                    for w, (sl, va) in new.items():
                        _p(f"    ★ 新しいカードを覚えた： 「{w}」→【{va}】")
                break
            _p(f"    {who} の案は足りない： {got} ✗")
    if "動作" not in slots or ("場所" not in slots and "パス" not in slots):
        print("    → 結局わかりませんでした")
        return "何を言われたのか分かりませんでした"

    shape = shape_of(slots)
    nb    = load_note()
    plan  = None

    _p("\n[2] ノートを見る")
    if shape in nb and not (readonly and
                            any(p in DESTRUCTIVE for p in nb[shape]["手順"])):
        plan = nb[shape]["手順"]
        _p(f"    → 知っている形だった： {' → '.join(plan)}")
        chk, bad = try_plan(plan, slots)
        if bad or not chk.get("files"):
            # 覚えた手順が空振り。状況が変わったので組み立て直す
            _p(f"    → ただし今回は空振り（{bad or '0件'}）。組み立て直します")
            plan = None
        else:
            st = run_plan(plan, slots)
            nb[shape]["回数"] += 1; save_note(nb)
            _p(f"\n[3] 実行（探さずに即実行）")
    if plan is None:
        if shape not in nb:
            _p("    → 知らない形。はじめての命令です")
        _p("\n[3] 組み立てる（置いて、実行して、確かめる）")
        plan, st = solve(slots, verbose=not quiet, allow=allow)
        if plan is None:
            _p("    → 自力では組み立てられませんでした")
            _p("\n[3b] 先生に相談する（案は信用せず、必ず下見で確かめる）")
            import consult
            cands, err = consult.ask_plans(text, slots, parts_desc())
            if err: print(f"    {err}")
            plan = None
            for who, cand in cands:
                st2, bad = try_plan(cand, slots)
                if bad:
                    _p(f"    {who}: {' → '.join(cand)}")
                    _p(f"       確かめる → {bad} ✗")
                    continue
                _p(f"    {who}: {' → '.join(cand)}")
                _p(f"       確かめる → 通った ✓ これを採用")
                plan = cand
                break
            if plan is None:
                print("    → 先生の案も全部落ちました")
                return "やり方を組み立てられませんでした"
        _p(f"\n[4] 決まった手順を、本番で1回だけ実行する")
        st = run_plan(plan, slots)
        nb[shape] = {"手順": plan, "回数": 1}
        save_note(nb)
        _p(f"\n[5] ノートに書いた： {shape}")
        _p(f"    {' → '.join(plan)}")

    dt = time.time() - t0
    _p("─" * 58)
    where = "本物のフォルダ" if ROOT == "real" else "練習用フォルダ(sandbox)"
    print(f"答え：（{where}を見ています）")
    print(f"      {st.get('answer','（完了）').replace(chr(10), chr(10)+'      ')}")
    print(f"かかった時間： {dt*1000:.1f} ミリ秒")
    return st.get("answer", "（完了）")

def _wipe_dir(d, tries=6):
    """フォルダの中身を、確実に空にする。

    exFAT（外付けSSD）では、ファイルを消すそばから macOS が
    「._」という影のファイルを作り直す。そのせいで rmtree が
    「中が空でない」と言って黙って失敗し、
    /reset しても古いフォルダが残り続けていた。

    下から順に消して、それを何度か繰り返す。
    ここで消すのは練習用フォルダの中だけ（本物には触らない）。
    """
    if not os.path.isdir(d):
        return
    if not os.path.abspath(d).startswith(os.path.abspath(SANDBOX)):
        raise Exception("練習用フォルダの外は、絶対に消さない: " + d)

    # exFAT では、ファイルを消してもフォルダの情報の更新が少し遅れる。
    # そのため直後の rmdir が「まだ中身がある」と言って失敗する。
    # 消す → 少し待つ → もう一度、を繰り返す。
    for i in range(tries):
        for root, dirs, files in os.walk(d, topdown=False):
            for f in files:
                try: os.remove(os.path.join(root, f))
                except OSError: pass
            for x in dirs:
                try: os.rmdir(os.path.join(root, x))
                except OSError: pass
        try:
            os.rmdir(d)
            return
        except OSError:
            pass
        if i < tries - 1:
            time.sleep(0.15)     # 情報の更新を待つ


def make_demo():
    now = time.time()
    Y = 365*24*3600
    spec = {
        "Desktop": [("旅行1.jpg", now-1.2*Y), ("旅行2.jpg", now-1.1*Y),
                    ("旅行3.png", now-1.3*Y), ("最近.jpg", now-3*24*3600),
                    ("会議.pdf", now-1.2*Y),  ("メモ.txt", now-10*24*3600),
                    ("動画.mp4", now-1.5*Y)],
        "Downloads": [("請求書.pdf", now-2*24*3600), ("契約.pdf", now-5*24*3600),
                      ("古い.pdf", now-1.4*Y), ("bg.png", now-40*24*3600)],
    }
    # exFAT では macOS が「._」ファイルを勝手に作るため、消してから消す
    os.environ.setdefault("COPYFILE_DISABLE", "1")
    if os.path.exists(SANDBOX):
        for root, dirs, files in os.walk(SANDBOX):
            for f in files:
                if f.startswith("._"):
                    try: os.remove(os.path.join(root, f))
                    except OSError: pass
        shutil.rmtree(SANDBOX, ignore_errors=True)
        if os.path.exists(SANDBOX):
            shutil.rmtree(SANDBOX, ignore_errors=True)
    for d, files in spec.items():
        p = os.path.join(SANDBOX, d)
        _wipe_dir(p)
        os.makedirs(p, exist_ok=True)
        for name, mt in files:
            fp = os.path.join(p, name)
            # 中身も大きさも、それらしくしておく。
            # 全部1バイトにしていたため「合計 7 B」になり、
            # さらに全ファイルが同じ中身として重複判定されていた
            ext = os.path.splitext(name)[1].lower()
            size = {".jpg": 320_000, ".jpeg": 320_000, ".png": 180_000,
                    ".mp4": 12_000_000, ".mov": 9_000_000,
                    ".pdf": 240_000, ".txt": 1_800, ".md": 900,
                    ".mp3": 4_500_000}.get(ext, 2_000)
            # 名前ごとに違う中身にする（たまたま一致させない）
            seed = (name.encode("utf-8") * 64)[:64]
            with open(fp, "wb") as fh:
                fh.write(seed)
                fh.write(b"\0" * max(0, size - len(seed)))
            os.utime(fp, (mt, mt))
        # 重複を試せるように、わざと同じ中身のものを1組だけ置く
        if d == "Desktop":
            src = os.path.join(p, "旅行1.jpg")
            if os.path.exists(src):
                dup = os.path.join(p, "旅行1のコピー.jpg")
                shutil.copy2(src, dup)
    # ノートは消さない。覚えた手順が今の状況に合わなければ、
    # handle が空振りを見つけて自分で組み立て直す（自己修復がある）。
    # ここで毎回消していたので、練習用フォルダを作り直すたびに
    # 覚えたことが失われ、いつまでも賢くならなかった
    print(f"デモ用のファイルを作りました： {SANDBOX}")
    for d in spec:
        print(f"  {d}/ : " + ", ".join(n for n, _ in spec[d]))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="*")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--note", action="store_true")
    a = ap.parse_args()
    if a.demo:   make_demo()
    elif a.note: print(json.dumps(load_note(), ensure_ascii=False, indent=2))
    elif a.text: handle(" ".join(a.text))
    else:        print(__doc__)
