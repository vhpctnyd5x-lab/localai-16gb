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


def simnote_path():
    """にた状況で引くノート。こちらも練習用と本物で分ける"""
    return os.path.join(HERE, "simnote_real.json" if ROOT == "real"
                        else "simnote.json")


# 「じっくり」考えるか。settings の /set じっくり true で入れ替わる
THINK_HARD = False

# ノートが実際に当たった回数。
#
# 前は「ノートの 回数 の合計」を前後で引き算して測っていた。
# ところが手順を組み立て直すたびに 回数 が 1 に戻る作りだったので、
# 合計が下がることがあり、当たった回数が **マイナス** になっていた
# （bench で -23/33 が出た）。
# 「ノート当たりが 26→21 と下がっていく」のも、これが原因だった疑いが濃い。
# 数えたいのは当たった回数そのものなので、その場で数える。
NOTE_HIT = {"形": 0, "にた": 0}


def note_hit_total():
    return NOTE_HIT["形"] + NOTE_HIT["にた"]

_SIMNOTE = {}


def simnote():
    """にた状況ノートを開く（1回だけ読んで、あとは使い回す）"""
    p = simnote_path()
    if p not in _SIMNOTE:
        import note_hdv
        _SIMNOTE[p] = note_hdv.SimNote(p)
    return _SIMNOTE[p]
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
    # 「資料」を PDF だけにしていたので「デスクトップの資料は何個」で
    # メモ.txt が数から落ちていた（実測: 2個のはずが1個）。
    # 日ごろ言う「資料」は 書類ぜんぶ のこと。PDF に限らない。
    "pdf":("種類","PDF"), "資料":("種類","書類"),
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
    "1年前":("時期","去年"), "一年前":("時期","去年"), "１年前":("時期","去年"),

    # ------------------------------------------------------------
    # 言い換えを測って足したもの（2026-08-28）
    #
    # bench.py の33問は 100% 当たるのに、
    # 同じことを違う言い方で頼む25問では 68% しか当たらなかった。
    # 外した8問のうち7問が「その言い方の札が無い」だけだった。
    # 勘ではなく、実測で外したものを足している。
    # 測り直しは  python3 iikae_bench.py
    # ------------------------------------------------------------
    "絵":("種類","画像"), "写真ファイル":("種類","画像"),
    "映像":("種類","動画"), "動画ファイル":("種類","動画"),
    "音声":("種類","音楽"), "音声ファイル":("種類","音楽"),
    "サウンド":("種類","音楽"), "音楽ファイル":("種類","音楽"),
    "メモ書き":("種類","テキスト"), "文書":("種類","書類"),
    "落とした":("場所","Downloads"), "落としてきた":("場所","Downloads"),
    "ダウンロードフォルダ":("場所","Downloads"),
    "枚ある":("動作","数える"), "個ある":("動作","数える"),
    "何枚ある":("動作","数える"), "数を":("動作","数える"),
    "数は":("動作","数える"), "枚数":("動作","数える"),
    "個数":("動作","数える"), "件数":("動作","数える"),
    "どれ":("動作","一覧"), "ずらっと":("動作","一覧"),
    "中身を":("動作","一覧"), "ファイル名を":("動作","一覧"),
    # 「枚数を教えて」は 一覧 ではなく 数える。
    # 「教えて」(3文字)が「枚数」(2文字)に勝って一覧になっていたので、
    # まとめて1枚の長い札にして、そちらが勝つようにする
    "枚数を教えて":("動作","数える"), "個数を教えて":("動作","数える"),
    "件数を教えて":("動作","数える"), "数を教えて":("動作","数える"),
    "枚数を":("動作","数える"), "個数を":("動作","数える"),
}

LEARNED = os.path.join(HERE, "learned_cards.json")

def load_grown():
    """使いながら育てたカードを、種火に足す"""
    try:
        import grow
        return grow.apply_to(SEED)
    except Exception:
        return 0


# もとから知っている札と けんかする教わり方は、受け取らない。
#
# 実際に入っていた誤り: 「Desktop」→ 対象=フォルダ
# Desktop は 場所 であって 対象 ではない。
# 対象 が どこにも使われていない 死んだ枠 だったので、
# 長いあいだ 害が出ずに残っていた。
# 対象 を使う部品を足した とたん、
# 「Desktopの写真の数は」が 0個 になった（実測 25→21）。
# 使われていない枠は、間違いを隠す。
_SEED0_LOW = {}


def _ayashii(w, slot, val):
    """教わった札が、もとの札と食い違っていないか

    大文字小文字は同じものとして見る。
    誤りは「Desktop」→対象 という形で入っていた。
    もとの札には小文字の「desktop」→場所 があり、
    そのままの綴りでは見つからず 素通りしていた。
    """
    if not _SEED0_LOW:
        for k, v in _SEED0.items():
            _SEED0_LOW.setdefault(k.lower(), v)
    moto = _SEED0_LOW.get(w.lower())
    return moto is not None and moto[0] != slot


def load_learned():
    """先生から教わったカードを読み込んで、種火に足す"""
    if os.path.exists(LEARNED):
        try:
            with open(LEARNED, encoding="utf-8") as f:
                for w, (slot, val) in json.load(f).items():
                    if _ayashii(w, slot, val):
                        continue          # もとの札と枠が違う。採らない
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
        if _ayashii(w, slot, val):
            continue                      # 書き込む前に断る
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
#
# ★ 2026-09-06 に直した。前は 3つの言い方で名前を落としていた:
#     「試験用 というフォルダ」     … 空白が入ると取れない（文字クラスが \s を除く）
#     「「試験用」というフォルダ」   … かぎ括弧が区切りなので中身が取れない
#     「試験用 という名前のフォルダ」 … 同じく空白で落ちる
#   落ちると 下流が「というフォルダ」を名前として拾い、
#   **本物のデスクトップに「というフォルダ」が出来た**（実際に起きた）。
#   しかも一度できると、それが「実在するフォルダ名」として最優先で守られ、
#   **間違いが正解として固定される**。名前を落とすのは、ただの取りこぼしでは済まない。
_TOIU = _re.compile(
    r"(?:"
    r"「([^「」\n]{1,24})」"
    r"|『([^『』\n]{1,24})』"
    r"|\"([^\"\n]{1,24})\""
    r"|'([^'\n]{1,24})'"
    r"|([^\s、。，．,」』）)にをのはがでともやへ]{2,24})"
    r")[\s　]*(?:という|といった|と言う)")


def _jitsuzai_folders():
    """いま本当に在るフォルダの名前（デスクトップなどの直下）。

    名前を「それらしい形か」で当てるのをやめて、実物を見に行く。

    ── なぜ要るか ────────────────────────────────
    「整理済み」というフォルダが本当に在るのに、
    「整理済みには何がある？」と聞くと、
    中の「整理」が 動作【移動】として読まれ、
    さらに「には」が行き先と読まれて、
    **質問が「整理済みへ移せ」という命令になっていた。**

    下の _mask_names は、まさにこの事故のために作られている。
    だが守れるのは「整理済み_2026-06-17」のように
    数字や記号が付いた形だけで、「整理済み」だけだと素通りしていた。

    形で当てるから漏れる。実物に当たれば漏れない。
    """
    out = []
    for p in ("Desktop", "Downloads", "Documents"):
        try:
            d = place_dir(p)
            if not os.path.isdir(d):
                continue
            for n in os.listdir(d):
                if n.startswith(".") or not os.path.isdir(os.path.join(d, n)):
                    continue
                # 丸ごとの名前と、区切りで割った部分の両方を候補にする。
                # 人は「整理済み_2026-06-17には何がある？」とは書かない。
                # 「整理済みには」と書く。
                for w in [n] + _re.split(r"[_\-.\s　]+", n):
                    w = w.strip()
                    if len(w) < 2:
                        continue
                    # 札に載っている語は、上書きしない。
                    #
                    # このユーザーのデスクトップには「画像」というフォルダが在る。
                    # それを固有名として守ると、
                    # 「デスクトップの画像を数えて」の「画像」が
                    # 種類ではなく名前になり、いままで動いていたものが壊れる。
                    #
                    # 意味の決まっている語は、そのままにしておく。
                    # 意味を持たない語が実物と一致したときだけ、固有名とみなす。
                    if w in SEED or w.lower() in SEED:
                        continue
                    out.append((w, p, n))
        except Exception:
            continue
    # 長い名前から先に見る（「整理済み_2026-06-17」を「整理済み」より優先）
    out.sort(key=lambda x: -len(x[0]))
    return out


def _mask_names(text):
    """「整理済み_2026-06-17」のような固有名を伏せる。

    伏せないと、中の「整理」を動作だと誤読して、
    質問なのにファイルを動かす事故が起きる（実際に起きた）
    """
    names, out = [], list(text)

    # まず、本当に在るフォルダの名前を守る。
    # 形で当てるより先に、実物に当たる
    for name, _basho, _full in _jitsuzai_folders():
        i = text.find(name)
        if i < 0 or out[i] == "":
            continue
        names.append(name)
        for k in range(i, i + len(name)):
            out[k] = ""

    # 「作業用というフォルダ」→ 作業用 が名前
    #   括弧つき・空白つきにも当たるので、どの組が当たったかを見る
    for m in _TOIU.finditer(text):
        gi = next((i for i, g in enumerate(m.groups(), 1) if g), None)
        if gi is None:
            continue
        w = (m.group(gi) or "").strip()
        # 括弧で囲ってあれば1文字でも名前。裸なら2文字から（助詞を拾わないため）
        shita = 1 if gi <= 4 else 2
        if shita <= len(w) <= 24 and w not in ("それ", "これ", "あれ", "こう", "そう"):
            names.append(w)
            for i in range(m.start(gi), m.end(gi)):
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
    # ★ 「書類フォルダに移して」の「書類フォルダ」は 場所。
    #   2026-09-14 の実測: ここで 書類 が「書類ファイル（種類）」と読まれて行き先が消え、
    #   代わりに **動かす相手のファイル名** が行き先に回り、
    #   「そのファイル名のフォルダ」を作ってそこへ入れようとしていた。
    #   知っている場所の名前＋「フォルダ」なら、場所として受け取る。
    if dest:
        import re as _re2
        _d = _re2.sub(r"(フォルダ|ホルダ|ディレクトリ)$", "", dest).strip("　 ")
        try:
            from safety import PLACE_MAP as _PM
        except Exception:
            _PM = {}
        if _d and _d != dest and _d in _PM:
            dest = _d

    # 「ファイル」「フォルダ」そのものは行き先の名前ではない。
    # 「PDFというデスクトップのファイルに移動」で行き先が「ファイル」に
    # なってしまっていた
    if dest in ("それ", "そこ", "ここ", "あそこ", "ファイル", "フォルダ",
                "ところ", "とこ", "もの", "やつ", "中", "なか") or len(dest) < 1:
        dest = None

    # ── 形式の名前を、行き先にしてはいけない ────────────────
    # 「写真をPDFにまとめて」で 行き先=PDF となり、
    # PDF という名前のフォルダを作って 画像5枚を そこへ移していた。
    # 頼まれたのは 形を変えること で、移すことではない。
    # 「できません」と言うべきところで、堂々と別のことをしていた。
    # これは、棚に無いことを できないと言えていない、という
    # いちばん危ない形の失敗。
    if dest:
        d2 = dest.strip("　 ").upper()
        try:
            from safety import PLACE_MAP as _PM2
        except Exception:
            _PM2 = {}
        # 場所の名前（書類・デスクトップ…）は「形式の名前」ではない。素通しする
        moto = None if dest in _PM2 else (_kind_of(dest) or (d2 if d2 in _KATACHI else None))
        if moto:
            _tsumazuki(text, {"行き先っぽい語": dest},
                       f"「{dest}」は形式の名前。形を変える部品が無い", "札引き")
            return None, None
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
    # ── 似ているだけで「壊す動作」を決めてはいけない ──────────────
    #
    # 実測で起きた事故：
    #   sim("消して", "して") = 0.5 （ちょうど下のしきい値）
    #   日本語で「〜にして」「〜くして」で終わる文は、
    #   文法が述語を「して」と切り出す。
    #     この動画をMP3にして / 画像をZIPにして / 画像をきれいにして
    #   これが全部 動作【ごみばこ】になり、ファイルがゴミ箱へ移された。
    #
    # しかもこれは「消して」を覚えたあとに発火する。
    # 素のカードだけなら起きない＝使うほど危なくなる形だった。
    #
    # ものを壊す動作は、はっきり言われた時だけ。
    # 「似ているから、たぶん消すことだろう」は、絶対にやらない。
    best, score = None, 0.0
    for k, (slot, val) in SEED.items():
        if slot != "動作" or len(k) < 2:
            continue
        if val in KOWASU_ACTS:
            continue                      # 壊す動作は、あてずっぽうの対象にしない
        sc = sim(k, pred)
        if sc > score:
            best, score = val, sc
    return best if score >= 0.5 else None


# ファイルの形の名前。行き先にはなりえない
_KATACHI = {"PDF", "JPG", "JPEG", "PNG", "GIF", "HEIC", "TIFF", "BMP", "SVG",
            "MP3", "WAV", "AAC", "FLAC", "M4A", "AIFF",
            "MP4", "MOV", "AVI", "MKV", "WEBM",
            "ZIP", "TAR", "GZ", "TXT", "CSV", "HTML", "MD", "DOCX", "XLSX"}


# いま本当に作れる形式。ここに無い形式を頼まれたら「できません」と言う。
# 部品が増えたら、ここも増やす。
_TSUKURERU_KATACHI = {"HTML"}

# 「作って」と言われても、作る部品を持っていないもの。
# ここに当たったら 探さずに断る
_TSUKURENAI = _re.compile(
    r"(ゲーム|げーむ|アプリ|あぷり|ソフト|プログラム|スクリプト|"
    r"ツール|道具|システム|サイト|ウェブサイト|ホームページ|"
    r"データベース|グラフ|表計算|動画|音楽|曲|絵|イラスト|画像|写真)")

# 「◯◯にして」「◯◯にまとめて」「◯◯に変換して」の ◯◯
_KATACHI_NI = _re.compile(
    r"([A-Za-z0-9]{2,5})\s*(?:形式|ファイル|フォーマット)?\s*(?:に|へ)\s*"
    r"(?:して|し(?:たい|ろ)|まとめ|変換|変え|かえ|直し|なおし|出力|書き出)")


def _katachi_youkyuu(text):
    """「ZIPにして」「PDFにまとめて」の、頼まれた形式。無ければ None

    これを見ずにいたので、ZIP を頼まれて HTML を作っていた。
    「写真をPDFにまとめて」で PDF という名のフォルダを作ったのと同じ形で、
    頼まれた形式を作れないことを言わずに、別のもので埋めていた。
    """
    m = _KATACHI_NI.search(text)
    if not m:
        return None
    k = m.group(1).upper()
    return k if k in _KATACHI else None


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


# 直前の札引きで、どの枠を どれくらいの確からしさ で埋めたか。
# draw_cards のたびに書き換わる。slots には入れない（下の注記を見よ）
KAKUDO = {}


def kakudo_ima():
    """直前の札引きの確からしさ。いちばん怪しい枠と、その値を返す"""
    if not KAKUDO:
        return None, 1.0
    waku = min(KAKUDO, key=lambda k: KAKUDO[k])
    return waku, KAKUDO[waku]


_TEN = _re.compile(r"[、，,]")

# 打ち消しの言い方。動作の言葉の すぐ後ろに来る
_UCHIKESHI = _re.compile(
    r"^(は|を|も|)\s*(しないで|しなくて|せずに|せず|しないでください|"
    r"は(いら|要ら)ない|はしない|なくていい|は不要|なしで|しなくていい|"
    r"はやめて|ないで)")


def _uchikeshi_wo_kesu(text):
    """打ち消されている動作の言葉を、札から見えなくする"""
    for key, (slot, val) in SEED.items():
        if slot != "動作" or len(key) < 2:
            continue
        i = 0
        while True:
            i = text.find(key, i)
            if i < 0:
                break
            ato = text[i + len(key):i + len(key) + 10]
            if _UCHIKESHI.match(ato):
                text = text[:i] + "　" * len(key) + text[i + len(key):]
            i += len(key)
    return text


def draw_cards(text, verbose=False):
    """入力の文から、カードを引いて概念スロットを埋める"""
    # 読点は 語ではない。札を見るときは 無いものとして扱う。
    #
    # 「〜の数を教えて」は 数える。
    # ところが「〜の数を、教えて」と 読点が一つ入るだけで、
    # 「数を教えて」という札が文の中に見えなくなり、
    # 「教えて」→一覧 が勝って 答えが変わっていた（壊す側が見つけた）。
    # 人は読点を打っても 同じことを言っているつもりでいる。
    text = _TEN.sub("", text)
    raw_text = text
    paths = _paths_in(text)
    for q in paths:                      # パスの中の語をカードに引かせない
        text = text.replace(q, " ")
    text, _names = _mask_names(text)
    low = text.lower()
    # どれを場所にするかは「文の中で いちばん前に出たもの」。
    # 日本語は 場所を先に言う。「机の上のドキュメントの数を」なら
    # 机の上＝場所、ドキュメント＝種類。長いほうを採ると
    # ドキュメント(6字)が机の上(4字)に勝ってしまい、場所が Documents になった。
    # 同じ位置から始まるものだけ、長いほうを採る（ダウンロード ⊂ ダウンロードフォルダ）。
    _basho_kari, _ichi, _nagasa = None, None, 0
    for key, (sl, val) in SEED.items():
        if sl != "場所":
            continue
        i = low.find(key.lower())
        if i < 0:
            continue
        if _ichi is None or i < _ichi or (i == _ichi and len(key) > _nagasa):
            _basho_kari, _ichi, _nagasa = val, i, len(key)
    if _basho_kari is not None:
        nagasa = _nagasa
        # 場所のうしろに付く「ところ」「とこ」「の中」も いっしょに消す。
        # 「落としたところ」は 札が「落とした」までなので「ところ」が残り、
        # そこから 名前='ころ' が拾われて、名前で絞って 0件になっていた
        for shippo in ("のところ", "ところ", "のとこ", "とこ", "の中"):
            if text[_ichi + nagasa:].startswith(shippo):
                nagasa += len(shippo)
                break
        text = text[:_ichi] + "　" * nagasa + text[_ichi + nagasa:]
        low = text.lower()
    # 「整理はしないで」「捨てずに」は、やらないでほしい という意味。
    # 打ち消されている動作の言葉は、札として見ない。
    #
    # 実際に起きた（壊す側が見つけた）:
    #     「デスクトップの画像は何個？ 整理はしないで」
    #      → 「整理」を 移動 の合図として拾い、本当に仕分けが走った。
    #        やめてくれ と言われた ことを やっていた。
    text = _uchikeshi_wo_kesu(text)
    low = text.lower()

    # 場所を先に決めてから、ここへ来ること。
    # 順番を逆にしていたら「書類フォルダの中身」で
    # 「フォルダの中」が先に消され、場所の札が消えていた
    # 「フォルダ」は、いつも 数える相手 とはかぎらない。
    #   ダウンロードフォルダの PDF の数   … 場所の名前の一部
    #   写真をフォルダに入れといて         … 入れる先
    #   奥のフォルダまで全部見せて         … もぐる先
    # これを全部 対象=フォルダ として拾い、
    # ファイルを 0 件に絞ってしまっていた（実測 25→21）。
    # 相手として言われた「フォルダ」だけを残す。
    # 消すのは「フォルダ」の4文字だけ。前後は残す。
    # まるごと消したら「ダウンロードフォルダの…」で 場所 まで消えた
    text = _FOLDER_NOT_TAISHOU.sub(
        lambda m: m.group(0).replace("フォルダ", "　").replace("ふぉるだ", "　"),
        text)
    low   = text.lower()
    slots = {}
    trace = []
    _ex_raw = _except_in(text) or ""
    # 札を見る順は、SEED に書いた順のまま。
    #
    # 「長い札から先に見る」を試した。
    # 「机の上の画像の枚数を教えて」で「教えて」(→一覧)より
    # 「枚数を教えて」(→数える)が勝つはずで、理屈は通っていた。
    # だが実測すると、言い換え25問の正解が 88% → 84% に **下がった**。
    #   「机の上に置いてあるものを教えて」→ 一覧のはずが 数える
    #   「机の上のドキュメントの数を」    → 組み立てられなくなった
    # 理屈が通っていても、測って下がったなら入れない。
    # 場所の札を 先に確定して、その文字を 消しておく。
    #
    # 「書類フォルダ」は 場所の札（Documents）だが、その中には
    # 「書類」（種類）と「フォルダ」（対象）が 埋まっている。
    # 消さないと、一つの言葉が 三つの枠を埋めてしまう。実際こうなっていた:
    #     書類フォルダのファイルの数 → 場所=Documents 種類=書類 対象=フォルダ
    # 長い札から順に消すので、「ダウンロードフォルダ」が「ダウンロード」に
    # 食われることもない。
    # その枠を、どの札が どれくらいの確からしさ で埋めたか
    # （「教えて」で埋めた枠を「枚数を教えて」で上書きしてよいか の判断に使う）
    tsukatta = {}       # 枠 -> 使った札の言葉
    kakudo = {}         # 枠 -> 確からしさ(0〜1)
    if _basho_kari:
        slots["場所"] = _basho_kari
        tsukatta["場所"], kakudo["場所"] = "（先に決めた）", 1.00
    for key, (slot, val) in SEED.items():
        # 「画像以外」の「画像」を、種類として拾ってはいけない
        # 大文字小文字を揃えて見る。
        # 札は「pdf」、文は「PDF以外」だったので この見張りが素通りし、
        # 種類=PDF と 除く=PDF が同時に立って 答えが 0個 になっていた
        if slot == "種類" and key.lower() in _ex_raw.lower():
            continue
        if slot in slots:
            # 埋まっている枠を上書きしてよいのは、
            # 「前の札を丸ごと含んでいて、そのまま入っている」ときだけ。
            #     教えて ⊂ 枚数を教えて  → 後者が勝つ（言っていることが多い）
            # 札を長い順に並べ替えるやり方は前に試して 88%→84% に下がった。
            # 包含だけに限れば、順番をいじらずに 情報の多いほう を採れる。
            mae = tsukatta.get(slot, "")
            mae_kakudo = kakudo.get(slot, 1.0)
            # 上書きしてよいのは 次の二つだけ。
            #  (a) 前の札を丸ごと含んでいる  … 教えて ⊂ 枚数を教えて
            #  (b) そのまま言われている札が、似ているだけの札に当たったとき
            #      「ドキュメントの圧縮はいくつ」で
            #      札「ドキュメント類」が「ドキュメント」に近さで当たり、
            #      種類=書類 で埋まって、そのあと そのまま書いてある
            #      「圧縮」が入れなくなっていた（作った問題で見つかった）。
            #      はっきり言われたほうが、似ているだけより強い。
            fukumu = (mae and mae in key and key != mae and key.lower() in low)
            sonomama = (mae_kakudo < 1.0 and key.lower() in low)
            if not (fukumu or sonomama):
                continue
        if key.lower() in low:                       # そのまま入っていた
            slots[slot] = val
            tsukatta[slot] = key
            kakudo[slot] = 1.00
            trace.append((key, val, 1.00))
            continue
        # 「〜順」の札は、そのまま言われたときだけ採る。
        # 近さで採ると 札「大きい順」が「大きいファ」に当たってしまい、
        # 「大きいファイルを消して」まで 並べ方つき になっていた（実測）。
        if slot == "並べ方":
            continue
        best = 0.0                                   # 入っていない → 近さで探す
        n = len(key)
        for w in range(max(2, n-1), n+3):
            for i in range(0, max(1, len(text)-w+1)):
                best = max(best, sim(key, text[i:i+w]))
        if best >= 0.55:
            slots[slot] = val
            tsukatta[slot] = key
            kakudo[slot] = round(best, 2)
            trace.append((key, val, round(best, 2)))
    # 確からしさは slots に入れない。
    # 入れたら「slots を鍵にして覚える」所が落ちた（実測: unhashable type: dict）。
    # 枠の中身は文字だけ、という約束を壊してはいけない。
    KAKUDO.clear()
    KAKUDO.update(kakudo)
    if verbose:
        for k, v, s in trace:
            mark = "そのまま" if s == 1.0 else f"近さ {s}"
            print(f"      カード「{k}」→ 【{v}】   ({mark})")

    # 「画像以外」は、画像を種類として採ってはいけない。除くものとして扱う
    # 「いちばん大きい」の“いちばん”を、理屈で 並べ方 に変える。
    #
    # ここは長らく 偶然で動いていた。
    # 「一番大きいファイル」が通っていたのは、札「大きい順」が
    # 「大きいファ」に 近さ0.55以上で たまたま当たっていたから。
    # だから「いちばん重いファイル」は 同じ意味なのに通らなかった（実測）。
    # いちばん＝どれか一つ選べ、という合図。大きさ・時期 と組めば 並べ方 が決まる。
    if "並べ方" not in slots and _SAIJOU.search(raw_text):
        ookisa = slots.get("大きさ")
        jiki = _SHINKYU.search(raw_text)
        if ookisa == "大きい":
            slots["並べ方"] = "大きい順"
        elif ookisa == "小さい":
            slots["並べ方"] = "小さい順"
        elif jiki:
            slots["並べ方"] = "古い順" if jiki.group(1) in ("古", "ふる") else "新しい順"

    # 「デスクトップに曲って入ってる？」には 動作 が書かれていない。
    # だが「入ってる？」は あるか無いかを聞いている＝数えれば答えになる。
    # 書かれていないものを聞き返すより、聞かれ方から前向きに導く。
    if "種類" in slots and _ARUKA.search(raw_text):
        # 「入ってる？」の「入って」を もぐる の合図として拾っていた。
        # 奥へもぐれとは言われていない。あるか無いかを聞かれている
        if slots.get("動作") in (None, "もぐる"):
            slots["動作"] = "数える"

    # 「〜の数」「〜の総数」と言われたら、動作は 数える。
    # 札には「数を」「数は」しか無く、「写真の数」で終わる言い方が落ちていた。
    # 助詞の付き方を一つずつ札にするのではなく、言い方の形で受ける。
    if "動作" not in slots and _KAZU.search(raw_text):
        slots["動作"] = "数える"

    # 並べ方 が決まっていて 動作 が言われていないなら、動作は「一覧」。
    # 「いちばん大きいのは？」に 動作 は書かれていない。
    # 書かれていないものを 聞き返すのではなく、決まっている条件から前向きに導く。
    if "並べ方" in slots and slots.get("動作") in (None, "大きさ"):
        # 「いちばん容量食ってるファイルは」で
        # 札「容量食」から 動作=大きさ（合計の大きさ）が入り、
        # 「7個で合計89.5MB」と答えていた。聞かれているのは どれか、である。
        # 並べ方が決まっているなら、答えるのは 並べた中身
        slots["動作"] = "一覧"

    # 数を聞かれている文で、ものを動かしてはいけない。
    #
    # 「奥のフォルダまで入れて ファイルは何個」で
    # 「入れて」が 移動 の合図として拾われ、
    # **聞かれただけなのに 種類ごとの仕分けが本当に走っていた**
    # （画像/音楽/PDF フォルダが作られ、ファイルが移された）。
    # 数を尋ねる文は、最後まで 尋ねる文である。
    if slots.get("動作") in KOWASU_ACTS and _KAZU_TOI.search(raw_text):
        slots["動作"] = "数える"

    # 文の終わりが「見せて」「教えて」なら、それは 見せてほしい という頼み。
    # 途中に「整理」「捨てる」が出てきても、最後に言われたことが 本題。
    #
    # 実際に起きた（壊す側が見つけた）:
    #     「デスクトップの整理をしたいので、まず何があるか見せて」
    #      → 本当に 種類ごとの仕分けが走って ファイルが動いた
    # 「〜したいので、まず見せて」は 相談であって 指示ではない。
    if slots.get("動作") in KOWASU_ACTS and _MIRU_TOI.search(raw_text):
        slots["動作"] = "一覧"

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
    # 札に載っている語（＝すでに意味が決まっている語）を、
    # ファイル名の絞り込みに使ってはいけない。
    # 「デスクトップの一覧をHTMLで作って」の「一覧」がヲ格で拾われ、
    # 名前に入って「一覧という字を含むファイル」を探しに行き、0件で落ちていた。
    # 場所の言い方の 一部を、ファイル名として使ってはいけない。
    # 「落としたところを…」で、札は「落とした」までなので「ところ」が残り、
    # ヲ格から 名前='ころ' が拾われ、その字を含むファイルを探して 0件になっていた。
    _basho_kotoba = ""
    if _basho_kari is not None:
        for k, (sl, v) in SEED.items():
            if sl == "場所" and v == _basho_kari and k.lower() in raw_text.lower():
                for shippo in ("のところ", "ところ", "のとこ", "とこ", "の中", ""):
                    if (k + shippo).lower() in raw_text.lower():
                        _basho_kotoba = k + shippo
                        break
                break
    if tgt and _basho_kotoba and tgt in _basho_kotoba:
        if verbose:
            print(f"      「{tgt}」は場所の言い方の一部なので、"
                  f"ファイル名としては使いません")
        tgt = None
    if tgt and (tgt in SEED or tgt.lower() in _LOWER_SEED
                or tgt in _TOO_GENERIC):
        if verbose:
            print(f"      「{tgt}」は札に載っている語なので、"
                  f"ファイル名としては使いません")
        tgt = None
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

    # 実在するフォルダの名前が出ていたら、その置き場所も分かる。
    #
    # 「整理済みには何がある？」で「場所が分かりません」と言っていた。
    # だが 整理済み_2026-06-17 はデスクトップに在ると、こちらは知っている。
    # 名前が分かって場所が分からない、というのは、聞き返す理由にならない。
    if "場所" not in slots and "パス" not in slots:
        for _nm, _basho, _full in _jitsuzai_folders():
            if _nm and _nm in raw_text:
                slots["場所"] = _basho
                slots.setdefault("名前", _nm)
                if verbose:
                    print(f"      「{_nm}」は {_basho} に在るフォルダです")
                break

    # 「奥まで見て」と言われたか。
    #
    # 札には「サブフォルダ」→動作:もぐる のような語が入っているが、
    # 「サブフォルダも中まで全部数えて」では 動作 が先に「数える」で
    # 埋まってしまい、奥まで見ろという指示が消えていた。
    # 動作とは別の札にして、両方を残す。
    if _FUKAKU.search(raw_text):
        slots["深く"] = "はい"
        if verbose:
            print("      奥（サブフォルダの中）まで見ます")

    # 「これから付ける名前」は、探す相手の名前とは別ものとして持つ
    shinmei = _shinmei_in(raw_text)
    if shinmei:
        slots["新名"] = shinmei
        slots.setdefault("動作", "改名")
        _names = [n for n in _names if n != shinmei]
        if slots.get("名前") == shinmei:
            slots.pop("名前", None)
        # 「旅行という名前にして」を、行き先フォルダ「旅行」とも読んでいた。
        # 同じ語が両方に入ると「フォルダも作れ、名前も変えろ」になって
        # どちらの案も通らなくなる。名前の話だと分かっているので行き先は捨てる
        if slots.get("行き先") == shinmei:
            slots.pop("行き先", None)
        if verbose:
            print(f"      新しく付ける名前として受け取った： 「{shinmei}」")

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
                if slot == "時期":
                    # 時期も同じ。言われていない「去年」が勝手に付くと、
                    # 件数が静かに変わる。しかも画面には出ない。
                    #
                    # 実測: 「机の上の画像の枚数を教えて」で
                    #   {種類:画像, 名前:枚数, 時期:先月} になり、
                    #   先月のものだけに絞られて「何もありません」と答えていた。
                    #   「枚数」という語から「先月」が湧いている。
                    #
                    # 下のしきい値は 0.03。これはほぼ でたらめ と同じ。
                    # 前にも「一覧」が近さ 0.104 で【今月】にされた事故がある。
                    # 時期は、はっきり言われた時だけ受け取る
                    continue
                cands = vt.get(slot)
                if not cands:
                    continue
                # ── まず「パソコンの話」の材料で見極める ──────────
                # 抜いてきた表（辞書が材料）は当たらない。実測 4/17（24%）で、
                # 近さも 0.51 と、でたらめと変わらなかった。
                # 材料をパソコンの話の記事に替えたら 11/17（65%）、
                # 材料に載っている語だけなら 11/12（92%）になった。
                # 当たるほうを先に試す。
                if slot == "種類":
                    try:
                        import pc_kind
                        for w in _words_in(text):
                            if w in _TOO_GENERIC:
                                continue
                            # 「絵以外」のように 除く と言われている語を、
                            # そのまま 種類 として見立ててはいけない。
                            # 「絵以外は何個」で 種類=書類 と見立てられ、
                            # 書類だけを数えていた（作った問題で見つかった）
                            if _ex_raw and (w in _ex_raw or _ex_raw in w):
                                continue
                            if "以外" in w or "のぞく" in w or "除く" in w:
                                continue
                            # 名前として受け取った語を、種類として見立て直さない。
                            # 「カードゲームを作って」で「カード」を見立てて
                            # 種類=書類 が立ち、作りもしないのに
                            # 書類で絞り込む案を 300通り探していた
                            _na = slots.get("名前") or ""
                            if _na and (w in _na or _na in w):
                                continue
                            wl = w.lower()
                            if any(k.lower() in wl or wl in k.lower()
                                   for k in used):
                                continue
                            k2, n2, m2 = pc_kind.guess(w)
                            if k2:
                                slots[slot] = k2
                                used.add(w)
                                if verbose:
                                    print(f"      パソコンの話で見極め「{w}」"
                                          f"→ 【{k2}】   (近さ {n2:.3f} 差 {m2:+.3f})")
                                break
                        if slot in slots:
                            continue
                        if pc_kind.ready():
                            # 見極めが「分からない」と言ったのに、
                            # 後ろの表引きに回すと、そちらが答えてしまう。
                            # 実際に「デスクトップのみそ汁を数えて」で
                            # みそ汁が【書類】にされた。
                            # 24%しか当たらない係に、黙った後を任せない。
                            # 分からないものは、分からないままにしておく
                            continue
                    except Exception:
                        pass
                # ────────────────────────────────────────────────
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

    # ── 最後の関所: 形式の名前を、行き先にしない ──────────────
    # 「写真をPDFにまとめて」で 行き先=PDF となり、
    # PDF という名のフォルダを作って 画像5枚を そこへ移していた。
    # 頼まれたのは 形を変えること。移すことではない。
    # 入口が何通りもあるので、出口で一度だけ塞ぐ。
    #
    # これは、棚に無いことを「できません」と言えず、
    # 代わりに 似た別のことを 堂々とやってしまう、という
    # いちばん危ない形の失敗だった。
    yuki = slots.get("行き先")
    if yuki and str(yuki).strip("　 ").upper() in _KATACHI:
        _tsumazuki(text, dict(slots),
                   f"「{yuki}」は ファイルの形の名前。形を変える部品が無い",
                   "札引き")
        slots.pop("行き先", None)
        if slots.get("動作") == "移動":
            slots.pop("動作", None)      # 移動ではない。勝手に移させない
        if verbose:
            print(f"      「{yuki}」は形の名前です。"
                  f"形を変える部品が無いので、移動にはしません")
    return slots


@functools.lru_cache(maxsize=1)
def _unified():
    from cards_unified import UnifiedCards
    return UnifiedCards()


# 助詞・記号で切る。またぐ断片（「去年のスナッ」等）を作らせない
_SEP = _re.compile(r"[のをにへとがはでや、。，．,.\s　！？!?（）()「」\[\]"
                   r"だけとか　]+")

# 総称語。何にでも薄く似てしまうので、種類や場所の判定に使わない
@functools.lru_cache(maxsize=1)
def _lower_seed():
    return {k.lower() for k in SEED}


class _LowerSeed:
    """SEED は後から増えるので、そのつど作り直せるようにしておく"""
    def __contains__(self, w):
        return w in {k.lower() for k in SEED}


_LOWER_SEED = _LowerSeed()

_TOO_GENERIC = {
    "ファイル", "ふぁいる", "もの", "やつ", "データ", "中身", "なかみ",
    "全部", "ぜんぶ", "いろいろ", "何か", "なにか", "こと", "とこ", "ところ",
    "フォルダ", "ふぉるだ", "ディレクトリ", "アイテム", "中の", "たち",
    # 人称・指示語。表では何にでも薄く似てしまう
    "あなた", "あんた", "きみ", "おまえ", "自分", "わたし", "わたく",
    "これ", "それ", "あれ", "どれ", "ここ", "そこ", "あそこ", "どこ",
    "今の", "さっき", "本当", "ほんと", "普通", "感じ", "とき", "ため",
    # 「〜の名前を旅行に変えて」で、この「名前」そのものが
    # ファイル名の絞り込みに入り、肝心の「旅行」が捨てられていた
    "名前", "なまえ", "ファイル名", "題名", "タイトル",
    # 数をたずねる言葉。ファイル名ではない。
    # 「画像の枚数を教えて」の「枚数」が名前スロットに入っていた
    "枚数", "個数", "件数", "総数", "数", "かず", "いくつ", "何個", "何枚",
}


# 「〜の名前を 旅行 に変えて」「〜を 旅行 という名前にして」の「旅行」。
# これは “探す相手の名前” ではなく “これから付ける新しい名前”。
# 別のスロットにしないと、しぼる(名前) が「旅行という字を含むファイル」を
# 探しに行って 0 件になり、そのうえ改名の元になる語が消えていた。
_SHINMEI = [
    # 名前を X に変えて／X にして／X へ変更
    _re.compile(r"(?:名前|なまえ|ファイル名|題名|タイトル)\s*(?:を|は)\s*"
                r"[「『\"']?([^\s　「」『』\"'、。]{1,30}?)[」』\"']?\s*"
                r"(?:という|といった)?\s*(?:に|へ)\s*"
                r"(?:変え|かえ|変更|直し|なおし|し(?:て|と|ろ|たい)|付け|つけ)"),
    # X という名前に(して)／X の名前に
    _re.compile(r"[「『\"']?([^\s　「」『』\"'、。をはがのにへ]{1,30}?)[」』\"']?\s*"
                r"(?:という|といった)\s*(?:名前|なまえ|ファイル名)\s*(?:に|へ)"),
]


# 「奥まで／サブフォルダも／中まで」＝ その場所だけでなく、下も全部見る
# 見せてほしい と言って終わっている文
_MIRU_TOI = _re.compile(
    r"(見せて|みせて|教えて|おしえて|出して|だして|見たい|みたい|"
    r"知りたい|しりたい|確認したい|一覧に(して|)|並べて)"
    r"\s*[。？?！!]?\s*$")

# 数を尋ねている文の 終わり方
_KAZU_TOI = _re.compile(r"(何個|何枚|何件|何本|いくつ|個数|枚数|件数|総数|"
                        r"どれだけ|何メガ|何ギガ)\s*[。？?]?\s*$")

# 「〜の数」「総数」＝ 数えろ、という合図
_KAZU = _re.compile(r"(の数|総数|の件数|の個数|の枚数|の本数|数は|数を)\s*[。？?]?\s*$"
                    r"|(の数|総数)(を|は|が)")

# 数える相手ではない「フォルダ」の出かた
_FOLDER_NOT_TAISHOU = _re.compile(
    # 「書類フォルダ」は それ自体が 場所の札（Documents）。ここに入れてはいけない。
    # 入れていたので「書類フォルダのファイルの数」で 場所が消え、
    # 種類=書類 だけが残っていた（作った問題で見つかった）
    r"(デスクトップ|ダウンロード|ドキュメント|desktop|downloads|documents"
    r"|奥の|中の|その)\s*(フォルダ|ふぉるだ)"
    r"|(フォルダ|ふぉるだ)\s*(に|へ|の中|まで)",
    _re.I)

# 「ある？」「入ってる？」＝ あるか無いかを聞いている。数えれば答えになる
_ARUKA = _re.compile(r"(ある[？?]|ある\s*$|あります|入って(る|いる|ます)|"
                     r"置いてある|残って(る|いる)|存在)")

# 場所らしい言い方。知らないものを名指しされたら 断るために使う
_BASHO_RASHII = _re.compile(
    r"([^\s、。「」]{1,12}?)"
    r"(ディスク|ドライブ|ライブラリ|ボリューム|サーバー|サーバ|"
    r"フォルダー|フォルダ|ふぉるだ|ディレクトリ)")


def _basho_rashii_shiranai(text, slots):
    """場所らしく名指しされているが、知らない場所ならその言葉を返す"""
    if slots.get("場所") or slots.get("パス"):
        return None                     # 場所は分かっている
    for m in _BASHO_RASHII.finditer(text or ""):
        kotoba = m.group(0)
        # 札に載っている場所の言い方なら、知っている
        if any(k.lower() in kotoba.lower() for k, (sl, v) in SEED.items()
               if sl == "場所"):
            continue
        # 「フォルダに入れて」のような 行き先の言い方は 場所の名指しではない
        ato = text[m.end():m.end() + 2]
        if ato.startswith(("に", "へ", "まで")):
            continue
        return kotoba
    return None


# 「ゴミ箱を空にして」＝ 取り返しのつかない消し方。引き受けない
_GOMI_KARA = _re.compile(
    r"(ゴミ箱|ごみ箱|ごみばこ|トラッシュ)\s*(を|の中身を|の)?\s*"
    r"(空|から|きれいに|綺麗に|片付|かたづ|掃除|そうじ|消|け|削除|クリア)")

# 「いちばん」＝ 並べて先頭を取れ、という合図
_SAIJOU = _re.compile(r"(一番|いちばん|1番|最も|もっとも|最大|最小|"
                      r"最新|最古|トップ|先頭)")
# 古い／新しい の言い方（最上級と組ませて 並べ方 を決める）
_SHINKYU = _re.compile(r"(古|ふる|新し|あたらし|最新|最古)")

_FUKAKU = _re.compile(r"(奥の\s*(フォルダ|ふぉるだ)|"
                      r"サブ\s*フォルダ|さぶふぉるだ|奥まで|おくまで|"
                      r"中まで|なかまで|もぐって|潜って|再帰|"
                      r"下の(フォルダ|ほう)|以下(の|も)|全部の?フォルダ)")


def _shinmei_in(text):
    """これから付ける新しい名前。無ければ None"""
    for rx in _SHINMEI:
        m = rx.search(text)
        if m:
            w = m.group(1).strip("　 「」『』\"'")
            # 「名前を名前に」のような、意味の無い取り方を弾く
            if w and w not in _TOO_GENERIC and not _re.fullmatch(r"[をはがのにへ]+", w):
                return w
    return None


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
    # ── 一文字予想を繋いでみたが、外した（記録として残す）──────
    # mojiyosou.kugiri() で切った かたまり を候補に足してみた。
    # 結果は A/B で ぴったり同じ。上の「語尾を削る」だけで
    # 同じ範囲をすでに拾えていた。得は無く、30% 遅くなるだけ。
    #   前: デスクトップ画像かぞえて → {場所:Desktop, 種類:画像}
    #   後: デスクトップ画像かぞえて → {場所:Desktop, 種類:画像}
    # 効くようになるのは、材料が いまの 10倍（600万字）を超えて
    # 「デスクトップ」が一語として立つようになってから。
    # 文字予想そのものは mojiyosou.py で動いている（次の字 33%）。

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
    # すでに「ここを掘る」と決まっているなら、それに従う。
    # 名前は使い切って消えているので、ここが唯一の手がかりになる
    hori = slots.get("掘り先")
    if hori and os.path.isdir(hori):
        return hori
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
    fs, ds = [], []
    for f in os.listdir(d):
        if f.startswith("."):
            continue
        p = os.path.join(d, f)
        if os.path.isfile(p):
            fs.append(p)
        elif os.path.isdir(p):
            ds.append(p)
    # フォルダも控えておく。
    #
    # ここは長いあいだ isfile だけを見ていた。
    # そのため「デスクトップには何がある？」と聞かれて、
    # 実際には PDF / 画像 / 整理済み_2026-06-17 の3つが在るのに
    # 「何もありません」と答えていた（実物で再現）。
    # 中身がフォルダだけの場所では、いつもこうなる。
    #
    # ただし ものを動かす部品には渡さない。files のままにしておく。
    # フォルダごと動かす・捨てるのは、頼まれていないのにやると
    # 取り返しがつかない。
    # 見せる・数える部品だけが、この dirs を見る。
    #
    # もともと何件あったかを控える。
    # 「0件だったのは手順が悪いからか、本当に何も無いからか」を
    # 見分けるのに要る。ここが無かったせいで、空のフォルダに
    # 対して 90回さまよっていた（下の goal_reached を参照）
    return {**st, "files": fs, "dirs": ds, "src": d,
            "もと": len(fs) + len(ds)}

# 絞り込んだら、フォルダは落とす。
#
# 「デスクトップの画像を数えて」で、絞り込みはファイルにしか掛からないのに
# フォルダが残っていると、画像でないものまで数に入る。
# 絞り込みを言われた時点で、相手はファイルだと決まる。
def _dirs_nashi(st):
    return {k: v for k, v in st.items() if k != "dirs"}


def p_filter_kind(st, slots):
    """しぼる(種類) : 写真だけ、PDFだけ、に絞る"""
    exts = EXT[slots["種類"]]
    fs = [f for f in st["files"] if os.path.splitext(f)[1].lower() in exts]
    return {**_dirs_nashi(st), "files": fs}

def p_filter_time(st, slots):
    """しぼる(時期) : 去年のだけ、今月のだけ、に絞る"""
    a, b = _period_range(slots["時期"])
    fs = [f for f in st["files"] if a <= os.path.getmtime(f) < b]
    return {**_dirs_nashi(st), "files": fs}

def p_count(st, slots):
    """かぞえる : 数を出す"""
    ds = st.get("dirs") or []
    # 「ファイルは何個」と言われたら、フォルダは数に入れない。
    # 対象 を見ていなかったので「ファイルって何個ある」に
    # 「8個（ファイル7・フォルダ1）」と答えていた
    if (slots or {}).get("対象") == "ファイル":
        ds = []
    n = len(st["files"]) + len(ds)
    if ds and st["files"]:
        return {**st, "answer": f"{n} 個"
                      f"（ファイル {len(st['files'])}・フォルダ {len(ds)}）"}
    if ds:
        return {**st, "answer": f"{n} 個（すべてフォルダ）"}
    return {**st, "answer": f"{n} 個"}

def p_list(st, slots):
    """ならべる : 一覧を出す

    もう並べ替えてあるなら、その順のまま出す。
    ここで名前順に並べ直していたので、
    「いちばん大きいファイルは」で 大きい順に並べたあと
    名前順に戻してしまい、先頭が いちばん大きいものでなくなっていた。
    """
    if st.get("並んだ"):
        names = [os.path.basename(f) for f in st["files"]]
        if not names:
            return {**st, "answer": "何もありません"}
        return {**st, "answer": "\n".join("  - " + n for n in names)}
    # フォルダも並べる。ここを見ていなかったので、
    # 中身がフォルダだけのデスクトップに対して
    # 「何もありません」と答えていた
    names = sorted(os.path.basename(d) + "/" for d in (st.get("dirs") or []))
    names += sorted(os.path.basename(f) for f in st["files"])
    if not names:
        return {**st, "answer": "何もありません"}
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
    # ★ フォルダ名として使ってよい形に整える（parts_more と同じ関所）。
    #   ここも生のまま使っていたので、読み取りがくずれると
    #   **「というフォルダ」という名前のフォルダに 写真がまとめられた**。
    #   「机の上の写真を 旅行 というフォルダにまとめて」で実際に起きる形だった。
    try:
        from parts_more import _namae_wo_totonoeru as _seiketsu
        name = _seiketsu(name) or "まとめ"
    except Exception:
        pass
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

# もとから知っている札の写し。
# 教わった札が これと食い違っていないか を見るのに使う（_ayashii）
_SEED0 = dict(SEED)

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
    if "新名" in slots and "なまえかえ" not in path: return False
    if "深く" in slots and "もぐる" not in path: return False
    if "行き先" in slots and "つくる" not in path: return False
    if "種類" in slots and "しぼる(種類)" not in path: return False
    # 「フォルダはいくつ」と言われて ファイルを数えた案は、答えではない。
    #
    # ただし 対象=ファイル のときは何も要求しない。
    # 対象 は札だけでなく文法からも入る（「写真を」のヲ格など）ので、
    # ファイルまで要求したら「Desktopの写真の数は」まで通らなくなった（実測 25→21）。
    # ファイルは元から既定。わざわざ絞る必要がない。
    # 「フォルダを作って」でも 対象=フォルダ が立つ。
    # そこで しぼる(対象) を要求すると、作る案が ぜんぶ落ちる。
    # 絞るのは 数える・並べるときの話。作るときの話ではない
    if (slots.get("対象") == "フォルダ" and slots.get("動作") in READ_ACTS
            and "しぼる(対象)" not in path):
        return False
    if "時期" in slots and "しぼる(時期)" not in path: return False
    # 「一番大きい」「一番古い」と言われたのに、並べていない案は答えではない。
    #
    # ここは長いあいだ抜けていた。並べない案も「答えはある」ので通っていて、
    # たまたま並べる案を先に引いていたから当たっていただけだった。
    # 何人かで探させたら、並べない短い案が選ばれて初めて表に出た。
    # 並べ替えは 一度だけ。二つ入ると あとの向きが 前を打ち消す。
    # 実際に「さがす → おおきいじゅん → ちいさいじゅん → ならべる」を
    # 覚えていて、大きい順と言われて 小さい順に並んでいた。
    # 「おおきいじゅんが入っているから合格」で通していたのが穴だった
    if len(SORT_PARTS & set(path)) > 1:
        return False
    if "並べ方" in slots:
        iru = NARABE_PART.get(slots["並べ方"])
        # 言われた向きに並べていなければ答えではない。
        # 「どれか並べていれば通す」にしていたので、大きい順と言われて
        # 古い順に並べた案が通っていた
        if iru and iru not in path:
            return False
        if not iru and not (SORT_PARTS & set(path)):
            return False

    act = slots.get("動作")

    # 読むだけの頼みに、ものを作る・動かす部品が混ざっていてはいけない。
    #
    # 実際に起きていた: 「いちばん大きいファイルは」で
    #   さがす → つくる → おおきいじゅん → ならべる
    # という手順が ノートに焼き付いていて、
    # 聞かれただけなのに 毎回「まとめ」フォルダが作られていた。
    # 答えは合っているので、誰も気づかない形の事故だった
    # （作った問題 500問のうち 198問で 場が変わっていた）。
    if act in READ_ACTS and any(p in DESTRUCTIVE for p in path):
        return False

    if act == "作成":
        if st.get("created") is None:
            return False
        # 頼まれたものと 別のものを作ってはいけない。
        # 「メモというフォルダを作って」で HTMLをつくる が答えになり、
        # メモ.html ができていた。作れないと言うほうが まだよい
        if slots.get("対象") == "フォルダ":
            # 「つくる」が入っていれば通す、にしていたら
            # 「さがす → つくる → HTMLをつくる」が合格して
            # ノート.html ができていた。最後に作られたものが何かで判じる
            if any(p in path for p in ("HTMLをつくる", "ファイルをつくる")):
                return False
            return any(p in path for p in ("フォルダをつくる", "つくる"))
        if slots.get("対象") == "ファイル":
            return "ファイルをつくる" in path
        return True

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
    # フォルダしか無い場所を「1個も見つからない」と言っていた。
    # 中身がフォルダだけのデスクトップに対して さがす が空振り扱いになり、
    # 探索が もぐる（サブフォルダの中身まで）へ逃げて、
    # 「デスクトップには何がある？」に 46個 のファイル名を並べていた。
    # 聞かれたのは、その場所に何が在るか
    aru = bool(st["files"]) or bool(st.get("dirs"))
    if name == "さがす" and not aru:
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


def _kezuru(plan, slots, st, verbose=False):
    """答えが変わらない部品を、手順から落とす

    落としてよい条件は 三つ全部:
      ① 抜いても 同じ答えになる
      ② 抜いても goal_reached が通る（言われた条件を使い切っている）
      ③ 抜いても 落ちない
    一つでも欠けたら その部品は要る。安全側に倒す。
    """
    if len(plan) <= 2:
        return plan
    moto = _mijikaku(st.get("answer"))
    ima = list(plan)
    for nuku in list(plan):
        if nuku in ("さがす", "じかに") or len(ima) <= 2:
            continue
        kouho = [p for p in ima if p != nuku]
        try:
            st2 = run_plan(kouho, slots)
        except Exception:
            continue                       # 落ちるなら 要る
        if _mijikaku(st2.get("answer")) != moto:
            continue                       # 答えが変わるなら 要る
        if not goal_reached(st2, slots, kouho):
            continue                       # 条件を使い切れないなら 要る
        ima = kouho
        if verbose:
            print(f"    （「{nuku}」は答えに効いていないので、覚えるときに落とします）")
    return ima


# 二通りで確かめるのを止めるための札（測るときに使う）
FUTAMICHI_YAMERU = False


def _mijikaku(a):
    t = " ".join((a or "").split())
    return t[:60] + ("…" if len(t) > 60 else "")


def _futatsume(plan, slots, allow, budget):
    """一つ目と違う道すじを探して、答えが違えば返す。同じなら None

    違う道すじの作り方は「一つ目で使った部品のどれかを 使わない」。
    使える部品を減らして 解き直す。それで別の答えが出るなら、
    どちらかが 条件を取りこぼしている
    """
    try:
        for nuku in plan:
            if nuku in ("さがす", "じかに"):
                continue                      # これを抜くと そもそも始まらない
            tsukaeru = (set(allow) if allow else set(PARTS)) - {nuku}
            p2, st2 = solve(slots, verbose=False, allow=tsukaeru, budget=budget)
            if p2 is None:
                continue
            a1 = _mijikaku(_st_answer(plan, slots))
            a2 = _mijikaku(st2.get("answer"))
            if a1 and a2 and a1 != a2:
                return p2, st2
        return None
    except Exception:
        return None                            # 確かめられないなら 黙って通す


_ST_CACHE = {}


def _st_answer(plan, slots):
    st = run_plan(plan, slots)
    return st.get("answer")


def solve(slots, verbose=True, allow=None,
          bias=None, budget=None, max_depth=6, collect=1, strategy="幅"):
    """見込みの高い手から試す。実績が無ければ、これまで通り幅優先

    allow を渡すと、その部品だけを使う（読み取り専用にする時に使う）

    ここから下の4つは「長く考える」ための取っ手。
    掛け算を増やすのではなく、考える時間を増やして賢くするための入口。

      bias      … 部品を並べ直す係。視点を変えて探すのに使う
      budget    … 何通りまで試すか（既定 300）
      max_depth … 手順を何手まで伸ばすか（既定 6）
      strategy  … 探し方。"幅" は横に広く（今まで通り）、
                  "深" は一本の道を先まで掘る。
                  順番を変えるだけでは、見る場所が同じで意味がなかった。
                  実測でそれが出たので、探し方そのものを変えられるようにした。
      collect   … 見つけた案を何個ためるか。
                  1 なら今まで通り「最初に見つかった案」で打ち切る。
                  2以上にすると、打ち切らずに探し続けて案を集める。
                  戻り値は [(手順, 結果), …] のならびになる
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
    MAX_TRY, MAX_SHOW = (budget or 300), 60
    found = []             # collect>=2 のとき、ここに案をためる
    # 0件で終わる案は「答えではある」が弱い。もっと良い案が無い時だけ使う
    fallback = None
    while queue:
        if tried >= MAX_TRY:
            if verbose:
                print(f"    → {MAX_TRY} 通り試して見つからないので、ここで打ち切ります")
            break
        if pol:            # 見込みの高い枝から取り出す（最良優先）
            queue.sort(key=lambda q: -pol.rank(slots, q[1]))
        st, path = queue.pop(0) if strategy == "幅" else queue.pop()
        if len(path) >= max_depth:
            continue
        names = [n for n in PARTS if allow is None or n in allow]
        if pol:
            names = pol.order(names, slots, path)
        if bias:
            names = bias(names, slots, path)
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
                        # 0件の答えは、ふつうは保留する。
                        # しぼり方が悪くて0件になっただけかもしれないので、
                        # もっと良い案がないか探し続ける。
                        #
                        # ただし「もと」が 0 件、つまりフォルダ自体が空なら、
                        # どう探しても 0 件にしかならない。探すだけ無駄。
                        # ここで打ち切る（実測 1,220ミリ秒 → 数ミリ秒）
                        if nst.get("もと") == 0:   # 未記録(None)ではなく、本当に0件
                            _show(f"{indent}  ★ そもそも中身が空。探しても増えない")
                            if pol: pol.win(slots, npath)
                            return (npath, nst) if collect <= 1 else None
                        if fallback is None:
                            fallback = (npath, nst)
                            _show(f"{indent}  → 0件。保留して探索を続ける")
                        continue
                    if verbose: print(f"{indent}★ できた（{tried}回ためした）")
                    if pol: pol.win(slots, npath)
                    if collect <= 1:
                        return npath, nst
                    if npath not in [p for p, _ in found]:
                        found.append((npath, nst))
                    if len(found) >= collect:
                        return found
                    continue
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
                if collect <= 1:
                    return npath, nst
                if npath not in [p for p, _ in found]:
                    found.append((npath, nst))
                if len(found) >= collect:
                    return found
            queue.append((nst, npath))
    if collect > 1:
        if not found and fallback:
            found.append(fallback)
        return found
    if fallback:
        if verbose: print(f"  ★ 0件の答えを採用（{tried}回ためした）")
        if pol: pol.win(slots, fallback[0])
        return fallback
    return None, None

# 並べる部品。「一番◯◯」と言われたら、このどれかが要る
# 並べ方 と 部品 の対応。
# ここが無かったころは goal_reached が「どれか並べていれば通る」判定で、
# 「大きい順」と言われて 古い順 に並べた案も 答えとして通ってしまっていた。
NARABE_PART = {
    "古い順":   "ふるいじゅん",
    "大きい順": "おおきいじゅん",
    "新しい順": "あたらしいじゅん",
    "小さい順": "ちいさいじゅん",
}
SORT_PARTS = set(NARABE_PART.values())

# 読むだけで済む動作。聞かれているときも、そのまま活かしてよい
READ_ACTS = {"数える", "一覧", "重複", "大きさ", "もぐる"}

# ものを動かす・作る部品。ここに書き忘れると、
# 仮想も 関所も 読むだけモードも ぜんぶ素通りする。
#
# 「つくる」（行き先フォルダを作る部品）が 抜けていた。
# 部品の名前は「つくる」なのに、ここには「フォルダをつくる」と書いてあり、
# 名前が違うので 一度も引っかかっていなかった。
# そのため「いちばん大きいファイルは」と聞くだけで
# 「まとめ」フォルダが毎回できていた（作った問題500問中198問で場が変わった）。
DESTRUCTIVE = {"うつす", "しわけ", "なまえかえ", "ごみばこ", "HTMLをつくる",
               "つくる", "ファイルをつくる", "フォルダをつくる"}

# 部品の名前と食い違っていないか、ここで確かめる。
# 同じ書き忘れを 二度としないため
def _destructive_no_kakunin():
    return sorted(DESTRUCTIVE - set(PARTS))

def preview_plan(plan, slots):
    """本番の前に、下見でどうなるか見ておく"""
    st = {"files": None, "dry": True}
    for name in plan:
        st = PARTS[name]["fn"](st, slots)
    return st


# 実行の前に、いちいち人にたずねるか。
# 既定は「たずねない」。
# 下見（仮想）を必ず先に通し、そこで問題が出なければ、そのまま実行する。
# 毎回 y/N を押させるのは、正しいと分かっている手順にまで足を止めさせるだけ。
# ただし関所が「危険」と言った手順は、この設定に関係なく実行しない。
ASK_BEFORE = False

# 「読むだけ」。true なら、命令であっても、ものを動かす部品を一切使わない。
# 見せてもらうだけにしたい時のための、いちばん強い安全弁
READ_ONLY = False


def _preview_lines(pv, plan=None, slots=None, limit=12):
    """下見の結果を、人が読める形にする。

    ひな形の文を出すのではなく、本物のフォルダの姿をメモリに写して、
    その中で手順を動かし、前と後ろを突き合わせて出す（virtual.py）。
    ファイルの中身は読まないし、コピーも作成もしない。
    """
    try:
        import virtual
        sim = virtual.simulate(pv, plan or [], slots or {})
        return virtual.report(sim, limit), sim
    except Exception as e:
        # ここは前は「仮想が使えなくても止めない」だった。
        # だが仮想が落ちると sim が None になり、
        # 上書きの見張りが黙って無効になったまま
        # 「仮想で問題なし」と表示して本番を実行していた（実測で再現）。
        #
        # 検査できなかったことは「安全」ではない。「分からない」だ。
        # 分からないまま、ものは動かさない。
        out = []
        for a, b in (pv.get("pairs") or [])[:limit]:
            out.append(f"{os.path.basename(a)}  →  {b}")
        if not out:
            out.append(f"対象 {len(pv.get('files') or [])} 件")
        out.append(f"✗ 仮想で動かせませんでした（{e}）")
        return out, {"止める理由": [f"仮想が使えないので、確かめられません（{e}）"]}


def run_plan(plan, slots, guarded=None):
    """手順を実行する。

    ものを動かす手順は、必ず先に「下見」を通す。
    下見はファイルに一切触らず、何が起きるかだけを計算する。
    そこで関所が通れば、そのまま本番を1回だけ実行する。
    """
    if guarded is None:
        guarded = (ROOT == "real")
    if any(p in DESTRUCTIVE for p in plan):
        # ── ⓪ 自信があるか ──────────────────────────────────
        # ものを動かす前に「その動作は はっきり言われたか」を見る。
        #
        # 「この動画をMP3にして」で動画がゴミ箱へ入った事故は、
        # 札「消して」が「して」に 近さ0.5 で当たったのが始まりだった。
        # 近さで拾った動作は、当たっていることもあるが、外すと戻せない。
        # 読むだけなら 近さで拾ってよい。壊すなら はっきり言われたときだけ。
        # 見るのは 動作 だけでは足りない。
        # どこの何を壊すのかを決めている枠が あやふやなら、同じくらい危ない。
        # 場所を似ているだけで決めて、別のフォルダを空にしたら 取り返せない。
        yowai, waku = None, None
        for k in ("動作", "場所", "種類", "名前", "時期", "行き先"):
            v = KAKUDO.get(k)
            if v is not None and v < 1.0 and (yowai is None or v < yowai):
                yowai, waku = v, k
        if yowai is not None:
            print(f"\n  ✗ 「{slots.get(waku)}」（{waku}）と受け取りましたが、"
                  f"言われた言葉そのものではなく 似ているだけです"
                  f"（確からしさ {int(yowai * 100)}%）。")
            print("     ものを動かすのは、はっきり言われたときだけにします。")
            print("     そのつもりなら、言い方を変えてもう一度言ってください。")
            return {"answer": "自信がないので、やめておきます", "止めた": True}

        # ── ① 仮想 ──────────────────────────────────────────
        # 本番でも練習でも、必ず先に頭の中で動かす。
        # 本物のフォルダの「名前と大きさ」だけをメモリに写して、
        # そこで手順を動かし、前と後ろを突き合わせる。
        # 中身は読まない。コピーもしない。作りもしない。
        pv = preview_plan(plan, slots)
        lines, sim = _preview_lines(pv, plan, slots)
        print("\n  ── 仮想で動かしてみます（ファイルは1つも触っていません）──")
        for line in lines:
            print(f"     {line}")
        # 名前がぶつかるなら、ここで止める。
        # shutil.move は黙って上書きするので、これは本物の事故になる
        if sim and sim.get("止める理由"):
            for r in sim["止める理由"]:
                print(f"     ✗ {r}")
            raise PermissionError("仮想で止めました: "
                                  + "; ".join(sim["止める理由"]))
        # ── ② 関所（本物のフォルダのときだけ）────────────────
        if guarded:
            g = _guard()
            v = g.check_plan(plan, slots, pv)
            print(f"  ── 関所 ── {v['level']}： {v['summary']}")
            for r in v.get("reasons", []):
                print(f"     ・{r}")
            if not v["ok"] or v["level"] == "危険":
                raise PermissionError("関所が止めました: "
                                      + "; ".join(v.get("reasons", [])
                                                  or ["危険と判定されました"]))
            if ASK_BEFORE and v["level"] != "安全" and not g.confirm(v):
                raise PermissionError("実行しませんでした")
        # ── ③ 本番 ──────────────────────────────────────────
        print("  → 仮想で問題なし。このまま本番を1回だけ実行します")
    st = {"files": None, "dry": False}
    for name in plan:
        st = PARTS[name]["fn"](st, slots)

    # 実行「後」に、実際に動いた分だけを記録する。
    # 以前は下見の結果を書いていたので items が空になり、取り消せなかった
    items = [{"from": a, "to": b} for a, b in (st.get("pairs") or [])]

    # 作ったフォルダも記録する。ここが抜けていたので、
    # **フォルダを作っても /undo は「記録にありません」と言うだけ**だった。
    # 本物のデスクトップに作ったものは 手で消すしかなかった。
    #   ・記録するのは **フォルダだけ**。作ったファイルは入れない。
    #     取り消し側は「空のフォルダを消す」しかできないので、
    #     ファイルを入れると **取り消せない記録が先頭に居座り、
    #     その手前の操作を取り消せなくなる**。
    tsukutta = st.get("created")
    if (tsukutta and os.path.isdir(tsukutta)
            and not any(i["to"] == tsukutta for i in items)):
        items.append({"from": "", "to": tsukutta})

    if items:
        _guard().journal("plan", {
            "plan": plan, "slots": {k: v for k, v in slots.items()},
            "src": st.get("src", ""), "dest": st.get("dest", ""),
            "items": items,
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
# 見張り -- 聞かれる前に、次を構えておく
#
#   ここまでのカーネルは、聞かれてから動いていた。だから道具に見える。
#   一つ言われるたびに、それを「出来事」として覚え、
#   次に何が来るかを構えておく。
#     ・構えが当たっていれば、何も言わない（静かにしている）
#     ・大きく外れたら、そこではじめて口を開く
#   合っているうちは学ばない。おどろいた分だけ学ぶ。
# ============================================================
_MIMI = None


def mimamori():
    global _MIMI
    if _MIMI is None:
        import yosoku
        _MIMI = yosoku.Mimamori()
        f = os.path.join(HERE, "yosoku.json")
        if os.path.exists(f):
            try: _MIMI.load(f)
            except Exception: pass
    return _MIMI


# ものを壊しうる動作。先生が勝手に言い出したら、裏付けを求める
# 実際に使われている動作の名前で書かないと、素通りする。
# はじめ「削除」と書いていたが、本当の名前は「ごみばこ」だった。
# そのため「この動画をMP3にして」で 先生が出した ごみばこ が
# 素通りし、動画がゴミ箱へ移されていた。
KOWASU_ACTS = {"ごみばこ", "移動", "しわけ"}


def _kowasu_konkyo(text, act):
    """言われた文の中に、その動作に当たる言葉が本当にあるか"""
    for w, v in SEED.items():
        if (isinstance(v, (list, tuple)) and len(v) == 2
                and v[0] == "動作" and v[1] == act and w in text):
            return True
    # 活用形も裏付けとして認める。
    # 札には「移動」しか無いので、「ダウンロードから書類を移して」の
    # 「移して」が裏付け無しと判定され、正しい依頼まで断っていた。
    #
    # ここで使うのは活用表そのもの（規則で作った、確かな対応）だけ。
    # 「似ている」で寄せる当て方は、ここには絶対に入れない。
    # それをやったせいで「して」が「消して」に化けたのだから。
    try:
        for w, v in _pred_table().items():
            if v == act and w in text:
                return True
    except Exception:
        pass
    try:
        for w, (sl, va) in (load_learned() or {}).items():
            if sl == "動作" and va == act and w in text:
                return True
    except Exception:
        pass
    return False


def _tsumazuki(text, slots=None, riyuu="", tokoro=""):
    """詰まったことを控える。何を棚に足すべきかを、勘でなく実測で決めるため"""
    try:
        import tarinai
        tarinai.tsumazuita(text, slots, riyuu, tokoro)
    except Exception:
        pass


def _dekigoto(slots):
    """スロットを「出来事」にする。時間帯も手がかりに入れる"""
    h = datetime.datetime.now().hour
    obi = "朝" if h < 11 else "昼" if h < 17 else "夜"
    e = {"時": obi}
    for k in ("動作", "場所", "種類"):
        if slots.get(k):
            e[k] = slots[k]
    return e


def kamae(k=3):
    """次に来そうなこと。まだ何も言われていなくても呼べる"""
    try:
        return mimamori().yosou(k)
    except Exception:
        return []


def _mimamoru(slots):
    """一つ済んだので、覚えて、おどろきを測る"""
    try:
        m = mimamori()
        e = _dekigoto(slots)
        od = m.kita(e)
        m.save(os.path.join(HERE, "yosoku.json"))
        return od, m.hen(od, e)
    except Exception:
        return None, False

# ============================================================
# 入口
# ============================================================
# 聞き返して、返事を待っている状態。
# 「1」や「はい」だけ言われたときに、何の話だったかを思い出すために持つ
MACHI = {"枠": None, "候補": [], "文": ""}

# 直前に答えたときの中身。「それ」「さっきの」を受けるために持つ。
#   {"文": 元の言い方, "slots": 枠, "files": 実際に見ていたファイル}
MAE = {"文": "", "slots": {}, "files": []}

# 「それ」「さっきの」＝ 直前の話の続き
# はじめ「上の」も入れていたが、「机の上の…」が全部 指示語になり、
# 前の問いの枠を引き継いで 答えが狂った（作った問題で見つかった）。
# 紛れの無い言い方だけにする。「そこ」も場所の言い方と紛れるので外した
_SORE = _re.compile(r"(それ|そいつ|そのファイル|その中身|さっきの|さっき見た|"
                    r"いまの|今の|残りを|残りは|続きを)")

_HENJI = _re.compile(r"^\s*([1-9１-９]|はい|うん|そう|それ|そうです|ok|OK)\s*[。.！!]?\s*$")


def _henji_wo_uketoru(text):
    """聞き返しへの短い返事なら、元の文に候補を足して返す。違えば None"""
    if not MACHI["候補"]:
        return None
    m = _HENJI.match(text)
    if not m:
        return None
    t = m.group(1)
    if t in ("はい", "うん", "そう", "それ", "そうです", "ok", "OK"):
        i = 0
    else:
        i = "０123456789".find(t) if t in "0123456789" else -1
        if i < 0:
            i = "0１２３４５６７８９".find(t)
        i -= 1
    if not (0 <= i < len(MACHI["候補"])):
        return None
    erabu = MACHI["候補"][i]
    moto = MACHI["文"]
    MACHI["候補"] = []
    return f"{moto} {erabu}"


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
    raw_in = text          # 言われたままの文（あとで「それ」の控えに使う）
    # 関所も 読点は無いものとして見る。
    # 「ゴミ箱を、空にして」で 断りの関所が外れ、
    # 「場所はどこですか」と聞き返すところまで進んでいた（壊す側が見つけた）。
    # 読点ひとつで 安全の仕掛けが外れてはいけない
    text = _TEN.sub("", text)
    # 「1」「はい」だけの返事なら、さっき聞き返した話の続きとして読む
    _tsuzuki = _henji_wo_uketoru(text)
    if _tsuzuki:
        print(f"    （さっきの続きとして「{_tsuzuki}」と読みます）")
        text = _tsuzuki
        raw_in = text

    # 「それを整理して」の「それ」は、直前に答えた中身のこと。
    #
    # いままで 会話の履歴は持っていたのに、次の入力の材料にしていなかった。
    # そのため 毎回 場所と種類を言い直す必要があった。
    #
    # ただし ここは いちばん危ない所でもある。
    # 「それを消して」の「それ」を取り違えたら 取り返しがつかない。
    # だから 三つ 守る:
    #   ① 直前の答えが 読むだけのときだけ 受ける（動かした直後は受けない）
    #   ② 何を指しているのか 必ず口に出す
    #   ③ 受け継ぐのは 場所・種類・時期 だけ。動作は 今回の文から取る
    _sore_uketa = ""
    if _SORE.search(text) and MAE["slots"]:
        _sore_uketa = MAE["文"]

    # 言われる前に構えていたものを、控えておく（当たったか後で見る）
    maekamae = kamae(3)

    # 「ゴミ箱を空にして」は、ゴミ箱へ 捨てる ことではない。
    # 札は「ゴミ箱」を見て 動作【ごみばこ】にしていたので、
    # 場所を聞き返し、答えたら その場所の中身を捨てるところだった（実測）。
    # ゴミ箱を空にする＝取り返しがつかない。ここは やらない と決めている。
    if _GOMI_KARA.search(text):
        kotae = ("ゴミ箱を空にすることは しません。\n"
                 "  一度空にすると 取り返しがつかないからです。\n"
                 "  ご自身で Finder のゴミ箱を開いて「空にする」を押してください。\n"
                 "  （中に何が入っているかを見るだけなら、お手伝いできます）")
        print(kotae)
        return kotae

    _p("[1] カードを引く")
    slots = draw_cards(text, verbose=not quiet)
    if _sore_uketa:
        tsugu = {k: v for k, v in MAE["slots"].items()
                 if k in ("場所", "種類", "時期", "パス", "除く", "対象")
                 and k not in slots}
        if tsugu:
            slots.update(tsugu)
            iu = "・".join(f"{k}は{v}" for k, v in tsugu.items())
            print(f"    「それ」＝ さっきの「{_sore_uketa}」のこと"
                  f"（{iu}）として読みます")
    _p(f"    → {slots if slots else '（何も引けなかった）'}")

    if READ_ONLY and not readonly:
        readonly = True
        _p("    （読むだけモードなので、ものは動かしません）")
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
            _oya = place_dir(slots["場所"])
            _hori = dig_into(_oya, slots)
            if _hori is not None:
                # 名前はフォルダだった → 場所として使い切ったので、
                # 絞り込みの条件としては残さない
                #
                # ただし、掘り下げた先を控えておくこと。
                # 前はここで 名前 を捨てるだけだった。
                # あとで さがす が dig_into をもう一度呼ぶのに、
                # そのときには 名前 が消えているので掘れず、
                # いつも親フォルダに戻っていた。
                #   「整理済みには何がある？」
                #     → 整理済みの中ではなく、デスクトップの一覧が出ていた
                if os.path.isdir(_hori) and os.path.abspath(_hori) != os.path.abspath(_oya):
                    slots["掘り先"] = _hori
                    _p(f"    「{slots['名前']}」の中を見ます")
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
    # 「◯◯を作って」で、作れるのは フォルダ・空ファイル・HTMLのページ だけ。
    # 動くもの（ゲーム・アプリ・道具）は、作る部品が そもそも無い。
    #
    # いままでは 作れないと分かっているのに 300通り探して 2.3秒 使い、
    # 最後に「組み立てられませんでした」とだけ言っていた。
    # 何が作れないのかも、何なら作れるのかも 言っていなかった。
    # ZIP のときは即座に断れているのに、ここだけ断れていなかった。
    if slots.get("動作") == "作成":
        tsukurenai = _TSUKURENAI.search(text)
        if tsukurenai:
            nani = tsukurenai.group(0)
            _p(f"    → 「{nani}」を作る部品がありません。探さずに断ります ✗")
            _tsumazuki(text, dict(slots), f"{nani} を作る部品がない", "部品")
            return (f"「{nani}」を作ることは、いまのわたしにはできません。\n"
                    f"  動くものを書く部品を ひとつも持っていないからです。\n"
                    f"  （持っていないのに 探し回って、"
                    f"別のもので埋めるほうが困ると思うので、正直に言います）\n"
                    f"\n"
                    f"  作れるのは この3つだけです:\n"
                    f"    ・フォルダ\n"
                    f"    ・空のファイル\n"
                    f"    ・HTMLのページ（白紙／ファイル一覧／文章）")


    # 知らない場所を名指しされたら、勝手にデスクトップで代用しない。
    #
    # 実際に起きた（作った問題が一発で見つけた）:
    #     「外付けディスクの画像を捨てて」
    #      → 外付けディスクは知らないので デスクトップが既定になり、
    #        **デスクトップの画像がゴミ箱へ入った**
    # 名指しされた場所と ちがう場所を触るのは、いちばんやってはいけないこと。
    _shiranai = _basho_rashii_shiranai(text, slots)
    if _shiranai:
        kotae = (f"「{_shiranai}」がどこなのか 分かりません。\n"
                 f"  知っているのは デスクトップ・ダウンロード・書類フォルダ だけです。\n"
                 f"  （分からないまま 別の場所で代わりにやると、"
                 f"取り返しがつかないので やりません）\n"
                 f"  場所そのもの（/Users/... のような道）で言ってもらえれば できます。")
        print(kotae)
        return kotae

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
            # ── 先生に、ものを壊す操作を発明させない ──────────────
            # 「この動画をMP3にして」で、カードは何も引けていないのに
            # 先生が 動作=削除 と答え、そのまま動画がゴミ箱へ移された。
            # 頼まれたのは 形を変えること。消すことではない。
            #
            # 先生が「消す」「移す」と言うなら、
            # 言われた文の中に、そう読める言葉が無ければならない。
            # 裏付けが無ければ、その案は採らない。
            if (got.get("動作") in KOWASU_ACTS
                    and slots.get("動作") != got.get("動作")
                    and not _kowasu_konkyo(text, got["動作"])):
                _p(f"    {who} は「{got['動作']}」だと言っていますが、"
                   f"言われた文にその言葉がありません。危ないので採りません ✗")
                _tsumazuki(text, dict(got),
                           f"先生が裏付けなく「{got['動作']}」を出した", "札引き")
                continue
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
        # ここで諦める前に、ふだんの くせ から埋められないか試す。
        # 「Downloads の音楽」とだけ言われても、その場所で
        # いつも数えているなら「数える」だろう、という当て方。
        # 勝手に実行はしない。必ず聞き返す。
        anaume = []
        for e, p, _n in kamae(5):
            for k in ("動作", "場所"):
                if k not in slots and e.get(k):
                    anaume.append((k, e[k], p))
        if anaume:
            # 前は いちばん確からしい一つだけ出して
            # 「そう書いてもう一度言ってください」と返していた。
            # 打ち直させるのは 相手の手間で、しかも 二番目の候補が
            # 正解のときに たどり着けなかった。
            # 候補を並べて、番号で答えられるようにする。
            k, v, p = max(anaume, key=lambda x: x[2])
            kouho, mita = [], set()
            for kk, vv, pp in sorted(anaume, key=lambda x: -x[2]):
                if kk != k or vv in mita:
                    continue
                mita.add(vv)
                kouho.append((vv, pp))
                if len(kouho) >= 3:
                    break
            MACHI["枠"], MACHI["候補"] = k, [x[0] for x in kouho]
            MACHI["文"] = text
            gyou = [f"「{k}」が言われていないので、決められません。どれでしょう？"]
            for i, (vv, pp) in enumerate(kouho, 1):
                gyou.append(f"  {i}) {vv}　（ふだんの様子だと {pp:.0%}）")
            gyou.append("  → 番号で答えてください。"
                        "1番でよければ「はい」でもかまいません")
            kotae = "\n".join(gyou)
            print("    → " + gyou[0])
            return kotae
        print("    → 結局わかりませんでした")
        _tsumazuki(text, slots, "札が引けなかった", "札引き")
        return "何を言われたのか分かりませんでした"

    # ── 作れない形式を頼まれたら、はっきり断る ──────────────────
    #
    # 「デスクトップの画像をZIPにして」で、ZIP は作れないのに
    # 「HTMLをつくる」が答えを出し、Desktop の中身.html を作っていた。
    # 「写真をPDFにまとめて」でPDFという名のフォルダを作ったのと同じ形。
    # できないことは、できないと言う。別のもので埋めない。
    _kt = _katachi_youkyuu(text)
    if _kt and _kt not in _TSUKURERU_KATACHI:
        _p(f"    → 「{_kt}」を作る部品がありません。別のことで埋めません ✗")
        _tsumazuki(text, dict(slots), f"{_kt} を作る部品がない", "部品")
        return (f"{_kt} を作ることは、いまのわたしにはできません。\n"
                f"（できるふりをして別のものを作るほうが困ると思うので、"
                f"そこは正直に言います）\n"
                f"数える・一覧・整理・移動・改名・ゴミ箱・HTML なら できます。")

    # ── 壊す動作の、最後の裏付け確認 ────────────────────────────
    #
    # 以前この確認は「先生の答え」にしか掛けていなかった。
    # だからカードや文法から出てきた ごみばこ／移動 は素通りしていて、
    # 「この動画をMP3にして」で動画がゴミ箱へ移る事故が直っていなかった。
    #
    # 動作がどこから来たかは関係ない。ものを壊すなら、
    # 言われた文の中に、そう読める言葉が無ければならない。
    if slots.get("動作") in KOWASU_ACTS and not _kowasu_konkyo(text, slots["動作"]):
        _p(f"    →「{slots['動作']}」と読み取れましたが、"
           f"言われた文にその言葉がありません。危ないのでやりません ✗")
        _tsumazuki(text, dict(slots),
                   f"裏付けなく「{slots['動作']}」になった", "札引き")
        return (f"「{text}」が、どうしてほしいのか分かりませんでした。\n"
                f"（{slots['動作']}のことかとも読めましたが、"
                f"そう書かれていないので、勝手にはやりません）")

    shape = shape_of(slots)
    nb    = load_note()
    plan  = None

    _yomu_dake = slots.get("動作") in READ_ACTS
    _p("\n[2] ノートを見る")
    if shape in nb and _yomu_dake and any(p in DESTRUCTIVE for p in nb[shape]["手順"]):
        _p("    → 覚えていた手順に、ものを動かす部品が混ざっている。捨てます")
        del nb[shape]; save_note(nb)
    # 読むだけの頼みに、ものを作る・動かす部品が混ざった手順は
    # ノートに入っていても 使わない。
    #
    # ここは 近道なので goal_reached を通っていない。
    # そのため「さがす → つくる → おおきいじゅん → ならべる」という
    # 一度おぼえた手順が 検証されないまま走り続け、
    # 「いちばん大きいファイルは」と聞くたびに フォルダが作られていた。
    # 一度おぼえた誤りが 永久に残る形だった（作った問題500問で見つかった）。
    if shape in nb and not ((readonly or _yomu_dake) and
                            any(p in DESTRUCTIVE for p in nb[shape]["手順"])):
        plan = nb[shape]["手順"]
        _p(f"    → 知っている形だった： {' → '.join(plan)}")
        chk, bad = try_plan(plan, slots)
        # ここは設計を間違えていた。
        #   「0件しか出なかった＝手順が悪い」と決めつけていた。
        # だが、フォルダが空なら 0件が正しい答えである。
        # 正しい答えを「空振り」とみなして捨て、別の手順を探し回っていた。
        # もとが 0件（＝そもそも何も無い）なら、0件を答えとして受け取る。
        # 覚えていた手順でも、言われた条件を使い切っているか 必ず確かめる。
        #
        # ここは近道なので、長いあいだ goal_reached を通していなかった。
        # そのため 一度おぼえた誤りが 検証されずに走り続けていた。
        #   ・聞かれただけで フォルダを作る手順（今日 直した）
        #   ・「フォルダを作って」に HTMLをつくる を返す手順（今日 直した）
        # 近道は 速さのためのものであって、検査を飛ばす口実ではない。
        _joken = True
        if not bad:
            try:
                _joken = goal_reached(chk, slots, plan)
            except Exception:
                _joken = True          # 確かめられないなら 今まで通り通す
        if not _joken:
            _p("    → ただし言われた条件を使い切っていません。組み立て直します")
            plan = None
        elif bad or (not chk.get("files") and not chk.get("dirs") and chk.get("もと", 0) > 0):
            _p(f"    → ただし今回は空振り（{bad or '0件'}）。組み立て直します")
            plan = None
        else:
            st = run_plan(plan, slots)
            nb[shape]["回数"] += 1; save_note(nb)
            NOTE_HIT["形"] += 1
            _p(f"\n[3] 実行（探さずに即実行）")
    if plan is None:
        if shape not in nb:
            _p("    → 知らない形。ノートの中から、にている状況を探します")
        # ────────────────────────────────────────────────
        # 形が合わなくても、状況が「にて」いれば手順は使い回せることが多い。
        #   覚えた形: 動作+場所+種類 / 数える
        #   来た形  : 動作+場所+種類+時期 / 数える
        # 上の2つは、やることは同じ。形の一致だけだと当たらない。
        #
        # ただし「にている」は当てずっぽう。そのまま実行してはいけない。
        # 実測でも「移動＋2条件」が「移動だけ→しわけ」に引かれた。
        # これは昔デスクトップを全部動かした事故と同じ形なので、
        # 必ず下見（try_plan）で確かめてから使う。
        # ────────────────────────────────────────────────
        try:
            for sc, past, cand in simnote().recall(slots, 3):
                if readonly and any(x in DESTRUCTIVE for x in cand):
                    continue
                _p(f"    にている過去（近さ {sc:.3f}）： "
                   f"{shape_of(past)} → {' → '.join(cand)}")
                chk, bad = try_plan(cand, slots)
                if bad or (not chk.get("files") and not chk.get("dirs") and chk.get("もと", 0) > 0):
                    _p(f"       確かめる → {bad or '0件'} ✗ 使わない")
                    continue
                if not goal_reached(chk, slots, cand):
                    _p("       確かめる → 条件を使い切っていない ✗ 使わない")
                    continue
                _p("       確かめる → 通った ✓ これを使います")
                plan = cand
                st = run_plan(plan, slots)
                # ここで 回数 を 1 に戻していた。ノートが当たった回なのに、
                # 溜まっていた数（たとえば12）が 1 に落ちる。
                # 元の数を引き継ぐ
                nb[shape] = {"手順": plan,
                             "回数": nb.get(shape, {}).get("回数", 0) + 1}
                save_note(nb)
                NOTE_HIT["にた"] += 1
                break
        except Exception as e:
            _p(f"    （にている過去は使えませんでした： {e}）")
    if plan is None:
        _p("\n[3] 組み立てる（置いて、実行して、確かめる）")
        first = 1800 if THINK_HARD else 300
        plan, st = solve(slots, verbose=not quiet, allow=allow, budget=first)

        # ── 別の道すじでも同じ答えになるか、確かめる ──────────────
        #
        # 今日直したバグの半分は「別の道すじなら違う答えが出た」ものだった。
        #   ・大きい順と言われて 小さい順に並べていた
        #   ・対象（ファイル／フォルダ）を見ずに数えていた
        #   ・場所の名前の中の語を 二重に取っていた
        # どれも 答えの形は正しく見えるので、正解だけ見ていても分からない。
        # 読むだけの頼みなら、二通り目を探して 突き合わせる。
        # 食い違ったら「自信がない」と言う。黙って片方を出さない。
        # （ものを動かす頼みでは やらない。二回動いてしまう）
        if (plan is not None and not FUTAMICHI_YAMERU
                and slots.get("動作") in READ_ACTS):
            _hoka = _futatsume(plan, slots, allow, first)
            if _hoka is not None:
                _p(f"    ⚠ 別の道すじ（{' → '.join(_hoka[0])}）だと"
                   f" 答えが違いました")
                _p("      どちらが正しいか決められないので、そう申し上げます")
                return ("同じことを 二通りのやり方で確かめたところ、"
                        "答えが食い違いました。\n"
                        f"  ひとつめ: {_mijikaku(st.get('answer'))}\n"
                        f"  ふたつめ: {_mijikaku(_hoka[1].get('answer'))}\n"
                        "  どちらが正しいか こちらでは決められないので、"
                        "言い方を変えて もう一度お願いします。")
        if plan is None:
            # ────────────────────────────────────────────────────
            # 行き詰まったら、外に聞く前に「もっと長く考える」。
            #
            # ここは最初、視点を変えた何人かに探させる合議にしていた。
            # 測ったら、そちらは弱かった（council_bench.py）:
            #
            #   考える量    ひとり   6人で合議   ひとり・6倍考える
            #     8通り     2/10     2/10        7/10
            #    20通り     2/10     4/10        8/10
            #    80通り     8/10     8/10       10/10 （合議の3倍速い）
            #
            # 人数を増やすより、ひとりが長く考えるほうが、強くて速かった。
            # だから、まず考える量を10倍にして、深さも伸ばす。
            # 掛け算は1回も増えない。増えるのは考える時間だけ。
            # ────────────────────────────────────────────────────
            _p("\n[3a] 行き詰まった → もっと長く考える（10倍・8手まで）")
            plan, st = solve(slots, verbose=False, allow=allow,
                             budget=first * 10, max_depth=8)
            if plan is not None:
                _p(f"    → 見つかった： {' → '.join(plan)}")
        if plan is None:
            # それでも駄目なら、視点を変えた何人かで探す。
            # 長く考えるより弱いが、探し方が違うので、
            # 一本道では届かない案が出ることがある（実測 8/10 → 10/10）
            _p("\n[3b] それでも駄目 → 探し方を変えた何人かで探す")
            try:
                import council
                plan, st, _lg = council.deliberate(
                    slots, allow=allow, per_view=4, budget=1200, max_depth=8,
                    verbose=not quiet)
            except Exception as e:
                _p(f"    （合議はできませんでした： {e}）")
                plan = None
        if plan is None:
            _p("    → 自力では組み立てられませんでした")
            _p("\n[3c] 先生に相談する（案は信用せず、必ず下見で確かめる）")
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
                _tsumazuki(text, slots, "手順を組み立てられなかった", "組み立て")
                return "やり方を組み立てられませんでした"
        _p(f"\n[4] 決まった手順を、本番で1回だけ実行する")
        st = run_plan(plan, slots)
        # 0件しか出なかった手順は、ノートに書かない。
        # 「ダウンロードには何がある？」で、Downloads が空だったとき、
        # 90回さまよった末の「0件の手順」を覚えてしまっていた。
        # 空だったのは手順のせいではないので、覚える値打ちがない。
        karappo = (not st.get("files")) and not st.get("answer")
        if karappo:
            _p("\n[5] ノートには書きません（0件だったので、覚える値打ちがない）")
        else:
            # 組み立て直しでも、その形を使った回数は消さない。
            # ここで 1 に戻していたので、ノートが育つほど
            # 「回数の合計」が下がり、当たった回数の集計が
            # マイナスになっていた（bench で -23/33 が出た）
            # ── 覚える前に、要らない部品を落とす（説明にもとづく学習）──
            #
            # いままでは うまくいった手順を そのまま丸ごと覚えていた。
            # そのため「さがす → つくる → おおきいじゅん → ならべる」の
            # ような、要らない「つくる」を含む手順が焼き付き、
            # 聞かれただけで フォルダができるようになっていた。
            # 私が手で「つくる」を危険部品に足して塞いだが、
            # 本当は「どの部品が答えに効いたか」を こちらで判じるべきだった。
            #
            # やり方: 一つ抜いて、同じ答えになり、条件も満たすなら、
            #         その部品は 要らなかった。抜いて覚える。
            plan = _kezuru(plan, slots, st, verbose=not quiet)
            nb[shape] = {"手順": plan,
                         "回数": nb.get(shape, {}).get("回数", 0) + 1}
            save_note(nb)
            try:
                simnote().add(slots, plan)      # にた状況でも引けるように
            except Exception:
                pass
            _p(f"\n[5] ノートに書いた： {shape}")
            _p(f"    {' → '.join(plan)}")

    # 次に「それ」と言われたときのために、いま見ていた中身を控える。
    # 動かしたあとは 控えない（動いた後の「それ」は、もう別のものを指す）
    if slots.get("動作") in READ_ACTS:
        MAE["文"] = raw_in
        MAE["slots"] = dict(slots)
        MAE["files"] = list((st or {}).get("files") or [])
    else:
        MAE["文"], MAE["slots"], MAE["files"] = "", {}, []

    # 済んだことを覚え、おどろきを測る
    od, hen = _mimamoru(slots)
    atatta = any(_dekigoto(slots) == e for e, _p2, _n in maekamae)

    dt = time.time() - t0
    _p("─" * 58)
    where = "本物のフォルダ" if ROOT == "real" else "練習用フォルダ(sandbox)"
    print(f"答え：（{where}を見ています）")
    kotae = st.get("answer")
    if not kotae or not kotae.strip():
        # 空欄を返していた。何も無いなら、そう言うのが答え
        basho = slots.get("場所") or slots.get("パス") or "そこ"
        kotae = f"{basho} には何もありません"
    print(f"      {kotae.replace(chr(10), chr(10)+'      ')}")
    print(f"かかった時間： {dt*1000:.1f} ミリ秒")
    if hen and od is not None:
        print(f"　（いつもと違いますね。おどろき {od:.2f}）")
    elif atatta:
        print("　（これは構えていました）")
    tsugi = kamae(1)
    if tsugi and tsugi[0][1] >= 0.5:
        e = tsugi[0][0]
        naka = "・".join(str(v) for k, v in e.items() if k != "時")
        if naka:
            print(f"　つぎは「{naka}」ですか？（{tsugi[0][1]:.0%}）")
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
