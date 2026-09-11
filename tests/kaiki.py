#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaiki.py -- 毎回まわす自動検査。**模型もネットも要らない。**

★ なぜ要るか
  この研究では 採点器・問題生成・深さの受け渡し・GGUF検査 で
  **結果に影響する不具合が何度も出た**。手で丁寧に検算しても、
  直すたびに別の所が戻る。ここで機械に見張らせる。

    /usr/local/bin/python3 tests/kaiki.py
"""
import io, json, os, sys, time, threading, http.server

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "monosashi"))

SHIPPAI = []


def miru(na, jouken, kuwashiku=""):
    print(("  ○ " if jouken else "  × ") + na + (("  " + kuwashiku) if kuwashiku else ""))
    if not jouken:
        SHIPPAI.append(na)


# ── 1. 採点器（正例・負例）────────────────────────────────────
def t_saiten():
    print("[1] 採点器")
    import hakaru as H
    hyou = [
        ("答えの行を見る",          {"答": "652", "答の形": "数"}, "式は 300+352\n答え: 652", True),
        ("★途中の数で通さない",     {"答": "652", "答の形": "数"}, "途中で 652 が出る\n答え: 500", False),
        ("形式違反はゆるく拾う",     {"答": "652", "答の形": "数"}, "652 です", True),
        ("小数が読める",            {"答": "22.5", "答の形": "数"}, "答え: 22.5", True),
        ("小数を割らない",          {"答": "22.5", "答の形": "数"}, "答え: 22", False),
        ("曜日は通す",              {"答": "月", "答の形": "語"}, "答え: 月曜日", True),
        ("★語の一部で通さない",     {"答": "パン", "答の形": "語"}, "答え: フライパン", False),
        ("空は×",                  {"答": "3", "答の形": "数"}, "", False),
    ]
    for na, d, o, kitai in hyou:
        miru(na, H._seikai(d, o) == kitai, repr(o[:26]))


# ── 2. 深さの入力検証 ─────────────────────────────────────────
def t_fukasa():
    print("[2] 深さの受け取り")
    import kangaeru_fukasa as K
    r = K.kiku("1+1は?", fukasa=4)
    miru("知らない深さは例外でなく error で返る", isinstance(r, dict) and bool(r.get("error")))
    miru("深さの表は 0..3", sorted(K.FUKASA) == [0, 1, 2, 3])
    miru("深さ0は思考しない", K.FUKASA[0]["思考"] is False)
    miru("深さ2は思考する",   K.FUKASA[2]["思考"] is True)


# ── 3. 総時間の上限（わざと遅いサーバを立てて確かめる）──────────
class _Noroi(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        time.sleep(3)
        ln = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(ln)
        b = json.dumps({"prompt": "x", "content": "y", "stop_type": "limit"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


def t_jikan():
    print("[3] 約束した時間を守るか")
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Noroi)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    import kangaeru_fukasa as K
    moto = K.URL
    K.URL = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        for tmo in (6, 10):
            t0 = time.monotonic()
            K.kiku("1+1は?", fukasa=3, timeout=tmo)   # 深さ3＝見直しもある
            kakatta = time.monotonic() - t0
            # 1回のHTTPが3秒。締切を見ていないと 深さ3で 4回＝12秒超える。
            miru("timeout=%d秒 を超えない" % tmo, kakatta <= tmo + 4,
                 "実測 %.1f秒" % kakatta)
    finally:
        K.URL = moto
        srv.shutdown()


# ── 4. 出所判定（0本で合格にならないか）───────────────────────
def t_kensa():
    print("[4] 出所の判定")
    import kensa as E
    ok, naze = E.hantei(True, True, True, 0)
    miru("★照合0本は合格にしない", ok is False, naze)
    miru("名前が不一致なら不合格", E.hantei(False, True, True, 5)[0] is False)
    miru("語彙が不一致なら不合格", E.hantei(True, False, True, 5)[0] is False)
    miru("バイト不一致なら不合格", E.hantei(True, True, False, 5)[0] is False)
    miru("全部そろえば合格",       E.hantei(True, True, True, 5)[0] is True)


# ── 5. 6段120問が いまも独立検算と合うか ──────────────────────
def t_mondai():
    print("[5] 6段120問の独立検算")
    sys.path.insert(0, os.path.join(ROOT, "monosashi"))
    f = os.path.join(ROOT, "monosashi", "mondai_6dan.jsonl")
    if not os.path.exists(f):
        miru("mondai_6dan.jsonl がある", False)
        return
    import kenzan3 as K3
    d = [json.loads(l) for l in io.open(f, encoding="utf-8") if l.strip()]
    warui = []
    for x in d:
        try:
            v = K3.kenzan(x)
        except Exception as e:
            warui.append((x["id"], repr(e)[:40]))
            continue
        if isinstance(v, K3.Dame) or str(v) != str(x["答"]):
            warui.append((x["id"], v))
    miru("120問", len(d) == 120, "%d問" % len(d))
    miru("食い違い0件", not warui, str(warui[:3]))


# ── 6. GGUF を書き出しても 1バイトも変わらないか（＋メモリを抱えないか）──
def t_gguf():
    print("[6] GGUF の書き出し（小さいモデルで往復）")
    import hashlib, resource, glob
    ko = (glob.glob(os.path.join(ROOT, "..", "data", "models", "*0.6B*.gguf"))
          + glob.glob(os.path.expanduser("~/LocalAI_mirror/models/*0.6B*.gguf")))
    if not ko:
        print("  - 小さいGGUFが無いので飛ばす")
        return
    sys.path.insert(0, os.path.join(ROOT, "lib"))
    from ggufwrite import Copier
    out = os.path.join(os.environ.get("TMPDIR", "/tmp"), "kaiki_round.gguf")
    m0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9
    Copier(ko[0]).write(out, {})
    yama = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9 - m0

    def sha(p_):
        h = hashlib.sha256()
        with open(p_, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()

    ookisa = os.path.getsize(ko[0]) / 1e9
    miru("差し替え無しなら1バイトも変わらない", sha(ko[0]) == sha(out))
    # ★ 中身を全部抱えていると ファイルとほぼ同じだけ RAM を食う
    miru("中身を抱えこまない", yama < ookisa * 0.3,
         "増えたメモリ %.2fGB / ファイル %.2fGB" % (yama, ookisa))
    os.remove(out)


if __name__ == "__main__":
    for f in (t_saiten, t_fukasa, t_jikan, t_kensa, t_mondai, t_gguf):
        try:
            f()
        except Exception as e:
            SHIPPAI.append("%s が落ちた: %r" % (f.__name__, e))
            print("  × %s が落ちた: %r" % (f.__name__, e))
    print()
    if SHIPPAI:
        print("★ しくじり %d 件:" % len(SHIPPAI))
        for x in SHIPPAI:
            print("   -", x)
        sys.exit(1)
    print("★ 全部とおった")
