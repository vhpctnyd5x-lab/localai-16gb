#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chat.py -- kernel.py の「会話層」

kernel.py は命令しか扱えない。この層は、命令でない入力(雑談・質問・独り言)に
返事をするためのもの。設計思想は kernel.py と同じ:

  ・ふだんは掛け算(ニューラルネット推論)を一切しない。
    classify() は文字パターンとスロットだけで判定し、LLM を呼ばない。
  ・先生(LLM)を呼ぶのは「返事を作るとき」と「分類に行き詰まったとき」だけ。
  ・覚えたことは SQLite に残り、次の会話に効いてくる。
  ・recall() も埋め込みモデルを使わない。文字 2-gram の重なり(Jaccard)を
    語の希少度(IDF 的な重み)で補正するだけ。標準ライブラリのみ。

使い方:
    python3 chat.py          対話ループ  (:quit で終了、:mem で記憶を表示)
"""

from __future__ import annotations

import math
import os
import re
import sqlite3
import sys
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

DEFAULT_DB = os.path.join(HERE, "memory.db")

# ============================================================
# (0) 文字あつかいの下ごしらえ
# ============================================================

# 記号・空白を落とすための表。ここで落とした文字は n-gram に入らない。
_DROP_RE = re.compile(r"[\s、。，．,\.!！?？「」『』()（）\[\]【】…ー~〜:：;；\"'`]+")


def normalize(text: str) -> str:
    """全角/半角のブレをならし、記号と空白を落として比較用の文字列にする。"""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).lower()
    return _DROP_RE.sub("", s)


def ngrams(text: str, n: int = 2) -> set:
    """文字 n-gram の集合。短すぎる文はその文字自身を 1 個だけ返す。"""
    s = normalize(text)
    if len(s) <= n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


# ============================================================
# (1) 分類 -- LLM を呼ばずに済むなら絶対に呼ばない
# ============================================================

# 命令らしさを直に示す語尾・依頼表現。スロットが片方しか無くてもこれで命令に倒す。
_ORDER_TAIL = (
    "して", "してくれ", "してよ", "しといて", "しとい", "ください", "くださ",
    "ちょうだい", "頼む", "たのむ", "お願い", "おねがい", "やって", "やっと",
    "まとめて", "整理して", "片付けて", "開いて", "ひらいて", "消して", "けして",
    "作って", "つくって", "コピーして", "移動して", "動かして", "実行", "起動",
    "教えて", "見せて", "みせて", "出して", "だして", "探して", "さがして",
    "数えて", "かぞえて", "並べて", "ならべて", "しろ", "せよ",
)

# 雑談らしさ: あいさつ・相づち・感情の吐露。
_CHAT_WORD = (
    "こんにちは", "こんばんは", "おはよう", "やあ", "ハロー", "はろー", "hello", "hi",
    "ありがとう", "ありがと", "thanks", "サンキュー", "よろしく", "はじめまして",
    "おつかれ", "お疲れ", "ごめん", "すまん", "すみません", "さようなら", "またね",
    "そうなんだ", "なるほど", "へえ", "ふーん", "まじか", "すごい", "すご",
    "つかれた", "疲れた", "ねむい", "眠い", "たのしい", "楽しい", "うれしい",
    "嬉しい", "かなしい", "悲しい", "つらい", "辛い", "おなかすいた", "腹減",
    "元気", "げんき", "調子どう", "どう思う", "だと思う", "気がする", "な気分",
)

# 一人称の感想・独り言。「〜だなあ」「〜かも」など。
_MONOLOGUE_TAIL = (
    "かな", "かなあ", "かなー", "だなあ", "だなー", "だね", "ですね", "だよね",
    "かも", "かもしれない", "気がする", "と思う", "とおもう", "みたい", "らしい",
    "でした", "だった", "ちゃった", "しまった", "のに", "けどね",
)

# 疑問符・疑問詞。ただし「〜を数えて何個？」のように命令スロットが揃っていれば命令優先。
_QUESTION_MARK = ("?", "？")

# 「ファイルの話をしている」と判断できる語。問い合わせの判定に使う
# 相手や自分のことを聞いている合図。これがあれば雑談
_SELFISH = ("あなた", "きみ", "君は", "君の", "お前", "自分", "私のこと",
            "誰", "だれ", "何者", "なにもの")

_FILEISH = ("ファイル", "フォルダ", "ディレクトリ", "写真", "画像", "動画",
            "pdf", "書類", "資料", "メモ", "デスクトップ", "ダウンロード",
            "中身", "入って", "何がある", "なにがある")
_QUESTION_WORD = (
    "なに", "何", "なぜ", "なんで", "どうして", "どこ", "だれ", "誰", "いつ",
    "どう", "どんな", "どっち", "どちら", "いくつ", "ですか", "ますか", "の？",
)

# 命令に必須のスロット名(kernel.py の SEED と対応)
_ACT = "動作"
_PLACE = "場所"

# 「〜てくれる？」「〜てもらえる？」のような、頼みごとの形。
# 「ください」「ほしい」も同じ仲間
_REQUEST = re.compile(
    r"(?:て|で)\s*(?:くれる|くれない|くれます|もらえる|もらえない|もらえます|"
    r"もらっていい|いただけ)(?:か|の)?[？?]?\s*$"
    r"|(?:て|で)\s*(?:ください|ちょうだい|ほしい|ほしいな|おいて)\s*[。！!]?\s*$")


def _has(text: str, words) -> bool:
    return any(w in text for w in words)


def _ends_with(text: str, tails) -> bool:
    t = text.rstrip("。．.!！?？ 　")
    return any(t.endswith(x) for x in tails)


def mono_no_hanashi(text: str) -> bool:
    """ファイル・フォルダ・場所・頼みごとの気配があるか（無ければ、先生に分類を聞くまでもなく雑談）。
    ★ 2026-09-12: 算数の問いを「あいまい」→先生が「命令」→ consult に 900トークン ×2 → 雑談へ、
      という回り道で 1回の返事に 204秒かかっていた。ものの話でなければ、その回り道に入れない。"""
    low = unicodedata.normalize("NFKC", text or "").lower()
    if "/" in low or "~" in low:
        return True
    # 「説明して」「教えて」も頼みの形だが、**もの**が出てこなければ カーネルの出番ではない
    return _has(low, _FILEISH)


def classify(text: str, slots: dict) -> str:
    """入力が「命令」「雑談」「あいまい」のどれかを、LLM を使わずに判定する。

    引数:
        text  : 生の入力文
        slots : kernel.draw_cards() が埋めたスロット辞書 (例 {"動作":"移動","場所":"Desktop"})

    戻り値: "命令" / "雑談" / "あいまい"
            "あいまい" のときだけ、呼び出し側が先生に聞けばよい。
    """
    raw = (text or "").strip()
    if not raw:
        return "あいまい"

    low = unicodedata.normalize("NFKC", raw).lower()
    slots = slots or {}
    has_act = _ACT in slots
    has_place = _PLACE in slots
    has_obj = ("種類" in slots) or ("時期" in slots)

    order_tail = (_ends_with(low, _ORDER_TAIL)
                  or _has(low, ("してください", "してくれ", "お願いします")))

    # 場所もパスも無いのに動作カードだけ引けた時は、命令ではない。
    # 「自分の言葉で教えて」の「教えて」を【一覧】と読んで、
    # ファイル一覧を出そうとしてしまう事故を防ぐ
    if slots and "場所" not in slots and "パス" not in slots \
            and not _has(low, _FILEISH):
        return "雑談"

    # 日本語の「依頼形」。？で終わるが、質問ではなく頼みごと。
    #   「寄せといてくれる？」「移してもらえる？」「やってくれない？」
    # ここを見ていなかったので、頼みごとが質問と読まれ、
    # 一覧が返るだけで何もしてくれなかった。
    # ただし、はっきりした依頼の形だけに限る。
    # 「〜って何？」のような問いを巻き込むと、質問でものが動いてしまう
    if _REQUEST.search(low) and (has_act or has_place):
        return "命令"

    # --- 0) 疑問形かどうかを、何よりも先に見る ★ ----------------------
    #    「〜には何がある？」のような問いで、ものを動かしてはいけない。
    #    以前ここを後回しにしていたため、質問でファイルを移動する事故が起きた。
    is_question = (raw.rstrip().endswith(_QUESTION_MARK)
                   or _has(low, _QUESTION_WORD))
    if is_question and not order_tail:
        # ファイルやフォルダの話だと分かる時だけ「問い合わせ」。
        # 時期だけ・種類だけで判断すると、雑談を問い合わせに化けさせる
        if _has(low, _FILEISH) and (has_place or has_obj or _has(low, _FILEISH)):
            return "問い合わせ"
        if has_place and not _has(low, _SELFISH):
            return "問い合わせ"
        return "雑談"

    # --- 1) スロットが揃っていれば「命令」。ここが最速路。 -------------
    if has_act and has_place:
        return "命令"

    # --- 2) 依頼の語尾があり、動作か場所のどちらかが取れていれば命令 -----
    if order_tail and (has_act or has_place or has_obj):
        return "命令"

    # --- 3) 明確な雑談マーカー -------------------------------------------
    #    あいさつ語だけ / 感情の吐露は、スロットが多少取れていても雑談。
    if _has(low, _CHAT_WORD):
        # 「デスクトップの写真まとめて、ありがとう」のような混在は命令を優先
        if not (has_act and (has_place or has_obj)):
            return "雑談"

    # 一人称の感想・独り言の語尾
    if _ends_with(low, _MONOLOGUE_TAIL):
        return "雑談"

    # 自己開示(「私の名前は〇〇です」「僕は東京に住んでる」)は雑談で確定。
    # 覚えるべき事実の型と同じパターンを使い回すので、追加コストはほぼ無い。
    if not order_tail and any(p.search(raw) for p, _ in _FACT_PATTERNS):
        return "雑談"

    # --- 4) スロットが何も取れず、依頼語尾も無い短文 → 雑談寄りだが断定しない -
    if not slots and not order_tail:
        # 「うん」「はい」のような相づちは雑談で確定してよい
        if len(normalize(raw)) <= 3:
            return "雑談"
        return "あいまい"

    # --- 5) それ以外は判断保留 -------------------------------------------
    return "あいまい"


# ============================================================
# (2) 記憶 -- SQLite。埋め込みは使わない
# ============================================================

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    REAL    NOT NULL,
    role  TEXT    NOT NULL,
    text  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    ts    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);
"""

# 「私の名前は〇〇です」のような、そのまま覚えてよい事実の型。
_FACT_PATTERNS = [
    (re.compile(r"(?:私|わたし|僕|ぼく|俺|おれ)の名前は([^\s。、,\.！!？?]{1,20})"), "名前"),
    (re.compile(r"(?:私|わたし|僕|ぼく|俺|おれ)は([^\s。、,\.！!？?]{1,20})(?:です|だ|と言います|といいます|と申します)"), "名前"),
    (re.compile(r"(?:私|わたし|僕|ぼく|俺|おれ)の(?:好きな|すきな)([^\sは]{1,10})は([^\s。、,\.！!？?]{1,20})"), None),
    (re.compile(r"(?:私|わたし|僕|ぼく|俺|おれ)は([^\s。、,\.！!？?]{1,20})に(?:住んで|すんで)"), "住んでいる場所"),
    (re.compile(r"(?:私|わたし|僕|ぼく|俺|おれ)の(?:仕事|職業)は([^\s。、,\.！!？?]{1,20})"), "仕事"),
]


# 事実の値の末尾に残りがちな丁寧語・助動詞。ここを削らないと「アキトです」と覚えてしまう。
_COPULA_TAIL = ("なんです", "なのです", "だったんだ", "なんだ", "ですよ", "だよ",
                "でした", "だった", "です", "だす", "だ", "ます")


def trim_copula(value: str) -> str:
    """「アキトです」→「アキト」。短くなりすぎる場合は削らない。"""
    v = (value or "").strip()
    for t in _COPULA_TAIL:
        if v.endswith(t) and len(v) - len(t) >= 1:
            return v[: -len(t)]
    return v


class Memory:
    """会話の記憶。SQLite で永続化する。

    ・add()    : 発言を 1 件ためる。事実らしければ facts にも自動で書く。
    ・recent() : 直近の会話。
    ・recall() : 関連する過去の発言。文字 2-gram の重なりを IDF で重み付け。
    ・note()   : 「私の名前は〇〇」のような事実を明示的に覚える。
    """

    def __init__(self, path: str = DEFAULT_DB):
        self.path = path
        # 画面(アプリ)からは別のスレッドで呼ばれる。
        # 既定のままだと「別のスレッドからは使えない」と怒られる。
        # 同時に触らないよう、呼ぶ側で順番を守っている（server._LOCK）
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()
        # recall 用のキャッシュ。add のたびに捨てる。
        self._cache = None

    # ------------------------------------------------ 書く

    def add(self, role: str, text: str) -> int:
        """発言を 1 件ためる。戻り値は行 id。"""
        text = (text or "").strip()
        if not text:
            return -1
        ts = time.time()
        cur = self.conn.execute(
            "INSERT INTO turns(ts, role, text) VALUES(?,?,?)", (ts, role, text))
        self.conn.commit()
        self._cache = None
        if role == "user":
            self._auto_note(text)
        return int(cur.lastrowid)

    def _auto_note(self, text: str) -> None:
        """発言から自明な事実を拾って facts に入れる。取れなければ何もしない。"""
        for pat, key in _FACT_PATTERNS:
            m = pat.search(text)
            if not m:
                continue
            if key is None:
                # 「私の好きな色は青」型: グループ1がキー、2が値
                if m.lastindex and m.lastindex >= 2:
                    self.note("好きな" + m.group(1), m.group(2))
            else:
                self.note(key, m.group(1))
            return

    def note(self, key: str, value: str) -> None:
        """事実を覚える(同じキーは上書き)。"""
        key = (key or "").strip()
        value = trim_copula(value)
        if not key or not value:
            return
        self.conn.execute(
            "INSERT INTO facts(key, value, ts) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, ts=excluded.ts",
            (key, value, time.time()))
        self.conn.commit()

    def wipe(self) -> None:
        """覚えていることを全部消す（/forget ぜんぶ で呼ばれる）"""
        self.conn.executescript(
            "DELETE FROM turns; DELETE FROM facts;")
        self.conn.commit()

    # ------------------------------------------------ 読む

    def facts(self) -> dict:
        rows = self.conn.execute(
            "SELECT key, value FROM facts ORDER BY ts DESC").fetchall()
        return {k: v for k, v in rows}

    def recent(self, n: int = 8) -> list:
        """直近の会話を古い順で返す。[{"id","role","text","ts"}, ...]"""
        rows = self.conn.execute(
            "SELECT id, ts, role, text FROM turns ORDER BY id DESC LIMIT ?",
            (int(n),)).fetchall()
        rows.reverse()
        return [{"id": r[0], "ts": r[1], "role": r[2], "text": r[3]} for r in rows]

    # -------- recall: 文字 2-gram Jaccard + IDF 重み ----------------------

    def _index(self):
        """全発言の n-gram と、gram ごとの出現文書数(df)を作ってキャッシュする。

        埋め込みモデルは使わない。ここが「掛け算をしない」検索の本体。
        """
        if self._cache is not None:
            return self._cache
        rows = self.conn.execute(
            "SELECT id, ts, role, text FROM turns ORDER BY id").fetchall()
        docs = []
        df = {}
        for rid, ts, role, text in rows:
            g = ngrams(text)
            if not g:
                continue
            docs.append((rid, ts, role, text, g))
            for x in g:
                df[x] = df.get(x, 0) + 1
        n_docs = max(1, len(docs))
        # IDF: 珍しい gram ほど重い。よくある gram(「です」など)はほぼ 0 になる。
        idf = {x: math.log(1.0 + n_docs / (1.0 + c)) for x, c in df.items()}
        self._cache = (docs, idf, n_docs)
        return self._cache

    def recall(self, query: str, n: int = 3, exclude_ids=None) -> list:
        """query に関連する過去の発言を上位 n 件返す。

        戻り値: [{"id","role","text","score","ts"}, ...] スコア降順。
        """
        q = ngrams(query)
        if not q:
            return []
        docs, idf, n_docs = self._index()
        skip = set(exclude_ids or ())
        # 「私の名前は？」を投げた直後にその発言自身が最上位に来ないよう、
        # 正規化して同一の文は結果から外す。
        qn = normalize(query)
        # 未知の gram(この DB に一度も出ていない)は最大級に珍しいので重めに扱う
        unseen = math.log(1.0 + n_docs)

        def w(x):
            return idf.get(x, unseen)

        qw = sum(w(x) for x in q)
        out = []
        for rid, ts, role, text, g in docs:
            if rid in skip or normalize(text) == qn:
                continue
            inter = q & g
            if not inter:
                continue
            iw = sum(w(x) for x in inter)
            uw = qw + sum(w(x) for x in g) - iw
            if uw <= 0:
                continue
            # 重み付き Jaccard。さらに「質問語がどれだけ拾えたか」で軽く補正。
            score = (iw / uw) * (0.5 + 0.5 * (iw / qw if qw else 0.0))
            out.append({"id": rid, "ts": ts, "role": role,
                        "text": text, "score": round(score, 4)})
        out.sort(key=lambda d: (-d["score"], -d["id"]))
        return out[:int(n)]

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


# ============================================================
# (3) 返事づくり -- ここだけ先生(LLM)を呼ぶ
# ============================================================

# システムプロンプトは短く。長いと入力トークンが増えて遅くなる。
def _load_persona():
    """人格の設定。persona.json があればそれを使う（自由に書き換えてよい）"""
    import json as _j
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona.json")
    d = {"名前": "カーネル",
         "説明": "この人のパソコンの中だけで動く、手作りの相棒",
         "口調": "親しい相手に話すように、2文以内で短く",
         "できること": ""}
    if os.path.exists(p):
        try:
            d.update(_j.load(open(p, encoding="utf-8")))
        except Exception:
            pass
    return d


_P = _load_persona()

# 外部APIに丸投げすると「私はChatGPTです」と名乗ってしまうため、
# 名乗り方をこちらで固定する
SYS = (f"あなたの名前は「{_P['名前']}」。{_P['説明']}。"
       f"ChatGPT・Claude・Gemini など他の名前を名乗ってはいけない。"
       f"名前を聞かれた時だけ「{_P['名前']}」と答える。"
       # これが無いと毎回「カーネルです。」で始めてしまい、読みづらくなる
       f"毎回名乗ってはいけない。返事を「{_P['名前']}です」で始めてはいけない。"
       f"分からないこと・覚えていないことは、正直に分からないと言う。"
       + (f"できることは次の通りで、これ以外はできない：{_P['できること']}。"
          if _P.get("できること") else "")
       + f"日本語で、{_P['口調']}答える。前置き・箇条書き・記号は使わない。"
       # ★ 掟（2026-09-11 実測で入れた）。32問で 行動を促す 6/16→12/16、お世辞は元から合わせない(14/16→16/16)。
       #   「先に『違う』と言え」と書くと相談にまで「違う。」と返す(9/16)ので、その指示は入れないこと。
       + (f"{_P['掟']}" if _P.get("掟") else ""))

_ROLE_JA = {"user": "相手", "assistant": "あなた", "system": "メモ"}


NARABI = os.environ.get("KERNEL_ZATSUDAN_NARABI", "会話が先")
# ★ 2026-09-17: 頭脳が自分で道具を選ぶ（erabu.py）。一覧は system の末尾＝頼み文の頭に来るので、使い回しが効く。
#   KERNEL_DOUGU_ERABI=0 で前の形（道具を見せない）。
DOUGU_ERABI = os.environ.get("KERNEL_DOUGU_ERABI", "1") != "0"
# ★ 2026-09-18: 道具か雑談かを 1トークンの確率で先に決める（kimeru・Jev の真似）。**既定は切**:
#   物差し（dougu/hakaru_kimeru.py・36問）で 最良 22/36、返事に「道具: 言い方」を書かせる元の形は 約30/36。
#   はい/いいえ の確かめも当てにならなかった（正しい道具に p=0.001、似た語だけの雑談に 0.88）。KERNEL_KIMERU=1 で試せる
KIMERU = os.environ.get("KERNEL_KIMERU", "0") == "1"


def sys_dougu() -> str:
    if not DOUGU_ERABI:
        return SYS
    try:
        import erabu
        return SYS + "\n\n" + erabu.oshie(kaku=not KIMERU)
    except Exception:
        return SYS


def _build_prompt(text: str, history: list, memory: "Memory") -> str:
    """過去の会話 + 記憶から引いた関連事項を混ぜたプロンプトを作る。"""
    lines = []

    # (a) 覚えている事実
    if memory is not None:
        f = memory.facts()
        if f:
            lines.append("【覚えていること】")
            for k, v in list(f.items())[:6]:
                lines.append("  %s: %s" % (k, str(v)[:80]))

    # (b) 直近の会話に出てこない、関連する過去の発言
    kanren = []
    if memory is not None:
        recent_ids = {h.get("id") for h in (history or []) if isinstance(h, dict)}
        hits = memory.recall(text, n=2, exclude_ids=recent_ids)
        hits = [h for h in hits if h["score"] >= 0.05]
        if hits:
            kanren.append("【関連する昔の発言】")
            for h in hits:
                kanren.append("  %s: %s" % (_ROLE_JA.get(h["role"], h["role"]), str(h["text"])[:160]))

    # (c) 直近の会話
    kaiwa = []
    if history:
        kaiwa.append("【直近の会話】")
        # ★ 手元の頭脳は読み込みが 15〜30 t/s。頼み文 1トークンが 0.05秒。長いほど遅い。
        for h in history[-4:]:
            if isinstance(h, dict):
                kaiwa.append("  %s: %s" % (_ROLE_JA.get(h.get("role"), "相手"),
                                           str(h.get("text", ""))[:200]))
            else:
                kaiwa.append("  %s" % (h,))

    # ★ 2026-09-17: 並びは「会話が先・関連は後」。手元の頭脳は前と同じ頭の部分だけ使い回す（--cache-reuse は
    #   前へずれた行しか拾えない）。毎回変わる「関連する昔の発言」が会話の前にあると、会話が毎回読み直しになる。
    #   操作の輪で 537→97 トークンになったのと同じ理屈。KERNEL_ZATSUDAN_NARABI=関連が先 で前の形。
    if NARABI == "関連が先":
        lines += kanren + kaiwa
    else:
        lines += kaiwa + kanren

    lines.append("【今の発言】" + text)
    lines.append("これに短く返事して。")
    return "\n".join(lines)


def reply(text: str, history: list, memory: "Memory") -> dict:
    """雑談への返事を作る。teachers.ask_panel で先生団に同時に聞き、速い方を採る。

    戻り値: {"text": str, "teacher": str, "ms": int, "error": str|None}
    """
    t0 = time.monotonic()
    out = {"text": "", "teacher": "", "ms": 0, "error": None}

    try:
        from teachers import ask_panel
    except Exception as e:
        out["error"] = "先生に接続できません: %s" % e
        out["ms"] = int((time.monotonic() - t0) * 1000)
        return out

    prompt = _build_prompt(text, history, memory)

    # ★ 2026-09-18: 先に **1トークンで** 道具か雑談かを決める（kimeru・Jev の System One の真似）。
    #   道具なら 返事を書かせずに済む（2〜3秒 → 1秒）。自信が線より低ければ 今まで通り 雑談の返事へ。
    #   材料が文から取れない用件（探す・書く・送る…）だけ、頭脳に「言い方」を 1行書かせる。
    if DOUGU_ERABI and KIMERU:
        try:
            import erabu
            k = erabu.kimeru_dougu(sys_dougu(), prompt)
            out["決め"] = k
            name = k.get("用件")
            if name and k.get("自信", 0.0) >= erabu.SEN:
                slots = erabu.zairyou(name, text)
                if slots is not None:
                    out.update(text="", teacher="kimeru", ms=int((time.monotonic() - t0) * 1000), 道具=(name, slots))
                    return out
                rows = ask_panel(prompt + "\n\n" + (erabu.IIKATA_TOI % name), system=sys_dougu(), timeout=90, fukasa=0)
                for r in rows:
                    if not r.get("error") and (r.get("text") or "").strip():
                        hit = erabu.yomu(r["text"], name)
                        if hit and hit[0]:
                            out.update(text=r["text"].strip(), teacher="kimeru+" + r["teacher"],
                                       ms=int((time.monotonic() - t0) * 1000), 道具=hit)
                            return out
                        break
                # 言い方が作れなかった → 雑談の返事へ（下）
        except Exception as e:
            out["決め"] = {"error": "%s: %s" % (type(e).__name__, e)}

    try:
        # ★ 2026-09-12: 手元の頭脳に聞くようになったので、雲の上向けの 20秒では足りない。
        #   深さは「おまかせ」（短い雑談は深さ0、多段の問いだけ深く）。画面は流しながら受け、止められる。
        #   ★ 深さは **相手の言葉** で決める。組み立てた prompt（履歴入り）で決めると長さで毎回「深く」になる。
        import teachers as _T
        fukasa = _T.fukasa_miru(text)
        _T.mado_hyouji(True)
        try:
            rows = ask_panel(prompt, system=sys_dougu(), timeout=180, fukasa=fukasa)
        finally:
            _T.mado_hyouji(False)
    except Exception as e:
        out["error"] = "相談に失敗: %s" % e
        out["ms"] = int((time.monotonic() - t0) * 1000)
        return out

    # ask_panel は「速く返った順」。最初に成功したものを採用する。
    for r in rows:
        if not r.get("error") and (r.get("text") or "").strip():
            out["text"] = r["text"].strip()
            out["teacher"] = r["teacher"]
            out["ms"] = int((time.monotonic() - t0) * 1000)
            if DOUGU_ERABI:
                try:
                    import erabu
                    out["道具"] = erabu.yomu(out["text"])      # (用件, 材料) ／ ("", 言い方)=当たらず ／ None
                except Exception:
                    out["道具"] = None
            return out

    errs = [("%s: %s" % (r.get("teacher"), r.get("error"))) for r in rows]
    out["error"] = "先生が全滅: " + ("; ".join(errs) if errs else "応答なし")
    out["ms"] = int((time.monotonic() - t0) * 1000)
    return out


def ask_teacher_classify(text: str) -> str:
    """classify が「あいまい」を返した時だけ使う、先生への分類相談。

    ここは遅い(0.5〜0.7秒)。呼び出し側が必要なときだけ呼ぶこと。
    失敗したら安全側("雑談")に倒す。
    """
    try:
        from teachers import ask_panel
    except Exception:
        return "雑談"
    prompt = ("次の発言はPCへの操作命令か、ただの雑談か。"
              "「命令」か「雑談」のどちらか一語だけを出力せよ。\n発言: " + text)
    try:
        rows = ask_panel(prompt, system="一語だけ出力する。", timeout=15, fukasa=0)
    except Exception:
        return "雑談"
    for r in rows:
        t = (r.get("text") or "")
        if not r.get("error"):
            if "命令" in t:
                return "命令"
            if "雑談" in t:
                return "雑談"
    return "雑談"


# ============================================================
# (4) スロット取り -- kernel.py があれば使い、無ければ素通し
# ============================================================

def draw_slots(text: str) -> dict:
    """kernel.draw_cards() でスロットを埋める。kernel が読めなければ空辞書。"""
    try:
        import kernel
        try:
            kernel.load_learned()
        except Exception:
            pass
        return kernel.draw_cards(text) or {}
    except Exception:
        return {}


# ============================================================
# (5) CLI
# ============================================================

def _show_mem(mem: Memory) -> None:
    f = mem.facts()
    print("--- 覚えている事実 (%d 件) ---" % len(f))
    for k, v in f.items():
        print("  %s = %s" % (k, v))
    rows = mem.recent(20)
    print("--- 直近の会話 (%d 件) ---" % len(rows))
    for r in rows:
        print("  [%d] %-9s %s" % (r["id"], r["role"], r["text"]))


def main(argv: list) -> int:
    db = DEFAULT_DB
    if len(argv) > 1:
        db = argv[1]
    mem = Memory(db)
    print("chat.py -- 会話層  (記憶: %s)" % db)
    print("  :quit で終了 / :mem で記憶を表示")

    while True:
        try:
            line = input("\nあなた> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in (":quit", ":q", ":exit"):
            break
        if line == ":mem":
            _show_mem(mem)
            continue

        t0 = time.monotonic()
        slots = draw_slots(line)
        kind = classify(line, slots)
        ms = int((time.monotonic() - t0) * 1000)
        print("  [分類] %s  (%dms, スロット=%s)" % (kind, ms, slots or "なし"))

        if kind == "あいまい":
            kind = ask_teacher_classify(line)
            print("  [分類] 先生に確認 → %s" % kind)

        mem.add("user", line)

        if kind == "命令":
            print("  これは命令です（kernel側で処理）")
            continue

        r = reply(line, mem.recent(8), mem)
        if r["error"]:
            print("  [エラー] %s" % r["error"])
        else:
            print("AI> %s" % r["text"])
            print("  (%s / %dms)" % (r["teacher"], r["ms"]))
            mem.add("assistant", r["text"])

    mem.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
