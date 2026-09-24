#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teachers.py -- kernel.py が「行き詰まった時だけ」相談する先生(LLM)モジュール。

設計方針:
  - Python 標準ライブラリのみ。import 時に外部通信も重い初期化も一切しない(起動コストゼロ)。
  - 例外を外に出さない。失敗はすべて result dict の "error" に文字列で入れて返す。
  - API キーには一切触れない(groq.sh が ~/.groq.env から自分で読む)。

先生の指定形式:
  "groq:<model>"    例) groq:openai/gpt-oss-120b
  "ollama:<model>"  例) ollama:qwen3.5:4b     (CPU 推論で非常に遅い。オフライン時のみ)
  "nvidia:<tier>"   例) nvidia:fast           (毎回 macOS の承認ダイアログが出るので既定では呼ばない)
  "local:<label>"   例) local:main            (手元の llama-server。外に一切出ない)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time

# ---------------------------------------------------------------- 定数

# groq.sh の場所(環境変数で差し替え可能)
GROQ_SH = os.environ.get(
    "GROQ_SH", os.path.expanduser("~/.claude/scripts/groq.sh")
)

# ollama のモデル置き場(外付け SSD)
OLLAMA_ENV = {
    "OLLAMA_MODELS": "/Volumes/Mac Windows/LocalAI/ollama-models",
    "OLLAMA_NOPRUNE": "1",
}

# 手元の llama-server（本家 llama.cpp）。OpenAI 互換の口を叩く。
#   ik_llama.cpp の llama-server は連続要求で 12 件目から空を返すので使わない（実測・2026-09-06）。
LOCAL_URL = os.environ.get("KERNEL_LOCAL_URL", "http://127.0.0.1:8080")

# Qwen3 系は **既定で思考する**。「1+1は？」に 86 トークン（うち 73 が思考）を使い、
# 実効速度が 21 t/s → 9.3 t/s まで落ちた（実測・2026-09-06）。
# 手元の機械では思考は高くつくので、既定では切る。
#   切り方は 2 通りあり、どちらも効いた:
#     chat_template_kwargs {"enable_thinking": false}  49 トークン
#     system に "/no_think"                             37 トークン
#   前者はシステムプロンプトを汚さないので、こちらを採る。
# 思考させたいときは先生名に "+think" を付ける: local:main+think
LOCAL_THINK = os.environ.get("KERNEL_LOCAL_THINK", "") not in ("", "0", "false")

# ══════════════════════════════════════════════════════════════════
#  考える深さ（エフォート）  ── 2026-09-07 追加
# ══════════════════════════════════════════════════════════════════
#
#  【なぜ作ったか】
#    「もっと考えさせたい」は、ふつう **大きいモデルに載せ替える** ことで叶える。
#    ところがこの機械は 16GB しかない。8.6GB のモデルより大きいものは
#    もう入らない。**容量を増やさずに 賢さだけ上げる**必要があった。
#
#  【どうやるか】
#    考える量は **RAM を食わない**。食うのは時間だけ。
#    だから「深さ」は 文脈を伸ばすのではなく **考える手数** で稼ぐ。
#
#      深さ0 さっと   … 思考しない（今までの既定）           1回
#      深さ1 ふつう   … 思考する（上限 256 トークン）        1回
#      深さ2 じっくり … 思考する（上限 1024 トークン）        1回
#      深さ3 とことん … じっくりで下書き → **自分で見直す**   2回
#
#    ★ どの深さでも、1回の呼び出しは 1スロットぶんの文脈（4096）に収まる。
#      深さ3 が長いのは「1回が長い」のではなく「2回やる」から。
#      **こうしておけば、深さを上げても RAM は 1バイトも増えない。**
#      （-c を伸ばして 1回で長く考えさせる手もあるが、KV が増えて入らなくなる。
#        2026-09-06 の実測でも -c16384 は読解が 39% 落ちた。伸ばしてはいけない。）
#
#  【思考の上限をどう効かせているか】
#    llama-server の /v1/chat/completions では、思考だけに上限をかけられない。
#    max_tokens で切ると **考えている途中で終わって答えが1文字も出ない**
#    （実際にこれが起きていた。下の「空応答」の分岐がその名残）。
#    → /apply-template で頼み文の形だけ作らせ、/completion を **2段**に分ける:
#         ①  …assistant\n<think>\n  から  "</think>" が出るまで（上限つき）
#         ②  ①の続きに </think> を **こちらで閉じて**、答えだけ書かせる
#      これで「考えは 256 まで、答えは必ず出る」が成り立つ。
#
#  【使いかた】
#    環境変数     KERNEL_LOCAL_EFFORT=2
#    先生名       local:main+e2      （+e0 〜 +e3）
#    従来どおり   local:main+think   （= +e2 と同じ扱い）
#
FUKASA = {
    0: {"名": "さっと",   "思考": False, "考える上限":    0, "見直し": False},
    1: {"名": "ふつう",   "思考": True,  "考える上限":  256, "見直し": False},
    2: {"名": "じっくり", "思考": True,  "考える上限": 1024, "見直し": False},
    3: {"名": "とことん", "思考": True,  "考える上限": 1024, "見直し": True},
    # ★ 2026-09-12: 場合分け（数え上げ）は 深さ2 より 深さ0 の方が解けた（Q2: 12/32 vs 4/32）。
    #   1024 で思考が途中で切れ、見立てで答えるせいと疑い、上限を4倍にした段を足して測る。
    4: {"名": "ながく",   "思考": True,  "考える上限": 4096, "見直し": False},
}
FUKASA_SAIDAI = max(FUKASA)

# ══════════════════════════════════════════════════════════════════
#  「おまかせ」── 問いを見て、深さを自分で決める
# ══════════════════════════════════════════════════════════════════
#  【なぜ要るか】
#    深さ2は点が高いが、**簡単な問いにも同じだけ時間を使ってしまう。**
#    実測（120問・2ビットのまま）:
#        1段の問い … 深さ0 でも **100.0%**。考えさせるだけ無駄
#        2段の問い … 深さ0 52.5% → 深さ2 100.0%
#        3段の問い … 深さ0 47.5% → 深さ2  95.0%
#    → 1段には使わず、2段以上にだけ使えばよい。
#
#  【どう決めるか】安く、言い回しに寄りかからない2つだけで決める:
#      ① 問いが短い（42字未満）
#      ② 多段をにおわす語が入っていない
#    両方みたせば「一息で出る」とみなして 深さ0。それ以外は 深さ2。
#
#  【机上での確かめ】上の120問に当てはめると:
#      いつも深さ0   66.7%   456秒
#      いつも深さ2   98.3%  1764秒
#      ★おまかせ    98.3%  1328秒 ← **同じ点を 75% の時間で**
#    見立て違い（浅くすべきを深く／深くすべきを浅く）は 0件。
#
#  ★ ただし これは物差しの120問で確かめただけ。
#    ふだんの雑談や指示は形が違うので、**過信しないこと。**
#    迷ったら深い側に倒すよう、しきい値は甘めにしてある。
import re as _re

# ── おまかせの見立て ─────────────────────────────────────────────
# ★ 2026-09-08 に **実測ラベル125件**（kyouzai_G.jsonl。深さ0で解けたか /
#   深さ2で初めて解けたか を実際に測って付けた札）と突き合わせて作り直した。
#
#   前:  語が1つでも当たる or 42字以上 → 考える
#        → 取りこぼし 0件。ただし **簡単な問いの46%を無駄に考えていた**。
#   後:  強い語 / 弱い語3つ / 50字 → 考える
#        → 取りこぼし 0件のまま、無駄が **28%** に減った（簡単な問いが1.6倍速い）。
#
#   ★ 取りこぼし（考えるべきをさっとで答える）は **0 でなければならない**。
#     無駄に考えるのは時間を損するだけだが、取りこぼしは **答を間違える**。
#     線を動かすときは、まずここが 0 のままかを見ること。
#     （60字まで伸ばすと 0→7件 の取りこぼしが出た。50が崖の手前）
#
#   ★ 正直に言っておくべきこと、二つ:
#     (1) この125件は **算数の問題ばかり**（同じ作り手が作った）。
#         ふつうの会話で当たるかは **まだ measured ではない**。
#     (2) 下の「弱い語」の枝は、この125件では **一度も効いていない**
#         （強い語と長さだけで同じ数字が出る）。効くと示せてはいない。
#         それでも残すのは、材料の外——強い語が無くて短い文——での
#         保険だから。**効くと証明されたものとして扱わないこと。**

# 強い語: 1つでも当たれば 手順が要る
_TSUYOI = _re.compile(
    "平均|何曜日|何番目|日後|いくつありますか|それぞれ|全部で|合わせて|"
    "差は|比べ|くらべ|順番|並べ|なぜ|理由|どうやって|手順")
# 弱い語: 1つでは足りない（「おつりは?」は一息で出る）。3つ揃うと手順くさい
_YOWAI = ("%", "パーセント", "おつり", "引きです", "時速", "のこり", "残り",
          "持っていま", "ずつ", "そこから", "引いて", "合計")
_NAGASA = 50

OMAKASE = -1              # 深さの指定として使う番号


def fukasa_miru(toi: str) -> int:
    """問いを見て 深さを決める。上の説明を読むこと。"""
    toi = (toi or "").strip()
    if _TSUYOI.search(toi):
        return 2
    if sum(1 for g in _YOWAI if g in toi) >= 3:
        return 2
    if len(toi) >= _NAGASA:
        return 2
    return 0


# ══════════════════════════════════════════════════════════════════
#  階段 ── 浅く解いて、怪しければ深くする
# ══════════════════════════════════════════════════════════════════
#  ★ なぜ要るか
#    fukasa_miru は **問いの見た目**だけで決めている。125件で取りこぼし0だったが、
#    その125件は算数ばかり。**ふつうの会話で外さない保証は無い。**
#    そこで「浅く解いた答えが信用できるか」を **中身で** 確かめる網をかける。
#
#  ★ 怪しさの見方（外部AIを使わない。無料で完結する）
#    (1) 形式違反 … `答え: X` が取れない → 怪しい
#    (2) 空・異常に長い → 怪しい
#    (3) ★ **同じ問いを2回 浅く解いて、答えが食い違う** → 怪しい
#        これが一番強い。外の研究でいう self-consistency。
#        温度を少し上げて2回引き、同じ答えに落ちるなら その答えは安定している。
#
#  ★ 元が取れるかは 問題の難しさ次第。
#    浅い1回 2.5秒 / 深い1回 32秒（実測・REAP96）。
#    浅く2回で済めば 5秒。**簡単な問いが多いほど得**、難問ばかりなら損。
#    → だから **fukasa_miru が「浅くてよい」と言った時だけ** この網を使う。
_KOTAE_GYOU = _re.compile(r"答え\s*[:：]\s*([^\n]{1,40})")


def _kotae_dake(text: str):
    """出力から 答えの部分だけを取り出す。取れなければ None。"""
    if not text:
        return None
    m = _KOTAE_GYOU.findall(text)
    if m:
        return m[-1].strip().rstrip("。．.")
    t = text.strip()
    return t if 0 < len(t) <= 40 else None


def ayashii(text: str) -> bool:
    """浅く解いた答えが 怪しいか。True なら深くやり直す価値がある。"""
    k = _kotae_dake(text)
    if k is None or not k:
        return True
    if len(text) > 1200:            # 短く答えるはずの場面で書きすぎ
        return True
    return False


def kaidan(label: str, prompt: str, system: str = "", timeout: int = 300,
           asa: int = 0, fuka: int = 2, kakunin: bool = True) -> dict:
    """階段。浅く解き、怪しければ深く解き直す。

    ★ 深さは **引数で渡す**。環境変数を書き換えると、並列で呼んだとき
      片方がもう片方の深さを壊す（2本並列の測定で実際に起きた）。

    戻りに **どう決まったか** を必ず入れる（あとで検証できるように）:
      使った深さ / 浅い試行の回数 / 昇格した理由
    """
    riyuu, kaisuu = "", 0

    def hitokuchi(f):
        return ask_one(label, prompt, system=system, timeout=timeout, fukasa=f)

    if fukasa_miru(prompt) >= fuka:
        r = hitokuchi(fuka)
        r["使った深さ"], r["浅い回数"], r["昇格理由"] = fuka, 0, "問いを見て最初から深く"
        return r

    r1 = hitokuchi(asa); kaisuu = 1
    t1 = (r1.get("text") or "")
    if ayashii(t1):
        riyuu = "浅い答えの形が怪しい"
    elif kakunin:
        r2 = hitokuchi(asa); kaisuu = 2
        if _kotae_dake(t1) != _kotae_dake(r2.get("text") or ""):
            riyuu = "浅く2回引いて答えが食い違った"
    if not riyuu:
        r1["使った深さ"], r1["浅い回数"], r1["昇格理由"] = asa, kaisuu, ""
        return r1

    r = hitokuchi(fuka)
    r["使った深さ"], r["浅い回数"], r["昇格理由"] = fuka, kaisuu, riyuu
    return r


def _fukasa_kitei() -> int:
    """既定の深さ。環境変数 → 従来の KERNEL_LOCAL_THINK の順に見る。"""
    v = os.environ.get("KERNEL_LOCAL_EFFORT", "").strip()
    if v == "-1" or v == "おまかせ":
        return OMAKASE
    if v.isdigit():
        return max(0, min(FUKASA_SAIDAI, int(v)))
    return 2 if LOCAL_THINK else 0

# 既定パネル: Groq の 2 モデルのみ。ollama(遅い)/nvidia(承認ダイアログ)は含めない。
DEFAULT_PANEL = [
    "groq:openai/gpt-oss-120b",
    "groq:openai/gpt-oss-20b",
]

# 参考: 2026-08 時点で確認済みの利用可能モデル
KNOWN_TEACHERS = [
    "groq:openai/gpt-oss-120b",
    "groq:openai/gpt-oss-20b",
    "groq:qwen/qwen3.6-27b",   # <think>...</think> を吐くので除去が必要
    "groq:groq/compound",
    "ollama:qwen3.5:4b",
    "ollama:qwen2.5-coder:3b",
    "nvidia:super",
    "nvidia:fast",
    "nvidia:llama",
    "local:main",              # 手元の llama-server（要 起動）
]

# ---------------------------------------------------------------- テキスト整形

# <think> ... </think>(閉じタグ無しで途切れている場合も含む)
_THINK_RE = re.compile(r"<think\b[^>]*>.*?(?:</think>|\Z)", re.DOTALL | re.IGNORECASE)
# ```json ... ``` などのコードフェンス
_FENCE_RE = re.compile(r"^\s*```[ \t]*[A-Za-z0-9_+-]*[ \t]*\r?\n(.*?)\r?\n?\s*```\s*$", re.DOTALL)

# 端末の制御コード（ESC[49D = カーソルを49文字戻す、ESC[K = 行を消す など）
#
#   `ollama run` は 人が見る端末だと思って、書き直しの指示を混ぜてくる。
#   それを 文字として拾うと、こうなる（実測・2026-08-30）:
#
#       const guess = parseInt(document.getElementById("guess-field").v ESC[49D ESC[K
#       → SyntaxError: missing ) after argument list
#
#   **先生は 正しく書いていた。こちらが 受け取る時に壊していた。**
#   これに気づくまで、手元の先生の数字は 全部 あてにならなかった。
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_ansi(text: str) -> str:
    """端末の制御コードを取り除く。改行とタブは残す。"""
    return _ANSI_RE.sub("", text or "")


def strip_think(text: str) -> str:
    """<think>...</think> ブロックを丸ごと取り除く。"""
    if not text:
        return ""
    return _THINK_RE.sub("", text)


def strip_fences(text: str) -> str:
    """全体を囲っているコードフェンスを剥がす。中身が無ければそのまま返す。"""
    if not text:
        return ""
    m = _FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


def clean_text(text: str) -> str:
    """制御コード除去 + <think> 除去 + フェンス除去 + 前後空白除去。"""
    return strip_fences(strip_think(strip_ansi(text or ""))).strip()


# ---------------------------------------------------------------- JSON 抽出

def extract_json(text: str):
    """テキスト中の「最初の妥当な JSON(オブジェクトまたは配列)」を取り出す。

    前後に余計な文章やフェンスがあっても拾える。取れなければ None。
    """
    if not text:
        return None
    # clean_text と 同じ順で剥がすこと。ここだけ strip_ansi を抜かしていたので、
    # ollama を JSON 用途で使うと 同じ事故（制御コード混入）が起きる状態だった
    s = strip_fences(strip_think(strip_ansi(text)))

    # まず全体がそのまま JSON ならそれを返す
    try:
        v = json.loads(s)
        if isinstance(v, (dict, list)):
            return v
    except Exception:
        pass

    dec = json.JSONDecoder()
    # '{' か '[' の位置を順に試し、raw_decode で最短の妥当な JSON を探す
    for i, ch in enumerate(s):
        if ch not in "{[":
            continue
        try:
            v, _end = dec.raw_decode(s[i:])
        except ValueError:
            continue
        if isinstance(v, (dict, list)):
            return v
    return None


# ---------------------------------------------------------------- 先生ごとのコマンド組み立て

def _build_cmd(teacher: str, prompt: str, system: str):
    """teacher 指定から (argv, env追加) を作る。未知なら ValueError。"""
    if ":" not in teacher:
        raise ValueError("先生の指定形式が不正: %r ('種別:モデル' の形式)" % teacher)
    kind, model = teacher.split(":", 1)
    kind = kind.strip().lower()
    model = model.strip()
    if not model:
        raise ValueError("モデル名が空: %r" % teacher)

    if kind == "groq":
        if not os.path.exists(GROQ_SH):
            raise ValueError("groq.sh が見つからない: %s" % GROQ_SH)
        argv = ["bash", GROQ_SH, "-m", model]
        if system:
            argv += ["-s", system]
        argv.append(prompt)
        return argv, {}

    if kind == "ollama":
        # ollama には system 引数が無いのでプロンプト先頭に埋め込む
        full = ("%s\n\n%s" % (system, prompt)) if system else prompt
        return ["ollama", "run", model, full], dict(OLLAMA_ENV)

    if kind == "nvidia":
        # 実行のたびに macOS の承認ダイアログが出る。明示 opt-in 時のみ。
        full = ("%s\n\n%s" % (system, prompt)) if system else prompt
        return ["nv", "ask", full, "-m", model], {}

    if kind == "local":
        # ここには来ない（_ask_once が HTTP に回す）。来たら設計が壊れている。
        raise ValueError("local: は HTTP で聞く先生です（_ask_local を通ること）")

    raise ValueError("未知の先生種別: %r" % kind)


# ---------------------------------------------------------------- 公開 API

# 「あと 3.675s 待って」のように、待ち時間が本文に書かれていることがある
_WAIT_RE = re.compile(r"try again in ([0-9.]+)\s*s", re.IGNORECASE)


def available() -> list:
    """使えると分かっている先生のいちらん"""
    return list(KNOWN_TEACHERS)


def ask_one(teacher: str, prompt: str, system: str = "", timeout: int = 25,
            retry: int = 2, fukasa: int = None) -> dict:
    if os.environ.get("KERNEL_ASHIATO"):      # 足あと（調べるとき用）
        import sys as _sys, traceback as _tb
        yobi = [f for f in _tb.extract_stack(limit=6)[:-1]]
        print("  [足あと] %s 深さ=%s 頼み文=%d字 system=%r ← %s" % (teacher, fukasa, len(prompt), (system or "")[:24],
              " < ".join("%s:%d" % (os.path.basename(f.filename), f.lineno) for f in yobi[-3:])), file=_sys.stderr, flush=True)
    """先生 1 人に聞く。例外は投げず、必ず result dict を返す。

    混雑（rate limit）で断られたら、言われた秒数だけ待って retry 回まで試す。
    ここを入れる前は、少し続けて話すと先生が全滅して返事が作れなくなった。

    戻り値: {"teacher", "text", "json", "ms", "error"}
    """
    for i in range(retry + 1):
        res = _ask_once(teacher, prompt, system, timeout, fukasa=fukasa)
        err = res.get("error") or ""
        if "rate limit" not in err.lower() or i == retry:
            return res
        m = _WAIT_RE.search(err)
        wait = min(float(m.group(1)) + 0.4, 12.0) if m else 3.0
        time.sleep(wait)
    return res


# ollama の受け口。`ollama run` は 人が見る端末のつもりで書いてくるので使わない
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


def _ask_ollama(model: str, prompt: str, system: str, timeout: int) -> dict:
    """ollama に HTTP で聞く。

    `ollama run` を使っていた頃は、端末の制御コード（ESC[49D など）が
    そのまま本文に混ざって、コードを壊していた（実測・2026-08-30）:

        ...getElementById("guess-field").v ESC[49D ESC[K
        → SyntaxError: missing ) after argument list

    制御コードを 後から消す手も試したが、ESC[49D は「49文字戻る」、
    ESC[K は「行を消す」なので、**消すだけでは 本来消えるはずの字が残る**。
    受け口ごと変えるのが 正しい直しかた。

    実測: 制御コード 0個 ／ 22.8秒（`ollama run` は 47.8秒。読み直しが無い分 速い）
    """
    import json as _json
    import urllib.error
    import urllib.request

    t0 = time.monotonic()
    res = {"teacher": "ollama:" + model, "text": "", "json": None,
           "ms": 0, "error": None}
    full = ("%s\n\n%s" % (system, prompt)) if system else prompt
    body = _json.dumps({"model": model, "prompt": full,
                        "stream": False}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as f:
            out = _json.loads(f.read().decode("utf-8")).get("response", "")
    except urllib.error.URLError as e:
        res["error"] = ("ollama につながりません（`ollama serve` は起きていますか）: %s"
                        % e)
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res
    except Exception as e:
        res["error"] = "%s: %s" % (type(e).__name__, e)
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res

    res["text"] = clean_text(out)
    res["json"] = extract_json(out)
    res["ms"] = int((time.monotonic() - t0) * 1000)
    if not res["text"]:
        res["error"] = "空応答"
    return res


# 手元の先生の実効速度（tg）。max_tokens を timeout から逆算するのに使う。
#   実測 21.1 t/s（llama-bench・tg128）だが、読解ぶんが混ざるので低めに見ておく。
#   ここを高く見積もると、サーバは生成を続けているのに こちらが先に諦めて
#   **スロットを1本 無駄に握らせたまま捨てる**ことになる。低めが安全。
LOCAL_TPS = float(os.environ.get("KERNEL_LOCAL_TPS", "18"))

# 1スロットぶんの文脈は 4096（-c 16384 -np 4）。頼み文のぶんを残して上限を決める。
LOCAL_MAX_TOKENS = int(os.environ.get("KERNEL_LOCAL_MAX_TOKENS", "3500"))


class Tometa(Exception):
    """画面の「止める」で止めた。以後の先生呼び出しは **送る前に** これで抜ける。"""


def _tomeru_ka():
    t = getattr(_MADO, "tomeru", None)      # _MADO は下で定義（呼ばれる時には在る）
    if t is not None and t.is_set():
        raise Tometa("止めた")


def _post(path: str, payload: dict, timeout: int):
    """手元の llama-server に JSON を投げて JSON を受け取る。失敗は例外で返す。"""
    _tomeru_ka()          # ★ 止めた後は、新しい要求を1つも送らない（送ると読み込みぶん CPU を食う）
    import json as _json
    import urllib.request
    req = urllib.request.Request(
        LOCAL_URL.rstrip("/") + path,
        data=_json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return _json.loads(f.read().decode("utf-8"))


def _katachi(msgs: list, think: bool, timeout: int) -> str:
    """会話を、モデルが読む一続きの文字列に直してもらう（/apply-template）。

    自前で <|im_start|> を組み立てると、テンプレートが変わったとき静かにずれる。
    **形はモデル側に作らせる。** ここを横着すると、学習した形と1バイト違って
    LoRA が効かなくなる（前回の教訓）。
    """
    payload = {"messages": msgs}
    if not think:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return _post("/apply-template", payload, timeout)["prompt"]


# ★ 2026-09-12 画面用の「流しながら」と「止める」。
#   ★ 最初は threading.local にしたが、chat.py の ask_panel は先生を **別の糸** で呼ぶので届かなかった。
#     server.py は _LOCK で1件ずつしか流さないので、**プロセス全体で1つ**の置き場でよい。
#     物差し（hakaru.py 等）は別プロセスで何も設定しないので、前と1バイトも変わらない。
#     _MADO.on_token(文字列, 考え中か) … 1かたまり出るたびに呼ばれる（無ければ流さない）
#     _MADO.tomeru                   … threading.Event。立てると次のかたまりで接続を切って止める
class _Mado:
    on_token = None
    tomeru = None
    hyouji = False      # ★ True の間だけ画面へ流す。分類などの内側の呼び出しは流さない
    ima = None          # いま開いている llama-server への接続（止めるときに閉じる）


_MADO = _Mado()


def mado_tomeru():
    """いますぐ止める。合図を立て、開いている接続を **閉じる**。
    ★ 読み込み中（最初の文字が出る前）は かたまりが来ないので合図だけでは止まらない。
      接続を閉じれば llama-server は生成をやめ、CPU が空く。"""
    if _MADO.tomeru is not None:
        _MADO.tomeru.set()
    c = _MADO.ima
    if c is not None:
        try:
            import socket as _sk
            if getattr(c, "sock", None) is not None:
                c.sock.shutdown(_sk.SHUT_RDWR)
            c.close()
        except Exception:
            pass


def mado_settei(on_token=None, tomeru=None):
    """画面側が、この糸で使う「流す先」と「止める合図」を置く。None で解除。"""
    _MADO.on_token = on_token
    _MADO.tomeru = tomeru


def mado_hyouji(on: bool):
    """「これから呼ぶ先生の返事は画面に出すもの」と宣言する（返事を作る所だけが呼ぶ）。"""
    _MADO.hyouji = bool(on)


def _tsuzuki(prompt: str, n_predict: int, timeout: int, stop=None,
             temp: float = 0.0) -> dict:
    """続きを書かせる（/completion）。cache_prompt で前の分を数えなおさせない。"""
    _tomeru_ka()
    on_token = getattr(_MADO, "on_token", None) if getattr(_MADO, "hyouji", False) else None
    tomeru = getattr(_MADO, "tomeru", None)
    payload = {"prompt": prompt, "n_predict": n_predict,
               "temperature": temp, "cache_prompt": True,
               "stream": bool(on_token or tomeru)}
    if stop:
        payload["stop"] = stop
    if not payload["stream"]:
        return _post("/completion", payload, timeout)
    # 流しながら受ける。llama-server は 1行ずつ "data: {...}" を送ってくる。
    # ★ 止めるときは **ソケットごと閉じる**。urllib の response.close() では下の接続が残り、
    #   llama-server が相手の消失に気づかず生成を続けた（実測）。http.client で自前で持つ。
    import json as _json
    import http.client as _hc
    from urllib.parse import urlsplit as _us
    u = _us(LOCAL_URL)
    conn = _hc.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
    _MADO.ima = conn
    content, last = [], {}
    try:
        conn.request("POST", "/completion", body=_json.dumps(payload).encode("utf-8"),
                     headers={"Content-Type": "application/json"})
        f = conn.getresponse()
        while True:
            if tomeru is not None and tomeru.is_set():
                last["stop_type"] = "tometa"
                break
            raw = f.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                d = _json.loads(line[5:].strip())
            except Exception:
                continue
            piece = d.get("content") or ""
            if piece:
                content.append(piece)
                if on_token:
                    try:
                        # stop に </think> があるのは「考えている」段。答えの段と区別して渡す
                        on_token(piece, bool(stop and "</think>" in stop))
                    except Exception:
                        pass
            if d.get("stop"):
                last = d
                break
    except (OSError, _hc.HTTPException) as e:
        if tomeru is not None and tomeru.is_set():
            last["stop_type"] = "tometa"     # こちらが閉じた。正常
        else:
            raise
    finally:
        _MADO.ima = None
        try:
            conn.close()
        except Exception:
            pass
    _MADO.ima = None
    last = dict(last)
    last["content"] = "".join(content)
    return last


def _qwen35_chat(msgs: list, n_predict: int, timeout: int) -> dict:
    """Qwen3.5 の会話口。思考を切った検算用に使う。

    Qwen3.5 は思考を有効にすると、短い ``max_tokens`` を思考だけで使い切り、
    答えを返さないことがある。``/completion`` で途中に ``</think>`` を足す
    方式も、このモデルでは思考を再開してしまう。公式テンプレートに
    ``enable_thinking=false`` を渡した会話口なら、短い答えを安定して返せる。
    """
    payload = {
        "model": "qwen3.5-35b",
        "messages": msgs,
        "temperature": 0.0,
        "max_tokens": n_predict,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    return _post("/v1/chat/completions", payload, timeout)


# 見直しのときの言いつけ。**答えの形は変えさせない**（JSON なら JSON のまま）。
_MINAOSHI = (
    "上は あなた自身の下書きです。\n"
    "もう一度 落ち着いて確かめてください。計算・数え・日付・条件の見落としを"
    "とくに疑うこと。\n"
    "直すところが無ければ 下書きをそのまま出してください。\n"
    "**最終的な答えだけ**を、下書きと同じ形で出してください。"
    "「見直しました」などの前置きは書かないこと。"
)


def _ask_qwen35_review(label: str, prompt: str, system: str, timeout: int,
                       fukasa: int, omakase: bool, 設定: dict, msgs: list,
                       kotae_cap: int) -> dict:
    """Qwen3.5向けの安全な「考える」代替。

    このモデルのネイティブ思考は非常に長く、上限を小さくすると答えが
    出ない。そこで思考オフの初稿を出す。見直しをもう一度自動採用すると、
    正しい計算を壊す例が実測で出たため、ここでは初稿を保持する。
    """
    import urllib.error
    t0 = time.monotonic()
    res = {"teacher": "local:" + label + ("+e%d" % fukasa if fukasa else ""),
           "text": "", "json": None, "ms": 0, "error": None,
           "深さ": fukasa,
           "深さの名": ("おまかせ→" + 設定["名"]) if omakase else 設定["名"],
           "考えた字数": 0, "回数": 0}

    # 深さに応じて、同じ質問を読むときの確認の強さだけ変える。
    # IQ2_Sでは「複数の観点」など指示を増やすほど、かえって算術を
    # 取り違える例が出た。深さのラベルは保ちつつ、安定した一文に固定する。
    check = "回答前に条件と計算を短く確認してください。最終回答だけを返してください。"
    sysmsg = ((system + "\n\n") if system else "") + check
    msgs1 = [{"role": "system", "content": sysmsg},
             {"role": "user", "content": prompt}]

    def ask(ms, left):
        body = _qwen35_chat(ms, kotae_cap, max(10, int(left)))
        choices = body.get("choices") or []
        msg = (choices[0].get("message") or {}) if choices else {}
        text = msg.get("content") or ""
        finish = choices[0].get("finish_reason") if choices else None
        return text, finish

    try:
        out, finish = ask(msgs1, timeout)
        res["回数"] = 1
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        res["error"] = "HTTP %s: %s" % (e.code, detail)
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res
    except urllib.error.URLError as e:
        res["error"] = ("手元の先生につながりません（llama-server は %s で起きていますか）: %s"
                        % (LOCAL_URL, e))
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res
    except Exception as e:
        res["error"] = "%s: %s" % (type(e).__name__, e)
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res

    res["text"] = clean_text(out)
    res["json"] = extract_json(out)
    res["ms"] = int((time.monotonic() - t0) * 1000)
    if not res["text"]:
        res["error"] = "空応答"
    elif finish == "length":
        res["error"] = "途中で切れました（上限 %d トークン）" % kotae_cap
    return res


def _ask_local(label: str, prompt: str, system: str, timeout: int,
                fukasa: int = None) -> dict:
    """手元の llama-server に聞く。**考える深さ（エフォート）つき。**

    Groq との違いで、呼ぶ側が知っておくべきこと:

      ・**遅い。** Groq は 500 t/s 級、こちらは 20 t/s 級。25 秒だと 450 字ぶん。
        長いものを書かせるときは timeout を伸ばすこと（make_page は 90 秒）。
      ・**外に出ない。** 鍵も要らない。混雑（rate limit）も無い。
      ・**同時に 2 本まで**（-np 2 -cb）。
      ・考える深さは 既定 0（＝思考しない）。上の FUKASA を見ること。

    深さの指定のしかた（強い順に勝つ）:
        label が "…+e2"    → 深さ2
        label が "…+think" → 深さ2（昔からの書き方。互換のため残す）
        環境変数 KERNEL_LOCAL_EFFORT / KERNEL_LOCAL_THINK
    """
    import urllib.error

    # ★ 引数で渡された深さを **ここで捨てない**。
    #   前は無条件に None にしていたので、fukasa= を渡しても効かなかった
    #   （並列で環境変数が壊れる問題を直すために引数を足したのに、
    #     その引数が1行目で消えていた。実測で発覚）
    for n in range(FUKASA_SAIDAI + 1):
        if label.endswith("+e%d" % n):
            label, fukasa = label[:-3].strip(), n
            break
    if fukasa is None and label.endswith("+think"):
        label, fukasa = label[:-6].strip(), 2
    if label.endswith("+omakase"):
        label, fukasa = label[:-8].strip(), OMAKASE
    if fukasa is None:
        # ★ 2026-09-10: 深さを **引数で** 受け取れるようにした。
        #   前は環境変数だけだった。**並列で呼ぶと片方がもう片方の深さを上書きする。**
        #   （2本並列で測っていて、浅いはずの呼び出しが深く走っていた。実測で発覚）
        if fukasa is None:
            fukasa = _fukasa_kitei()
    omakase = (fukasa == OMAKASE)
    if omakase:
        fukasa = fukasa_miru(prompt)     # ★ 問いを見てから決める
    設定 = FUKASA[fukasa]

    t0 = time.monotonic()
    res = {"teacher": "local:" + label + ("+e%d" % fukasa if fukasa else ""),
           "text": "", "json": None, "ms": 0, "error": None,
           "深さ": fukasa,
           "深さの名": ("おまかせ→" + 設定["名"]) if omakase else 設定["名"],
           "考えた字数": 0, "回数": 0}

    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})

    # 答えのぶんの上限。待ち時間から逆算する（サーバ側で勝手に止まってもらう）
    kotae_cap = max(256, min(LOCAL_MAX_TOKENS, int(timeout * LOCAL_TPS)))

    # Qwen3.5 は、思考タグを途中で閉じる旧方式と相性が悪い。
    # 深さ1〜3を選んだときだけ、思考オフの短い初稿＋見直しに切り替える。
    # これなら「空応答」や数千トークンの暴走を防ぎつつ、RAMは増えない。
    if label.lower() in ("35b", "qwen35", "qwen3.5") and 設定["思考"]:
        return _ask_qwen35_review(label, prompt, system, timeout, fukasa,
                                   omakase, 設定, msgs, kotae_cap)

    def _hitokuchi(msgs_, nokori: float) -> tuple:
        """1回ぶん（考える → 答える）。(答え, 考えた字数, エラー) を返す。"""
        katachi = _katachi(msgs_, 設定["思考"], min(20, max(5, int(nokori))))
        kangae = ""
        if 設定["思考"]:
            # ★ <think> は こちらから開ける。開けないと、思考するかどうかを
            #   モデルの気分に任せることになり、深さが効かない回が出る。
            katachi = katachi + "<think>\n"
            r = _tsuzuki(katachi, 設定["考える上限"], max(10, int(nokori)),
                         stop=["</think>"])
            kangae = r.get("content") or ""
            # 上限で止まっても、こちらで閉じてしまえば 答えは必ず書ける。
            # ★ ただし **黙って閉じると 答えが暴走する。**（実測）
            #   考えの途中でいきなり </think> が来ると、モデルは
            #   「まだ考えている最中」のつもりで長々と書き続ける。
            #   一言だけ 断りを入れてから閉じる。
            if (r.get("stop_type") or "") != "word":
                kangae += "\n（ここまで。考える時間が尽きたので、いまの見立てで答えを出す）"
            katachi = katachi + kangae + "\n</think>\n\n"
        r2 = _tsuzuki(katachi, kotae_cap, max(10, int(nokori)))
        return (r2.get("content") or ""), len(kangae), r2

    try:
        nokori = timeout
        out, kangae_len, last = _hitokuchi(msgs, nokori)
        res["回数"] = 1
        res["考えた字数"] = kangae_len

        if 設定["見直し"] and out.strip():
            # ★ とことん = 下書きを **自分で** 見直す。
            #   別のモデルを呼ばない（16GB に2つは載らない）。
            nokori = timeout - (time.monotonic() - t0)
            if nokori > 8:
                msgs2 = list(msgs) + [
                    {"role": "assistant", "content": out},
                    {"role": "user", "content": _MINAOSHI}]
                try:
                    out2, k2, _ = _hitokuchi(msgs2, nokori)
                    if out2.strip():
                        out = out2
                        res["回数"] = 2
                        res["考えた字数"] += k2
                except Exception:
                    pass        # 見直しに失敗しても、下書きは返す
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        res["error"] = "HTTP %s: %s" % (e.code, detail)
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res
    except urllib.error.URLError as e:
        res["error"] = ("手元の先生につながりません（llama-server は %s で起きていますか）: %s"
                        % (LOCAL_URL, e))
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res
    except Exception as e:
        res["error"] = "%s: %s" % (type(e).__name__, e)
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res

    res["text"] = clean_text(out)
    res["json"] = extract_json(out)
    res["ms"] = int((time.monotonic() - t0) * 1000)

    if not res["text"]:
        if res["考えた字数"]:
            res["error"] = ("考えている途中で上限(%d トークン)に当たりました"
                            "（深さを下げるか 上限を増やす）" % 設定["考える上限"])
        else:
            res["error"] = "空応答"
    elif (last or {}).get("stop_type") == "limit":
        res["error"] = "途中で切れました（上限 %d トークン）" % kotae_cap

    return res


def _ask_once(teacher: str, prompt: str, system: str = "", timeout: int = 25,
               fukasa: int = None) -> dict:
    t0 = time.monotonic()
    res = {"teacher": teacher, "text": "", "json": None, "ms": 0, "error": None}

    if teacher.startswith("ollama:"):
        return _ask_ollama(teacher.split(":", 1)[1].strip(), prompt, system,
                           timeout)

    if teacher.startswith("local:"):
        return _ask_local(teacher.split(":", 1)[1].strip(), prompt, system,
                          timeout, fukasa=fukasa)

    if teacher.startswith("nvidia:"):
        # ★ 2026-09-18: nvidia.py の HTTP 経路（鍵は ~/.nvidia.env・ダイアログ無し）。無ければ nvidia.ask が nv（承認ダイアログ）に落ちる。
        #   本人「NVIDIA の API をたくさん使って」。無人の物差しでも回るように。
        try:
            import nvidia as _NV
            out = _NV.ask(prompt, model=teacher.split(":", 1)[1].strip(), system=system, timeout=timeout,
                          max_tokens=max(256, min(4096, int(timeout * 40))), temperature=0.0)
            res["text"] = clean_text(out or "")
            res["json"] = extract_json(out or "")
            if not res["text"]:
                res["error"] = "空応答"
        except Exception as e:
            res["error"] = "%s: %s" % (type(e).__name__, e)
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res

    try:
        argv, extra_env = _build_cmd(teacher, prompt, system)
    except Exception as e:
        res["error"] = str(e)
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res

    env = os.environ.copy()
    env.update(extra_env)

    try:
        cp = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            stdin=subprocess.DEVNULL,  # groq.sh の stdin 追記を防ぐ
        )
    except subprocess.TimeoutExpired:
        res["error"] = "timeout (%ss)" % timeout
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res
    except FileNotFoundError as e:
        res["error"] = "コマンドが見つからない: %s" % e
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res
    except Exception as e:
        res["error"] = "%s: %s" % (type(e).__name__, e)
        res["ms"] = int((time.monotonic() - t0) * 1000)
        return res

    out = clean_text(cp.stdout or "")
    res["text"] = out
    res["json"] = extract_json(cp.stdout or "")
    res["ms"] = int((time.monotonic() - t0) * 1000)

    if cp.returncode != 0:
        err = (cp.stderr or "").strip().splitlines()
        res["error"] = "exit=%d: %s" % (cp.returncode, err[-1] if err else "(stderr なし)")
    elif not out:
        res["error"] = "空応答"

    return res


def ask_panel(prompt: str, system: str = "", teachers: list = None,
              timeout: int = 25, fukasa: int = None) -> list:
    """複数の先生に同時に聞く(threading で並列)。速く返った順のリストを返す。
    fukasa は ask_one にそのまま渡す（None なら先生名の +eN か既定）。"""
    panel = list(teachers) if teachers else list(DEFAULT_PANEL)
    results = []
    lock = threading.Lock()

    def worker(name: str):
        r = ask_one(name, prompt, system=system, timeout=timeout, fukasa=fukasa)
        with lock:
            results.append(r)   # 完了順に積むので自然に「速い順」になる

    threads = [threading.Thread(target=worker, args=(t,), daemon=True) for t in panel]
    for th in threads:
        th.start()
    # 1 人が遅くても他の結果は先に積まれている。全体待ちは timeout + 余裕まで。
    deadline = time.monotonic() + timeout + 5
    for th in threads:
        th.join(max(0.0, deadline - time.monotonic()))

    with lock:
        return list(results)


# ---------------------------------------------------------------- 単体テスト用 CLI

def _table(rows: list) -> str:
    """結果リストを簡易表で整形。"""
    lines = []
    head = "%-26s %7s %5s  %s" % ("TEACHER", "ms", "json", "TEXT / ERROR")
    lines.append(head)
    lines.append("-" * max(72, len(head)))
    for r in rows:
        body = r["error"] and ("ERROR: " + r["error"]) or r["text"].replace("\n", " ⏎ ")
        if len(body) > 100:
            body = body[:97] + "..."
        lines.append("%-26s %7d %5s  %s" % (
            r["teacher"][:26], r["ms"], "yes" if r["json"] is not None else "-", body))
    return "\n".join(lines)


def _main(argv: list) -> int:
    args = [a for a in argv[1:] if a != "--"]
    prompt = " ".join(args) if args else (
        "日本の首都はどこ？ 必ず {\"answer\": \"...\", \"confidence\": 0.0〜1.0} "
        "という JSON だけで答えて。"
    )
    print("[panel] %s" % ", ".join(DEFAULT_PANEL))
    print("[prompt] %s\n" % prompt)
    rows = ask_panel(prompt, system="簡潔に答えること。")
    print(_table(rows))
    print()
    for r in rows:
        if r["json"] is not None:
            print("[json] %s -> %s" % (r["teacher"], json.dumps(r["json"], ensure_ascii=False)))
    return 0 if any(r["error"] is None for r in rows) else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
