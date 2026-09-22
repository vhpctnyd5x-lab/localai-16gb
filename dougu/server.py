#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py -- 画面（アプリ）のための、うちうちのサーバー

  ターミナルを開かずに使えるようにするための入口。
  自分のパソコンの中だけで動き、外からはつながらない。

  【決めごと】
   ・127.0.0.1（自分自身）にだけ耳を貸す。外のネットワークには出さない
   ・起動のたびに合言葉（token）を作り、それが無い要求は断る
   ・ファイルを配るのは、このフォルダの中の決まった1枚だけ
"""
import os, sys, io, json, time, threading, secrets, contextlib, mimetypes
import signal
import http.server
import socketserver
import subprocess
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import kernel
import chat
import settings as S
import main as cli
import chats
import feedback

TOKEN = secrets.token_urlsafe(24)

# 画面が生きている合図。窓を閉じたら来なくなるので、自分から終わる。
# 出しっぱなしのサーバーが残らないようにするため
LAST_PING = [time.time()]
# ★ 手元のモデルの畳み方（2026-09-16・「安い」）。使われずに MODERU_IDLE 秒たったら 11GB を返す。
#   16GB の機械で 11GB を握ったままだと「パソコンは悪くないのにずっと重い」（実際に起きた）。
#   次の頼みで moderu_youi が起こし直す（内蔵から 10〜20秒＋最初の読み込み）。
#   環境変数 KERNEL_MODERU_IDLE（秒）。0 で畳まない。
MODERU_IDLE = int(os.environ.get("KERNEL_MODERU_IDLE", str(15 * 60)) or 0)
_TSUKATTA = [time.time()]      # 手元のモデルを最後に使った時
_TSUKAICHUU = [0]              # いま手元のモデルを使っている頼みの数（0 のときだけ畳む）
_TATANDA = [False]             # 使われずに畳んだか（画面に「休止中」と出すため）

# 秒。この間 合図が無ければ店じまい。
#
# 前は 40 秒だった。それだと「たまに起動できない（開いていたのに死んでいる）」
# が起きる。原因は Chrome の仕組みで、
# 窓が裏に回ると setInterval が「1分に1回」まで間引かれる。
# 4秒ごとに合図を送っているつもりでも、実際は60秒に1回になり、
# 40秒の見張りに先に殺されていた。
# 間引きの上限（60秒）より、じゅうぶん長くしておく。
IDLE_LIMIT = 240

# 窓が生きている限り畳まないので、万一の取りこぼし用に **絶対の上限** を置く。
# 12 時間 合図が来なければ、窓が居ようと畳む（8.6GB を握ったまま何日も残らないため）。
HARD_LIMIT = 12 * 3600
PORT = 0                      # 空いている番号を OS に選んでもらう

# 画面と本体をつなぐ、ひとつぶんの状態
CTX = {"設定": None, "記憶": None, "会話": [], "kernel": kernel}
_LOCK = threading.Lock()


# ---------------------------------------------------------------- 手元のモデル

_MODELS = os.path.join(os.path.expanduser("~"), "LocalAI_mirror", "models")
# ★ 2026-09-08: LocalAI改良 フォルダが LocalAI/ の下へ移動して、ここが
#   行き止まりになっていた（＝手元の先生が立ち上がらない）。
#   二度と同じことで壊れないよう、**心当たりを順に見て、在るものを使う**。
#   おまけに llama-server は自分の道連れ（.dylib）の場所を焼き込んで持っている
#   ので、見つけた bin を DYLD_LIBRARY_PATH にも入れてやる必要がある。
def _SPEC_OPTS():
    """投機デコードの指定。既定は ngram-simple + size-m 16（2026-09-22 実測: x64/ARM/Mac の3台で
    正解率同じ・8〜12% 速い。m8・n8m16・ngram-mod・KV q8_0 は得なし）。"""
    v = os.environ.get("KERNEL_SPEC", "ngram-simple").strip()
    if not v or v == "none":
        return []
    o = ["--spec-type", v]
    if v == "ngram-simple":
        o += ["--spec-ngram-simple-size-m", os.environ.get("KERNEL_SPEC_M", "16")]
    return o


def _sagasu_lsrv():
    ne = [
        os.environ.get("KERNEL_LLAMA_SERVER") or "",
        # ★ 2026-09-16: 内蔵の写しを先に。外部SSDは日に何度も切れ、切れた瞬間に
        #   SSD上の bin/.dylib を持つ llama-server ごと落ちる（今日それで測定が止まった）。
        os.path.expanduser("~/LocalAI_mirror/llama-latest/build/bin/llama-server"),
        # Qwen3.5 / MTP / 最新のKVキャッシュ機能を使う新ビルド。
        # 無ければ従来の実験用ビルドへ戻る。
        "/Volumes/Mac Windows/LocalAI/llama-latest/build/bin/llama-server",
        "/Volumes/Mac Windows/LocalAI/LocalAI改良/tools/llama.cpp/build/bin/llama-server",
        "/Volumes/Mac Windows/LocalAI改良/tools/llama.cpp/build/bin/llama-server",
        os.path.expanduser("~/LocalAI_mirror/tools/llama.cpp/build/bin/llama-server"),
    ]
    for m in ne:
        if m and os.path.exists(m):
            return m
    return ne[1]          # 無くても道は返す（起動時に分かるエラーにする）

_LSRV = _sagasu_lsrv()
_LBIN = os.path.dirname(_LSRV)
_SUP = os.path.join(os.path.expanduser("~"), "Library",
                    "Application Support", "kernel-ai")

# ★ 2026-09-06 実測（本家 llama-server・温度0・思考オフ・日本語ものさし12問）
#   モデル              サイズ    pp     tg    点/12   落ちた問題
#   30B 混合96          8.0GB   44.9   13.4   10.0   山の県, 文字数
#   80B 枝刈り352      19.0GB   20.2    5.0    8.5   山の県, 文字数, 逆さ読み, Python
#   80B 素             27.2GB   12.6    3.4    9.5   山の県, 逆さ読み, Python
#   → **30B が いちばん小さく いちばん速く いちばん点が高い。**
#     引き継ぎ書は「80B は PPL が18%良い＝賢い」としていたが、
#     **能力の物差しでは 30B が勝つ**。PPL は能力を予測しない（3度目の実証）。
#
# ★ 2026-09-10 実測で -t 12 -np 1 が最速（30B-A3B素・ngram-simple 込み）:
#     -t 6  -np 1  7.04 t/s / 最初まで 5.08秒
#     -t 10 -np 1  8.46 t/s / 3.95秒
#     -t 12 -np 1  9.04 t/s / 3.22秒  ★これ（-t 6 比 +28%）
#     -t 12 -np 2  8.44 t/s / 3.42秒
#   物理6コアだが **論理12スレッド全部使う方が速い**。一般論の逆。必ず実測すること。
#   1人で使うなら -np 1。並列は総量を上げても 待ち時間では損。
# 選べる手元のモデル。**同時には1つしか載らない**（16GB しかないので）。
#   並びは 2026-09-06 に本家 llama-server で実測して決めた:
#     30B: -np2 -c8192 KV量子化なし  → pp 44.9 / tg 13.9 / KV 約800MB
#          （前の -np4 -c16384 q8_0KV は pp 32.3。**読解が +39%**）
#     80B: 29GB あって RAM に収まらない。OS のページキャッシュ任せで動く。
#          文脈を欲張ると収まらなくなるので小さくする。1本だけ。
MODERU = {
    # ★ 2026-09-11 モデルを1本にした。研究の結論:
    #   ・枝刈り版(REAP96)に得の証拠なし（難問 93.3% vs 素 96.7%, p=0.289 / 読解 76.2% vs 80.0%）
    #   ・Qwen3.5-35B は 3.3倍おそく賢さの差なし / 80B系はRAMに収まらず遅い
    #   → 雑談・推論・読解・道具、全部これ1本。設定は 2026-09-10/11 実測の最速
    #     （-t 12 / -np 1 / -dev none / KV f16 / 投機 ngram-simple は _SPEC_OPTS が足す）
    "local:main": {
        "名": "手元 30B-A3B（11.3GB・これ1本）",
        "file": os.path.join(_MODELS, "Qwen3-30B-A3B-Q2_K.gguf"),
        # ★ -ub 256: 読み込みを256トークンずつに区切る。「止める」がその区切りで効く（既定2048だと
        #   1回の読み込みが終わるまで止まらず、実測で20〜30秒待たされた）。処理速度の損は2%（実測）。
        # ★ --reasoning-format none: 考えの札（<think>）を llama-server に解釈させない。
        #   既定(auto)だと、Qwen3 が札を崩して書いたときに **サーバーが 500 を返す**
        #   （"The model produced output that does not match the expected …"）。
        #   2026-09-13 の操作の試験では、これで 1手ぶん 80〜100秒を何度も捨てていた。
        #   none なら 崩れた札も ただの文として届き、こちらの _yomu が JSON を拾える。
        # ★ 2026-09-16 読み込み（prompt eval）で選び直した（dougu/hakaru_yomi.py・約1000トークン・3回の中央値）:
        #     今まで（KV q8_0）                      17.3 t/s   次の手 537トークン 31秒
        #     -dev none（AMD GPU を触らせない）      28.7 t/s              18.5秒
        #     ＋ KV 量子化なし（f16）          ★     39.8 t/s              14秒   ← これ。2.3倍
        #     ＋ -ub 512 / -tb 6 / 投機なし / mlock   40〜42     差は誤差。-ub は「止める」の効きで 256 のまま
        #     ＋ --cache-reuse 64                    33.9（遅くなる・読み直しも減らない）
        #     -ngl 8（Metal・AMD 5300M）             14.2 で落ちた
        #   操作の輪は 1手の 97% が読み込み。-ngl 0 でも Metal の機器が居ると読み込みに割り込んで遅くなる。
        #   KV q8_0 は 2026-09-06 にも pp -28% と出ていた（tg のために残っていた）。RAM は +0.4GB。
        #   --cache-reuse 16: 頼み文の途中で行が消えて 後ろが前へずれたとき、ずらして使い回す。
        #   操作の輪（画面が先・初めて見えた順）と組んで 次の手の読み直し 537 → 97トークン（同日実測）。
        #   -fa off: 深い文脈（4.6k）での書き出しが 6.4 → 8.4 t/s（+31%・hakaru_kaki --nagai 2026-09-17）。
        #   浅い文脈の書き出し（16 t/s）と読み込み（40 t/s）は変わらない。2026-09-04 の実験38 と同じ向き。
        #   書き出し（浅い文脈・2026-09-16）: ngram-simple 16 t/s ／ 投機なし 14 ／ -t 6・8・12 は差なし ／ KV q8_0 17.7（読み込みで大損）
        "opts": ["-t", "6", "-ngl", "0", "-dev", "none", "-c", "8192", "-np", "1", "-cb", "-ub", "256",
                 "--cache-reuse", "16", "-fa", "off", "--reasoning-format", "none"],
    },
    # ★ GLM-4.7-Flash は 2026-09-11 に落選: Mac で 6.8 t/s（30B素の6割）、6段 70% vs 100%
}

# いま載っているもの。プロセスを立てたのが誰かも覚える
_IMA = {"key": None, "pid": None}
# 再入可能にしてある。moderu_youi が錠を持ったまま _temoto_okosu を呼ぶため。
_MODERU_LOCK = threading.RLock()


def moderu_ichiran():
    """画面に並べるための一覧。ファイルが無いものは出さない"""
    out = []
    for k, v in MODERU.items():
        if os.path.exists(v["file"]):
            out.append({"key": k, "名": v["名"],
                        "GB": round(os.path.getsize(v["file"]) / 1e9, 2),
                        "いま": k == _IMA["key"]})
    return out


def _pid_ikiteru(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _ikiteru():
    import urllib.request
    try:
        with urllib.request.urlopen(TEMOTO_URL + "/health", timeout=2) as f:
            f.read(64)
        return True
    except Exception:
        return False


def _notteru():
    """いま 8080 に **実際に載っているモデルのファイル名**を返す。分からなければ ""。

    ★ なぜ /health では足りないか。
      /health は「誰かが生きている」しか言わない。**誰かは 別人でもよい。**
      実際に起きること:
        ① カーネルが REAP96 を立てる → _IMA["key"] = "30B"
        ② 別の仕事（物差しの測定など）が それを終わらせて 8B を 8080 に立てる
        ③ カーネルは _IMA の記憶と /health だけを見るので **8B を REAP96 だと思う**
      → **別のモデルの答えを、頼んだモデルの答えとして出す。**
        これは測る側でも同じ罠を3回踏んだ（同じ数字が出続けた）。
        記憶ではなく **載っているものの名前** を見ること。
    """
    import urllib.request
    try:
        with urllib.request.urlopen(TEMOTO_URL + "/props", timeout=3) as f:
            return os.path.basename(json.loads(f.read()).get("model_path", "") or "")
    except Exception:
        return ""


def _sore_ga_notteru(key):
    """頼んだモデルが 本当に載っているか。名前で突き合わせる。"""
    v = MODERU.get(key)
    if not v:
        return False
    n = _notteru()
    return bool(n) and n == os.path.basename(v["file"])


def _matsu(byou=240):
    """立ち上がるまで待つ。80B は 29GB あるので長い"""
    for _ in range(byou):
        if _ikiteru():
            return True
        time.sleep(1)
    return False


def _temoto_shimau():
    """アプリが立ち上げた手元のモデルを終わらせる。

    **ここを入れないと 8.6GB（80B なら 29GB）を握ったまま居残る。**
    この機械は 16GB しかないので、居残られると
    「パソコン自体は悪くないのに、ずっと重い」状態になる（実際に起きた）。

    自分で立ち上げたときだけ終わらせる。
    人が別に立ち上げたもの（pid ファイルが無い）には手を出さない。
    """
    pf = os.path.join(_SUP, "llama.pid")
    try:
        with open(pf) as f:
            pid = int((f.read() or "0").strip())
    except Exception:
        return
    # ★ 0 や 負の数を os.kill に渡してはいけない。
    #   os.kill(0, 15) は **自分のプロセスグループ全体**に SIGTERM を送る＝自殺。
    #   pid ファイルが空（書きかけで死んだ等）だと int("" or "0") が 0 になり、
    #   カーネルのサーバが起動直後に黙って死んだ。traceback も出ないので
    #   原因が見えず、「アプリが起動しない」になる（2026-09-06 に実際に起きた）。
    if pid <= 1:
        try:
            os.remove(pf)
        except Exception:
            pass
        return
    # ★ 終わったことを確かめてから pid ファイルを消すこと。
    #   前は SIGTERM を投げただけで消していた。llama-server はすぐには
    #   終わらないので、**pid ファイルだけ消えてモデルは 8.6GB を握ったまま
    #   居残った**（2026-09-06 に実際に起きた）。こうなると誰も止められない。
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        pid = None
    except Exception:
        pass
    if pid is not None:
        for _ in range(30):              # 最大 9 秒待つ
            try:
                # ★ 2026-09-17: 自分の子なら ここで回収する。回収しないと 終わった後も **ゾンビ** として
                #   os.kill(pid, 0) が通り続け、毎回 9秒待って 力ずくの 9 を送っていた（畳むのに 12秒）。
                try:
                    if os.waitpid(pid, os.WNOHANG)[0] == pid:
                        pid = None
                        break
                except ChildProcessError:
                    pass
                os.kill(pid, 0)
            except Exception:
                pid = None
                break
            time.sleep(0.3)
    if pid is not None:                  # まだ居るなら 力ずくで
        try:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        except Exception:
            pass
    try:
        os.remove(pf)
    except Exception:
        pass
    _IMA["key"] = None
    _IMA["pid"] = None


def _temoto_okosu(key="local:main"):
    """手元のモデルを起こす。すでに違うものが載っていれば **入れ替える**。

    ★ なぜ **ここ**（python 側）でやるのか
      カーネル.app は 外付けSSD の中身を読む許可を macOS から
      もらっていない。ランチャ（シェル）から読むと、こうなる:

          grep: settings.json: Operation not permitted

      ディレクトリの一覧は見えるのに、中身だけ読めない。
      いま動いているのは、python3 が別に許可を持っているからで、
      **たまたま**でしかない。だから SSD を触る仕事は
      許可を持っている python 側に集める。
      （根本的には システム設定 > プライバシーとセキュリティ >
        ファイルとフォルダ で カーネル.app に許可を与えるのが正しい）

    ★ 入れ替えは **必ず 前を終わらせてから**。
      16GB しかないので、2本立てると両方が遅くなって使えない（実測ずみ）。
    """
    v = MODERU.get(key)
    if not v:
        return "知らないモデルです: %s" % key
    with _MODERU_LOCK:
        if _sore_ga_notteru(key):
            _IMA["key"] = key          # 記憶がずれていたら ここで直す
            return "すでに動いています（%s）" % v["名"]
        # ★ 2026-09-17: 同じモデルを **読み込み中**（立てたが /health がまだ）なら、殺して立て直さない。
        #   前は 温め（_atatameru）が立てた直後に最初の頼みが来ると、頼みの側が「別のが居る」と見て
        #   読み込み中のものを殺し、もう1本立て直していた（実測: pid が 2つ、15秒の無駄）。待てばよい。
        if _IMA["key"] == key and _IMA["pid"] and _pid_ikiteru(_IMA["pid"]):
            return "立ち上げ中です（%s）" % v["名"]
        if _IMA["key"] is not None or _ikiteru():
            _temoto_shimau()
            for _ in range(20):                # 番号が空くまで
                if not _ikiteru():
                    break
                time.sleep(0.5)
        if not os.path.exists(_LSRV):
            return "llama-server が見つかりません: %s" % _LSRV
        if not os.path.exists(v["file"]):
            return "モデルが見つかりません: %s" % v["file"]
        try:
            os.makedirs(_SUP, exist_ok=True)
            logf = open(os.path.join(_SUP, "llama.log"), "ab")
            pr = subprocess.Popen(
                # ★ 2026-09-10: 投機デコード（n-gram）を足す。**出力は1文字も変わらず
                #   +9%**（30B-A3B素・温度0・壁時計で実測。5通り比べた結果 これが最良）。
                #   下書きモデル方式は 17%遅かったので使わない。RAM は 0.35GB 増だけ。
                #   合わない場合は 環境変数 KERNEL_SPEC=none で外せる。
                [_LSRV, "-m", v["file"]] + v["opts"] + _SPEC_OPTS()
                + ["--host", "127.0.0.1",
                   "--port", TEMOTO_URL.rsplit(":", 1)[-1]],
                stdout=logf, stderr=logf, stdin=subprocess.DEVNULL,
                start_new_session=True,
                # ★ llama-server は道連れの .dylib の在り処を焼き込んで持っている。
                #   フォルダが動くと そこが行き止まりになるので、いま居る場所を教える。
                env=dict(os.environ, DYLD_LIBRARY_PATH=_LBIN))
            with open(os.path.join(_SUP, "llama.pid"), "w") as f:
                f.write(str(pr.pid))
            _IMA["key"], _IMA["pid"] = key, pr.pid
        except Exception as e:
            return "立ち上げられません: %s" % e
    return "立ち上げました（%s） pid=%d" % (v["名"], pr.pid)


def moderu_youi(key):
    """聞く前に、そのモデルが載っていることを確かめる。
    戻り値: (よいか, ひとこと)

    ★ 入れ替えの **待ちも 錠の中** でやること。
      前は _temoto_okosu だけが錠を取り、そのあとの「読み込み待ち」が
      錠の外だった。すると こうなる:
        ① 80B を頼む → 立ち上げ開始 → 待ちに入る（このとき錠を放している）
        ② すぐ 30B を頼む → **80B を殺して** 30B を立てる
        ③ ①の待ちは「立った」と見えるので、30B に 80B のつもりで聞く
      → **別のモデルの答えを、頼んだモデルの答えとして出す。**
        モデルの実力を見たい人にとっては 致命的な嘘になる。

      あわせて、成否の判定を「返ってきた文の文字列一致」から
      「_IMA['key'] が頼んだものになっているか」に変えた。
      文言を直すたびに壊れる作りだった。
    """
    if key not in MODERU:
        return True, ""                     # local: 以外（groq など）は素通し
    with _MODERU_LOCK:
        if _sore_ga_notteru(key):
            _IMA["key"] = key          # 記憶がずれていたら ここで直す
            return True, ""
        msg = _temoto_okosu(key)
        if _IMA["key"] != key:               # 立ち上げに失敗している
            return False, msg
        if not _matsu(240):
            return False, "読み込みが終わりませんでした（%s）" % MODERU[key]["名"]
        return True, "%s に入れ替えました" % MODERU[key]["名"]


@contextlib.contextmanager
def _temoto_tsukau():
    """頼みの間、手元のモデルを畳ませない。先生が手元なら、畳んだ後の起こし直しもここで。"""
    _TSUKAICHUU[0] += 1
    _TSUKATTA[0] = time.time()
    try:
        try:
            if any(str(t).startswith("local:") for t in (CTX.get("設定") or {}).get("先生", [])):
                ok, msg = moderu_youi("local:main")
                if not ok:
                    sys.stderr.write("手元のモデル: %s\n" % msg)
                _TATANDA[0] = False
        except Exception:
            pass
        yield
    finally:
        _TSUKAICHUU[0] -= 1
        _TSUKATTA[0] = time.time()


def _temoto_tatamu_nara():
    """見張りから 5秒ごとに呼ばれる。使われずに MODERU_IDLE 秒たっていれば畳む。"""
    if not MODERU_IDLE or _TSUKAICHUU[0] or _IMA["pid"] is None:
        return
    if time.time() - _TSUKATTA[0] < MODERU_IDLE:
        return
    with _MODERU_LOCK:
        if _TSUKAICHUU[0] or _IMA["pid"] is None:
            return
        sys.stderr.write("手元のモデル: %d分 使われていないので畳みます（次の頼みで起こし直す）\n" % (MODERU_IDLE // 60))
        _temoto_shimau()
        _TATANDA[0] = True


def _atatameru():
    """手元の先生の「読んだところ」を、先に温めておく。

    llama.cpp のサーバーは、前と同じ頭の部分を覚えていて読み直さない。
    consult の頼み文は 選べる値・部品表で 900〜1700 トークンあり、
    **一番最初の1回だけ 30〜40 秒かかる**（2回目からは 4〜5 秒）。
    その1回を、画面が出るまでの裏で済ませてしまう。

    失敗しても何もしない。ここで転んで本体が止まっては本末転倒。
    """
    try:
        import consult
        if not any(str(t).startswith("local:") for t in CTX["設定"].get("先生", [])):
            return
        sys.stderr.write("手元のモデル: %s\n" % _temoto_okosu())
        # 読み込みに 15 秒ほどかかる。立つのを待ってから温める
        import urllib.request
        for _ in range(60):
            try:
                with urllib.request.urlopen(TEMOTO_URL + "/health", timeout=2) as f:
                    f.read(64)
                break
            except Exception:
                time.sleep(1)
        # ★ 2026-09-12 直し: 前は consult を2回まわして温めていたが、深さ0でも JSON を 439 トークン
        #   書き続け（実測 125秒）、その間 最初の返事が待たされた。温めるのは **雑談の頼み文の頭**を
        #   1トークンだけ（cache_prompt に載る）。これで最初の返事が速くなる。
        import teachers as _T
        try:
            katachi = _T._katachi([{"role": "system", "content": chat.SYS},
                                   {"role": "user", "content": "こんにちは"}], False, 20)
            _T._post("/completion", {"prompt": katachi, "n_predict": 1, "cache_prompt": True,
                                     "temperature": 0}, 120)
        except Exception:
            pass
    except Exception:
        pass


def boot():
    cfg = S.load()
    CTX["設定"] = cfg
    S._apply(cfg, CTX)
    CTX["記憶"] = chat.Memory(cli.MEMDB)
    threading.Thread(target=_atatameru, daemon=True).start()
    return cfg


def _run_capturing(fn, *a, **kw):
    """本体は画面に文字を出す作りなので、それを横取りして文字列で受け取る"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            fn(*a, **kw)
        except Exception as e:
            print(f"\n  こまりました： {type(e).__name__}: {e}")
    return buf.getvalue()


class _Nagashi(io.TextIOBase):
    """print された文字を **1行ずつ** 画面へ流しつつ、あとで _split_answer にかけるため全部も持つ。"""
    def __init__(self, q):
        self.q, self.buf, self.all = q, "", []
    def write(self, t):
        self.buf += t
        while "\n" in self.buf:
            ln, self.buf = self.buf.split("\n", 1)
            self.all.append(ln)
            if ln.strip():
                self.q.put({"経過": ln})
        return len(t)
    def flush(self):
        pass
    def getvalue(self):
        return "\n".join(self.all + ([self.buf] if self.buf else []))


def handle_text_nagashi(text, q, tomeru):
    """handle_text と同じ道筋を、途中経過と文字を q に流しながら通る。
    ★ 画面の「止める」= tomeru。teachers は次のかたまりで接続を切る。"""
    import teachers as _T
    with _LOCK, _temoto_tsukau():
        t0 = time.time()
        cfg = CTX["設定"]
        keep = cfg.get("考える様子")
        cfg["考える様子"] = True
        w = _Nagashi(q)
        # 考えている間は字数だけ、答えは文字そのものを流す
        kazu = [0]
        def on_token(piece, kangae=False):
            if kangae:
                kazu[0] += len(piece)
                if kazu[0] // 40 != (kazu[0] - len(piece)) // 40:   # 40字ごとに1回だけ
                    q.put({"考え": kazu[0]})
            else:
                q.put({"文字": piece})
        _T.mado_settei(on_token=on_token, tomeru=tomeru)
        # ★ 承認: 道具が「押す・打つ」の前に聞いてくる → 画面に {"承認": …} を流し、/approve を待つ（shounin.py）
        import shounin as _shounin
        _shounin.TOIKAKE = lambda obj: q.put(obj)
        try:
            with contextlib.redirect_stdout(w):
                try:
                    if S.is_command(text):
                        S.run(text, CTX); kind = "コマンド"
                    elif cfg.get("先生と直接"):
                        import sensei as _sensei
                        _sensei.chokusetsu(text, CTX); kind = "先生"
                    else:
                        cli.route(text, CTX); kind = "ふつう"
                except Exception as e:
                    print(f"\n  こまりました： {type(e).__name__}: {e}"); kind = "ふつう"
        finally:
            _T.mado_settei(None, None)
            _shounin.TOIKAKE = None
            cfg["考える様子"] = keep
        ans, trace = _split_answer(w.getvalue())
        if tomeru.is_set():
            ans = (ans.rstrip() + "\n（ここで止めた）") if ans.strip() else "（ここで止めた）"
        return {"出力": ans, "経過": trace, "種類": kind,
                "ミリ秒": round((time.time() - t0) * 1000),
                "モード": CTX["設定"]["モード"], "止めた": tomeru.is_set()}


def _split_answer(out):
    """まるごとの出力を「答え」と「経過」に分ける。

    画面の吹き出しには答えだけを出し、
    途中で何をしたかは右のターミナルに流す。
    毎回スクショを撮らなくても、何をしたか後から読めるようにするため。
    """
    lines = out.rstrip("\n").split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith("答え：") or ln.startswith("  【"):
            # 「答え：」の直前の区切り線は、答え側には要らない
            head = lines[i:]
            return "\n".join(head).rstrip(), out.rstrip("\n")
    return out.rstrip("\n"), out.rstrip("\n")


def handle_text(text):
    """入力ひとつを処理して、画面に出す中身を返す"""
    with _LOCK, _temoto_tsukau():
        t0 = time.time()
        # 画面から使うときは、途中経過も必ず取る。
        # 吹き出しには出さず、右のターミナルに流すため
        cfg = CTX["設定"]
        keep = cfg.get("考える様子")
        cfg["考える様子"] = True
        try:
            if S.is_command(text):
                out = _run_capturing(S.run, text, CTX)
                kind = "コマンド"
            elif cfg.get("先生と直接"):
                # カーネルの仕組みを一切通さず、先生とそのまま話す。
                # 先生そのものの力を見たいときのための道（/sensei ずっと）。
                import sensei as _sensei
                out = _run_capturing(_sensei.chokusetsu, text, CTX)
                kind = "先生"
            else:
                out = _run_capturing(cli.route, text, CTX)
                kind = "ふつう"
        finally:
            cfg["考える様子"] = keep
        ans, trace = _split_answer(out)
        return {
            "出力": ans,
            "経過": trace,
            "種類": kind,
            "ミリ秒": round((time.time() - t0) * 1000),
            "モード": CTX["設定"]["モード"],
        }


def state():
    """画面の右下などに出す、今の様子"""
    cfg = CTX["設定"]
    bg = {}
    try:
        import background
        st = background._read(background.STATE, {})
        pid = st.get("pid")
        alive = False
        if pid:
            try:
                os.kill(pid, 0); alive = True
            except OSError:
                alive = False
        bg = {"動作中": alive, "調べた": st.get("調べた", 0),
              "候補": len(background._read(background.CAND, {}))}
    except Exception:
        pass
    kernel.load_learned(); kernel.load_grown()

    # ものおぼえの入れもの（コンテキスト）が、いまどれくらい埋まっているか。
    # 目で見えないと「なぜ急に忘れたのか」が分からないので、割合で見せる
    limit = int(cfg.get("会話の長さ", 8)) * 2
    used = len(CTX["会話"])
    chars = sum(len(str(x.get("文", x)) if isinstance(x, dict) else str(x))
                for x in CTX["会話"])

    nv = None
    try:
        import nvidia
        nv = {"呼び方": nvidia.how(), "モデル": list(nvidia.ALIASES)}
    except Exception:
        pass

    temoto = _temoto_genki()

    return {
        "モード": cfg["モード"],
        "考える様子": cfg["考える様子"],
        "先生": cfg["先生"][0] if cfg["先生"] else "",
        "札": len(kernel.SEED),
        "部品": len(kernel.PARTS),
        "裏の係": bg,
        "会話数": used // 2,
        "いれもの": {"使った": used, "上限": limit,
                     "割合": round(min(1.0, used / limit) * 100) if limit else 0,
                     "文字数": chars},
        "設定": {k: cfg.get(k) for k in S.DEFAULTS},
        "設定の説明": dict(S._HELP),
        "じっくり": bool(cfg.get("じっくり")),
        "NVIDIA": nv,
        "手元のモデル": temoto,
        "手元の一覧": moderu_ichiran(),
        "手元のいま": _IMA["key"],
        "手元は休止中": bool(_TATANDA[0]),
        "会話": chats.listing(),
        "組": chats.groups(),
        # 削除は SQLite の soft delete。通常の一覧からは消すが、あとで戻せる。
        "ゴミ箱": [item for item in chats.listing(include_archived=True, include_deleted=True)
                   if item.get("削除日時") is not None],
        "いま": CTX.get("会話id"),
    }


# 手元のモデル（llama-server）が動いているか。
#   /state は 4 秒ごとに呼ばれる。毎回たたくと、止まっているとき
#   待ち時間ぶん画面が固まる。**15 秒だけ覚えておく。**
_TEMOTO = {"時": 0.0, "答": None}
TEMOTO_URL = os.environ.get("KERNEL_LOCAL_URL", "http://127.0.0.1:8080")


def _temoto_genki():
    now = time.time()
    if now - _TEMOTO["時"] < 15:
        return _TEMOTO["答"]
    import urllib.request
    try:
        with urllib.request.urlopen(TEMOTO_URL + "/health", timeout=1.5) as f:
            f.read(64)
        ans = True
    except Exception:
        ans = False
    _TEMOTO["時"], _TEMOTO["答"] = now, ans
    return ans


def _allowed(path):
    """Finder で開いてよい場所か。

    どこでも開けるようにすると、画面に細工されたときに
    システムの奥まで案内してしまう。触ってよい範囲だけに限る
    """
    if not path:
        return False
    ap = os.path.abspath(os.path.expanduser(path))
    home = os.path.expanduser("~")
    ok = [os.path.join(home, "Desktop"), os.path.join(home, "Downloads"),
          os.path.join(home, "Documents"),
          os.path.join(home, "Library", "Application Support", "kernel-ai"),
          HERE]
    return any(ap == d or ap.startswith(d + os.sep) for d in ok) \
        and os.path.exists(ap)


def _artifacts(limit=40):
    """カーネルが作ったもの（いまのところ HTML）のいちらん"""
    out = []
    home = os.path.expanduser("~")
    for d in (os.path.join(home, "Desktop"), os.path.join(home, "Downloads"),
              os.path.join(kernel.SANDBOX, "Desktop")):
        if not os.path.isdir(d):
            continue
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.name.lower().endswith((".html", ".htm")):
                        st = e.stat()
                        out.append({"名": e.name, "パス": e.path,
                                    "大きさ": st.st_size, "とき": st.st_mtime})
        except OSError:
            pass
    out.sort(key=lambda x: -x["とき"])
    return out[:limit]


# ------------------------------------------------------------------
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "kernel-ui"

    def log_message(self, *a):
        pass                        # 画面を汚さない

    # --- 入口の確認 ---
    def _ok_host(self):
        """Host が自分自身であることを確かめる。

        これが無いと「DNSリバインディング」に弱い。
        悪意のあるサイトが、自分のドメインを 127.0.0.1 に向け直すことで、
        ブラウザに「同じ場所だ」と思わせてこのサーバーを叩ける。
        Host を見れば、そういう要求は名前が違うので弾ける。
        """
        h = (self.headers.get("Host") or "").split(":")[0].strip("[]")
        return h in ("127.0.0.1", "localhost", "::1", "")

    def _ok_origin(self):
        """よそのページから叩かれていないことを確かめる"""
        o = self.headers.get("Origin")
        if not o:
            return True                 # 同じページからの読み込みには付かない
        try:
            u = urllib.parse.urlparse(o)
        except Exception:
            return False
        return u.hostname in ("127.0.0.1", "localhost", "::1")

    def _ok_token(self):
        """合言葉を、きっちり同じかどうかで確かめる。

        前は `"t=" + TOKEN in クエリ` という文字列探しだった。
        それだと ?foo=t=合言葉 のような形でも通ってしまう。
        きちんと分解して、t の値そのものと比べる。
        """
        if not self._ok_host() or not self._ok_origin():
            return False
        want = self.headers.get("X-Token", "")
        if secrets.compare_digest(want, TOKEN):
            return True
        # 窓を再読み込みしたとき、住所からは合言葉が消えている。
        # そのために、最初の読み込みで渡した札(cookie)も見る
        ck = self.headers.get("Cookie") or ""
        for part in ck.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "kt" and secrets.compare_digest(v, TOKEN):
                return True
        q = self.path.split("?", 1)[1] if "?" in self.path else ""
        got = urllib.parse.parse_qs(q).get("t", [""])[0]
        return secrets.compare_digest(got, TOKEN)

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if getattr(self, "_cookie", None):
            self.send_header("Set-Cookie", self._cookie)
            self._cookie = None
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            if not self._ok_token():
                return self._send(403, "合言葉が違います", "text/plain; charset=utf-8")
            p = os.path.join(HERE, "ui.html")
            with open(p, "rb") as f:
                html = f.read().replace(b"__TOKEN__", TOKEN.encode())
            # 札を渡しておく。SameSite=Strict なので、よそのページからは送られない
            self._cookie = (f"kt={TOKEN}; Path=/; SameSite=Strict; HttpOnly; "
                            f"Max-Age=86400")
            return self._send(200, html, "text/html; charset=utf-8")
        if path == "/ping":
            if not self._ok_token():
                return self._json({"error": "合言葉が違います"}, 403)
            LAST_PING[0] = time.time()
            return self._json({"ok": True})
        if path == "/state":
            if not self._ok_token():
                return self._json({"error": "合言葉が違います"}, 403)
            LAST_PING[0] = time.time()
            return self._json(state())
        if path == "/commands":
            if not self._ok_token():
                return self._json({"error": "合言葉が違います"}, 403)
            return self._json([{"名": c, "説明": d} for c, d in S.COMMANDS])
        if path == "/transcript":
            if not self._ok_token():
                return self._json({"error": "合言葉が違います"}, 403)
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1]
                                      if "?" in self.path else "")
            return self._json({"文": chats.transcript(q.get("id", [""])[0])})
        if path == "/feedbacks":
            if not self._ok_token():
                return self._json({"error": "合言葉が違います"}, 403)
            return self._json({"一覧": feedback.listing(),
                               "置き場": feedback.folder()})
        if path == "/artifacts":
            if not self._ok_token():
                return self._json({"error": "合言葉が違います"}, 403)
            return self._json({"一覧": _artifacts()})
        self._send(404, "ありません", "text/plain; charset=utf-8")

    def do_POST(self):
        if not self._ok_token():
            return self._json({"error": "合言葉が違います"}, 403)
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > 4_000_000:
            return self._json({"error": "大きすぎます"}, 413)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            return self._json({"error": "読めませんでした"}, 400)
        path = self.path.split("?")[0]

        if path == "/pick":
            # ★ ファイル・フォルダを **画面で選ぶ**（Mac の標準の窓）。場所を文字で打たせない。
            import subprocess as _sp
            nani = body.get("何") or "file"
            js = ('POSIX path of (choose folder with prompt "フォルダを選んでください")' if nani == "folder"
                  else 'POSIX path of (choose file with prompt "ファイルを選んでください" with multiple selections allowed)')
            try:
                out = _sp.run(["osascript", "-e", js], capture_output=True, text=True, timeout=300).stdout.strip()
            except Exception as e:
                return self._json({"error": str(e)})
            paths = [x.strip() for x in out.split(", ")] if out else []
            return self._json({"道": paths})

        if path == "/approve":
            # 画面の「する／全部／やめる」を道具に返す
            import shounin as _shounin
            ok = _shounin.kotaeru(str(body.get("id") or ""), str(body.get("答え") or "やめる"))
            return self._json({"ok": ok})

        if path == "/ask/stream":
            # ★ 流しながら返す（1行1JSON）。先に user の分を会話に残すので、途中で止めても履歴に残る。
            text = (body.get("text") or "").strip()
            if not text:
                return self._json({"error": "からっぽです"}, 400)
            import queue as _queue
            cid = body.get("会話") or CTX.get("会話id")
            try:
                if not cid or not chats.load(cid):
                    cid = chats.create()["id"]
                CTX["会話id"] = cid
                chats.add_turn(cid, "user", text)
            except Exception:
                cid = None
            q = _queue.Queue()
            tomeru = threading.Event()
            def worker():
                try:
                    res = handle_text_nagashi(text, q, tomeru)
                except Exception as e:
                    res = {"出力": f"エラー： {type(e).__name__}: {e}", "経過": "", "ミリ秒": 0,
                           "モード": CTX["設定"].get("モード", ""), "止めた": tomeru.is_set()}
                res["会話"] = cid
                try:
                    if cid:
                        chats.add_turn(cid, "bot", res["出力"], res.get("経過", ""), res.get("ミリ秒", 0))
                except Exception:
                    pass
                q.put({"完了": res})
            threading.Thread(target=worker, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            def okuru(obj):
                self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            import select as _select, socket as _socket
            def kireta():
                """画面が接続を切ったか（何も送っていない間も気づけるように、覗いて確かめる）"""
                try:
                    r, _, _ = _select.select([self.connection], [], [], 0)
                    if r:
                        return self.connection.recv(1, _socket.MSG_PEEK) == b""
                except (OSError, ValueError):
                    return True
                return False
            try:
                okuru({"会話": cid})
                while True:
                    try:
                        m = q.get(timeout=0.5)
                    except _queue.Empty:
                        if kireta():
                            print("  [stream] 画面が切った → 止める", file=sys.stderr, flush=True)
                            raise BrokenPipeError
                        continue
                    okuru(m)
                    if "完了" in m:
                        break
            except (BrokenPipeError, ConnectionResetError, OSError):
                # 画面が「止める」を押した（接続を切った）。生成も **いますぐ** 止める。
                try:
                    import teachers as _T
                    _T.mado_tomeru()
                    print("  [stream] mado_tomeru 済 ima=%r" % (_T._MADO.ima,), file=sys.stderr, flush=True)
                except Exception as e:
                    print("  [stream] mado_tomeru 失敗 %r" % e, file=sys.stderr, flush=True)
                    tomeru.set()
            return

        if path == "/ask":
            text = (body.get("text") or "").strip()
            if not text:
                return self._json({"error": "からっぽです"}, 400)
            res = handle_text(text)
            # 会話に残す（分けて持っているほうへ）
            cid = body.get("会話") or CTX.get("会話id")
            try:
                if not cid or not chats.load(cid):
                    cid = chats.create()["id"]
                CTX["会話id"] = cid
                chats.add_turn(cid, "user", text)
                chats.add_turn(cid, "bot", res["出力"], res.get("経過", ""),
                               res.get("ミリ秒", 0))
                res["会話"] = cid
            except Exception:
                pass
            return self._json(res)

        # ---- 組（会話のまとまり）----
        if path == "/chat/group":
            cid, name = body.get("会話"), body.get("組", "")
            if not cid:
                return self._json({"error": "会話が指定されていません"}, 400)
            g = chats.set_group(cid, name)
            if g is None:
                return self._json({"error": "その会話がありません"}, 404)
            return self._json({"ok": True, "組": g, "一覧": chats.groups()})
        if path == "/group/rename":
            n = chats.rename_group(body.get("前", ""), body.get("後", ""))
            return self._json({"ok": True, "変えた件数": n, "一覧": chats.groups()})

        # ---- NVIDIA の鍵を入れ直す ----
        # 画面の設定から貼れるようにする。ターミナルを開かなくていいように。
        # 大事な作法: 形・一覧・推論の3つを実際に通してからでないと保存しない。
        # 通らない鍵で上書きすると「入れ直したらもっと悪くなった」が起きるため。
        if path == "/nvidia/key":
            k = (body.get("鍵") or "").strip()
            if not k:
                return self._json({"error": "鍵がからっぽです"}, 400)
            try:
                import nvkey
                ok, msg = nvkey.shindan(k)
            except Exception as e:
                return self._json({"error": f"調べられませんでした: {e}"}, 500)
            if not ok:
                # 保存しない。いまの設定はそのまま
                return self._json({"error": msg, "保存した": False}, 400)
            try:
                nvkey.save(k)
            except Exception as e:
                return self._json({"error": f"保存できませんでした: {e}"}, 500)
            return self._json({"ok": True, "保存した": True, "説明": msg})

        # ---- NVIDIA に直接きく ----
        # カーネル本体は通さない。外のモデルへそのまま投げて、返事をそのまま返す。
        # 会話への残し方は /ask と揃えてあるので、画面側は同じように描ける。
        # ---- 手元のモデル（や Groq）に じかに聞く ----
        if path == "/sensei":
            text = (body.get("text") or "").strip()
            if not text:
                return self._json({"error": "からっぽです"}, 400)
            who = (body.get("model") or "").strip() or "local:main"
            t0 = time.time()
            # 選ばれたモデルが載っていなければ、ここで入れ替える。
            # 16GB しかないので **同時には1つだけ**。入れ替えは 15〜60 秒かかる。
            ok, shirase = moderu_youi(who)
            if not ok:
                return self._json({"error": shirase}, 503)
            import sensei
            # 80B は 6 t/s しか出ない。待ち時間を分けておく
            byou = 600 if who == "local:80b" else 300
            rireki = CTX.setdefault("先生の話", [])
            with _temoto_tsukau():
                r = sensei.kiku(text, CTX["設定"], rireki, timeout=byou, sensei=who)
            if r.get("error"):
                return self._json({"error": r["error"]}, 502)
            rireki.append({"who": "user", "文": text})
            rireki.append({"who": "bot", "文": r["答え"]})
            del rireki[:-40]
            namae = MODERU.get(who, {}).get("名", who)
            keika = "%s に じかにきいた（カーネルは通っていない）" % namae
            if shirase:
                keika = shirase + " ／ " + keika
            res = {"出力": r["答え"], "経過": keika,
                   "ミリ秒": round((time.time() - t0) * 1000),
                   "モード": namae}
            cid = body.get("会話") or CTX.get("会話id")
            try:
                if not cid or not chats.load(cid):
                    cid = chats.create()["id"]
                CTX["会話id"] = cid
                chats.add_turn(cid, "user", text)
                chats.add_turn(cid, "bot", res["出力"], res["経過"], res["ミリ秒"])
                res["会話"] = cid
            except Exception:
                pass
            return self._json(res)

        # ---- 読み取り専用エージェント ----
        # 変更・削除・シェル実行は渡さず、agent.py の許可済み道具だけを
        # 最大数回まわす。既存の /ask（確認つき操作）とは別の入口にする。
        if path == "/agent":
            text = (body.get("text") or "").strip()
            if not text:
                return self._json({"error": "からっぽです"}, 400)
            who = (body.get("model") or "local:35b").strip()
            if who != "local:35b":
                return self._json({"error": "読み取りエージェントは今は local:35b だけです"}, 400)
            try:
                steps = max(1, min(4, int(body.get("steps", 3))))
            except (TypeError, ValueError):
                steps = 3
            ok, shirase = moderu_youi(who)
            if not ok:
                return self._json({"error": shirase}, 503)
            t0 = time.time()
            try:
                import agent
                r = agent.run(text, TEMOTO_URL, model="qwen3.5-35b",
                              max_steps=steps, timeout=240)
            except Exception as e:
                return self._json({"error": "%s: %s" % (type(e).__name__, e)}, 502)
            if r.get("error") and not r.get("text"):
                return self._json({"error": r["error"], "道具": r.get("tools", [])}, 502)
            namae = MODERU[who]["名"]
            trace = r.get("tools") or []
            keika = "%s の読み取り専用エージェント" % namae
            if shirase:
                keika = shirase + " ／ " + keika
            if trace:
                keika += "（道具 %d 回）" % len(trace)
            res = {"出力": r.get("text", ""), "経過": keika,
                   "ミリ秒": round((time.time() - t0) * 1000),
                   "モード": namae, "道具": trace, "段数": r.get("steps", 0)}
            cid = body.get("会話") or CTX.get("会話id")
            try:
                if not cid or not chats.load(cid):
                    cid = chats.create()["id"]
                CTX["会話id"] = cid
                chats.add_turn(cid, "user", text)
                chats.add_turn(cid, "bot", res["出力"], res["経過"], res["ミリ秒"])
                res["会話"] = cid
            except Exception:
                pass
            return self._json(res)

        # ---- AIカーソル（観測 → 提案 → 承認 → 実行）----
        # 既存の /agent は読み取り専用のままにしておく。PC操作は別入口に
        # 分け、Qwen3.5 が提案した一操作を画面側で明示的に許可してから
        # computer.py が eyes.py / hands.py を呼ぶ。
        if path == "/computer/observe":
            try:
                import computer
                seen = computer.observe(include_image=bool(body.get("画像", False)),
                                        fast=bool(body.get("速く", True)))
            except Exception as e:
                return self._json({"error": str(e)}, 502)
            return self._json(seen)

        if path == "/computer/plan":
            text = (body.get("text") or "").strip()
            if not text:
                return self._json({"error": "からっぽです"}, 400)
            who = (body.get("model") or "local:35b").strip()
            if who != "local:35b":
                return self._json({"error": "AIカーソルは今は local:35b だけです"}, 400)
            try:
                steps = max(1, min(6, int(body.get("steps", 4))))
            except (TypeError, ValueError):
                steps = 4
            ok, shirase = moderu_youi(who)
            if not ok:
                return self._json({"error": shirase}, 503)
            t0 = time.time()
            try:
                import computer_agent
                r = computer_agent.run(text, TEMOTO_URL, model="qwen3.5-35b",
                                       max_steps=steps, timeout=300)
            except Exception as e:
                return self._json({"error": "%s: %s" % (type(e).__name__, e)}, 502)
            if r.get("error") and not r.get("text"):
                return self._json({"error": r["error"], "道具": r.get("tools", [])}, 502)
            namae = MODERU[who]["名"]
            keika = "%s の AIカーソル計画（操作は承認待ち）" % namae
            if shirase:
                keika = shirase + " ／ " + keika
            trace = r.get("tools") or []
            if trace:
                keika += "（道具 %d 回）" % len(trace)
            res = {"出力": r.get("text", ""), "経過": keika,
                   "ミリ秒": round((time.time() - t0) * 1000),
                   "モード": namae, "道具": trace, "段数": r.get("steps", 0),
                   "操作": r.get("pending")}
            cid = body.get("会話") or CTX.get("会話id")
            try:
                if not cid or not chats.load(cid):
                    cid = chats.create()["id"]
                CTX["会話id"] = cid
                chats.add_turn(cid, "user", text)
                chats.add_turn(cid, "bot", res["出力"], res["経過"], res["ミリ秒"])
                res["会話"] = cid
            except Exception:
                pass
            return self._json(res)

        if path == "/computer/approve":
            ident = str(body.get("id") or "").strip()
            if not ident:
                return self._json({"error": "承認する操作がありません"}, 400)
            try:
                import computer
                done = computer.execute(ident)
            except KeyError as e:
                return self._json({"error": str(e)}, 409)
            except Exception as e:
                return self._json({"error": str(e)}, 502)
            return self._json({"ok": True, "出力": "操作を実行しました。",
                               "経過": "AIカーソル: ユーザー承認済み",
                               "操作": done.get("action"),
                               "アプリ": done.get("active_app"),
                               "カーソル": done.get("cursor")})

        if path == "/computer/cancel":
            ident = str(body.get("id") or "").strip()
            if not ident:
                return self._json({"error": "取り消す操作がありません"}, 400)
            try:
                import computer
                cancelled = computer.cancel(ident)
            except Exception as e:
                return self._json({"error": str(e)}, 500)
            return self._json({"ok": cancelled,
                               "出力": "操作を取り消しました。" if cancelled else "操作は期限切れです。"})

        if path == "/nvidia":
            text = (body.get("text") or "").strip()
            if not text:
                return self._json({"error": "からっぽです"}, 400)
            model = (body.get("model") or "").strip() or None
            t0 = time.time()
            try:
                import nvidia
                ans = nvidia.ask(text, model=model or nvidia.DEFAULT)
            except Exception as e:
                # nvidia.py は理由を日本語で投げてくる。そのまま見せる
                return self._json({"error": str(e)}, 502)
            res = {"出力": ans,
                   "経過": f"NVIDIA {model or 'fast'} に直接きいた（カーネルは通っていない）",
                   "ミリ秒": round((time.time() - t0) * 1000),
                   "モード": "NVIDIA " + (model or "fast")}
            cid = body.get("会話") or CTX.get("会話id")
            try:
                if not cid or not chats.load(cid):
                    cid = chats.create()["id"]
                CTX["会話id"] = cid
                chats.add_turn(cid, "user", text)
                chats.add_turn(cid, "bot", res["出力"], res["経過"], res["ミリ秒"])
                res["会話"] = cid
            except Exception:
                pass
            return self._json(res)

        # ---- 会話 ----
        if path == "/chat/new":
            c = chats.create(body.get("題") or "新しい会話")
            CTX["会話id"] = c["id"]
            CTX["会話"] = []
            return self._json({"ok": True, "会話": c["id"]})
        if path == "/chat/open":
            c = chats.load(body.get("id"))
            if not c:
                return self._json({"error": "その会話はありません"}, 404)
            CTX["会話id"] = c["id"]
            # 画面に戻すぶんの流れを、頭の中にも戻す
            CTX["会話"] = [{"役": t["役"], "文": t.get("文", "")}
                           for t in c["やりとり"]][-int(
                               CTX["設定"].get("会話の長さ", 8)) * 2:]
            return self._json({"ok": True, "会話": c})
        if path == "/chat/rename":
            c = chats.rename(body.get("id"), body.get("題"))
            return self._json({"ok": bool(c)})
        if path == "/chat/archive":
            c = chats.archive(body.get("id"), bool(body.get("on", True)))
            return self._json({"ok": bool(c)})
        if path == "/chat/fork":
            c = chats.fork(body.get("id"), body.get("まで"))
            return self._json({"ok": bool(c), "会話": c["id"] if c else None})
        if path == "/chat/delete":
            ok = chats.remove(body.get("id"))
            return self._json({"ok": ok, "取り消せる": ok})
        if path == "/chat/restore":
            return self._json({"ok": chats.restore(body.get("id"))})
        if path == "/chat/purge":
            # ゴミ箱の中のものだけ。画面側で「戻せません」と確かめてから来る
            return self._json({"ok": chats.purge(body.get("id"))})
        if path == "/chat/trash/empty":
            days = body.get("日数")
            n = chats.empty_trash(older_than_days=(float(days) if days not in (None, "") else None))
            return self._json({"ok": True, "件数": n})
        if path == "/chat/matomete":
            n = chats.matomete(body.get("ids") or [], str(body.get("何") or ""), str(body.get("組") or ""))
            return self._json({"ok": True, "件数": n})

        # ---- 設定 ----
        if path == "/settings":
            k, v = body.get("鍵"), body.get("値")
            if k not in S.DEFAULTS:
                return self._json({"error": "知らない設定です"}, 400)
            CTX["設定"][k] = v
            if k not in S.NEVER_SAVE:
                S.save(CTX["設定"])
            S._apply(CTX["設定"], CTX)
            return self._json({"ok": True, "設定": CTX["設定"][k]})

        # ---- 気づいたこと（虫マーク）----
        if path == "/feedback":
            try:
                p2 = feedback.add(body.get("文"), body.get("種類", "不具合"),
                                  {"モード": CTX["設定"]["モード"],
                                   "入力": body.get("入力"),
                                   "出力": body.get("出力"),
                                   "経過": body.get("経過"),
                                   "設定": {k: CTX["設定"].get(k)
                                            for k in S.DEFAULTS}})
            except Exception as e:
                return self._json({"error": str(e)}, 400)
            return self._json({"ok": True, "パス": p2,
                               "置き場": feedback.folder()})

        # ---- macOS のネイティブなファイル選択 ----
        if path == "/pick-file":
            # 画面の JavaScript ではなく、macOS 自身の選択窓を出す。
            # 固定の AppleScript だけを実行し、画面から文字列を差し込まない。
            try:
                picked = subprocess.run(
                    ["osascript", "-e", "POSIX path of (choose file)"],
                    text=True, capture_output=True, timeout=300, check=False,
                )
            except subprocess.TimeoutExpired:
                return self._json({"error": "ファイル選択が時間切れです"}, 408)
            except OSError as e:
                return self._json({"error": f"ファイル選択を開けません: {e}"}, 500)
            if picked.returncode:
                # キャンセル（AppleScript error -128）は失敗扱いにしない。
                return self._json({"ok": False, "キャンセル": True})
            selected = picked.stdout.strip()
            if not selected or not os.path.isfile(selected):
                return self._json({"error": "選んだファイルを確認できません"}, 400)
            return self._json({"ok": True, "パス": selected,
                               "名": os.path.basename(selected)})

        # ---- チャットに貼られたファイルを受け取る ----
        if path == "/upload":
            import base64
            name = os.path.basename(body.get("名") or "")
            b64 = body.get("中身") or ""
            if not name or not b64:
                return self._json({"error": "からっぽです"}, 400)
            # 貼られた物は、本物のフォルダには置かない。
            # 使い捨ての置き場に入れて、そこだけを見る
            room = os.path.join(os.path.expanduser("~"), "Library",
                                "Application Support", "kernel-ai", "はりつけ")
            os.makedirs(room, exist_ok=True)
            try:
                data = base64.b64decode(b64, validate=True)
            except Exception:
                return self._json({"error": "読めない中身です"}, 400)
            if len(data) > 60_000_000:
                return self._json({"error": "大きすぎます（60MB まで）"}, 413)
            # 同じ名前でも上書きしない
            stem, ext = os.path.splitext(name)
            dest = os.path.join(room, name)
            k = 2
            while os.path.exists(dest):
                dest = os.path.join(room, f"{stem} {k}{ext}")
                k += 1
            with open(dest, "wb") as f:
                f.write(data)
            return self._json({"ok": True, "パス": dest,
                               "バイト": len(data), "置き場": room})

        # ---- Finder で開く ----
        if path == "/open":
            t = body.get("パス") or ""
            if not _allowed(t):
                return self._json({"error": "そこは開けません"}, 400)
            # ファイルなら Finder で「見つけて選ぶ」、フォルダならそのまま開く
            argv = ["open"] + (["-R"] if os.path.isfile(t) else []) + [t]
            subprocess.run(argv, check=False)
            return self._json({"ok": True})

        self._json({"error": "ありません"}, 404)


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _mado_iru():
    """カーネルの窓（kernel-window）がまだ生きているか。

    ★ 2026-09-07 追加。「接続が切れました」の本当の原因はここだった。

    それまでの見張りは **画面からの合図（ping）だけ** を見ていた。
    ところが窓（WKWebView）は、裏に回る・隠れる・機械が寝るなどで
    macOS に **止められる**。止まると setInterval も動かないので合図が来ない。
    240 秒すぎると、窓は開いているのにサーバーが自分から店じまいし、
    表に戻った瞬間に「うちうちのサーバーとのつながりが切れました」が出ていた。

    → 合図ではなく **窓そのものの生き死に** を見る。
      窓が生きている限り、合図が来なくても畳まない。

    ★ pgrep -f は「その字を含むだけ」の無関係なプロセスにも当たる（過去に2回事故）。
      ここでは ps の command 行が **アプリの中の kernel-window そのもの**
      であることまで確かめる。
    """
    try:
        out = subprocess.run(
            ["/bin/ps", "-Ao", "command="],
            capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return False        # 数えられないときは「居ない」側に倒す（居残らせない）
    for line in out.splitlines():
        line = line.strip()
        if line.endswith("/MacOS/kernel-window") or "/MacOS/kernel-window " in line:
            return True
    return False


def _watchdog(httpd):
    """窓が閉じたら、静かに終わる。

    畳む条件は **2つそろったとき だけ**:
      ① 窓（kernel-window）が どこにも居ない
      ② 画面からの合図が IDLE_LIMIT 秒 途絶えている
    ①だけでは畳まない（窓を使わず curl で叩いている最中かもしれない）。
    ②だけでも畳まない（窓が裏で止められているだけかもしれない）。★これが今回の直し
    """
    while True:
        time.sleep(5)
        try:
            _temoto_tatamu_nara()
        except Exception:
            pass
        if time.time() - LAST_PING[0] <= IDLE_LIMIT:
            continue
        if _mado_iru() and time.time() - LAST_PING[0] < HARD_LIMIT:
            # 窓は生きている。止められているだけなので、待つ。
            continue
        httpd.shutdown()
        return


def serve():
    boot()
    # 127.0.0.1 のみ。外のネットワークからは見えない
    httpd = Server(("127.0.0.1", PORT), Handler)
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/?t={TOKEN}"
    print(url, flush=True)
    threading.Thread(target=_watchdog, args=(httpd,), daemon=True).start()

    # 外から終わらされたとき（ランチャの入れ替えなど）も、行儀よく畳む。
    # これが無いと finally を通らず、**手元のモデルが 8.6GB を握ったまま残る。**
    # shutdown() は serve_forever と同じ糸から呼ぶと固まるので、別の糸で。
    def _oshimai(signum, frame):
        threading.Thread(target=httpd.shutdown, daemon=True).start()
    try:
        signal.signal(signal.SIGTERM, _oshimai)
        signal.signal(signal.SIGINT, _oshimai)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        _temoto_shimau()


if __name__ == "__main__":
    serve()
