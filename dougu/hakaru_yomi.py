#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_yomi.py -- 物差し: 手元のモデルの「読み込み」の速さを、起動の指定ごとに測る。

  ★ なぜ（2026-09-14 の実測）
    操作の輪の 1手 82秒のうち **80秒が読み込み**（1028トークン @12.8 t/s）。書き出しは 2.5秒。
    だから 読み込みの速さ ＝ 操作の速さ。ところが今の起動の指定（-t 12 / KV q8_0 / ngram）は
    **書き出し（tg）の速さで選んだもの**（2026-09-10）。読み込みで選び直す。

  ★ 疑い（推測で語らず、ここで測る）
    ・-ngl 0 でも Metal（AMD 5300M）が居ると、読み込みのたびに重みを GPU へ運ぶことがある → -dev none
    ・KV q8_0 は 2026-09-06 に pp -28% と出ていたのに、tg のために残っている → f16
    ・--cache-reuse: 画面の資料は「ほぼ同じで数行ちがう」。ずらして使い回せれば 読み直しが減る

  ★ 測り方
    画面は使わない。モデルを 8090 で自分で立て、測り、消す。**1本だけ**（16GB）。
    1) 冷えた読み込み: 約1000トークン（本物の SYSTEM＋画面の資料の形）を 使い回しなしで 3回 → t/s の中央値
       （立てて最初の1回は 重みを SSD から触る時間が混じるので 捨てる）
    2) 次の手: 前の頼み文に「これまでの手」1行を足し 画面2行を変えた文 → 実際に読み直したトークン数と秒
    3) その間の ページイン（MB）。大きければ RAM に収まらず SSD を読み直している
"""
from __future__ import annotations
import json, os, signal, statistics, subprocess, sys, time, urllib.request, uuid

import os, sys
# ★ 2026-09-16: 正は内蔵の写し（外部SSDは日に何度も切れる）。無ければ SSD を見る
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel")
                                                if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")
sys.path.insert(0, KERNEL)
import sousa

LSRV = next((b for b in (os.path.expanduser("~/LocalAI_mirror/llama-latest/build/bin/llama-server"),
                         "/Volumes/Mac Windows/LocalAI/llama-latest/build/bin/llama-server") if os.path.exists(b)), "")
LBIN = os.path.dirname(LSRV)
MODEL = os.path.expanduser("~/LocalAI_mirror/models/Qwen3-30B-A3B-Q2_K.gguf")
PORT = 8090
KEKKA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kekka")


def opts(t="12", ngl="0", ub="256", kv=None, spec="ngram-simple", extra=()):
    a = ["-t", t, "-ngl", ngl, "-ub", ub]
    if kv:
        a += ["-ctk", kv, "-ctv", kv]
    if spec:
        a += ["--spec-type", spec]
    return a + list(extra)


# (見出し, 起動の指定)。A が今の server.py と同じ。
SHITEI = [
    ("A 今のまま（KV q8_0・ngram）",        opts(kv="q8_0")),
    ("B A ＋ GPUを使わない(-dev none)",      opts(kv="q8_0", extra=["-dev", "none"])),
    ("C B ＋ KV量子化なし(f16)",             opts(extra=["-dev", "none"])),
    ("D C ＋ --cache-reuse 64",              opts(extra=["-dev", "none", "--cache-reuse", "64"])),
    ("E C ＋ -ub 512",                       opts(ub="512", extra=["-dev", "none"])),
    ("F C ＋ 読み込みは6本(-tb 6)",          opts(extra=["-dev", "none", "-tb", "6"])),
    ("G C ＋ 投機なし",                      opts(spec=None, extra=["-dev", "none"])),
    ("H C ＋ 常駐(--mlock)",                 opts(extra=["-dev", "none", "--mlock"])),
    ("I C の代わりに Metal に 8層(-ngl 8)",  opts(ngl="8")),
]

# ── 頼み文（本物の形）────────────────────────────────────────────
MOKUTEKI = "メモを開いて、新しいメモに カーネル試験0913 と書いて"
_MOJI = ["メモ", "ファイル", "編集", "フォーマット", "表示", "ウインドウ", "ヘルプ", "すべてのiCloud",
         "メモ – 5件のメモ", "検索", "フォルダ", "新規メモ", "今日", "昨日", "過去7日間", "過去30日間",
         "買い物リスト", "牛乳を買う", "会議のメモ", "来週の予定を確認する", "レシピ", "カレーの作り方",
         "旅行の計画", "北海道に行く", "読書メモ", "新しい本を読み始めた", "ピン固定", "共有", "写真を追加",
         "チェックリスト", "表を追加", "リンクを追加", "フォントを大きく", "タイトル", "見出し", "本文",
         "箇条書き", "番号付きリスト", "添付ファイルを表示", "削除したメモ", "クイックメモ", "スマートフォルダ",
         "メモをロック", "名称未設定", "最近削除した項目", "iCloud", "このMac内", "メモを検索", "フォルダを追加",
         "並べ替え", "タグ", "重要", "仕事", "個人", "書き出す", "プリント"]


def _g(moji, dai):
    return {"アプリ": "Notes", "枠": (0, 0, 1440, 900), "目当て": "Notes", "窓の題": dai,
            "文字": [{"文": s, "x": 100 + (i % 3) * 300, "y": 28 + i * 14} for i, s in enumerate(moji)]}


NARABI = "画面が後"     # --narabi 画面が先 で、画面を履歴より前に置く（sousa.NARABI と同じ意味）


def _tanomi(rireki, g, mae=None, nonce=None):
    p = []
    if nonce:
        p.append("整理番号: " + nonce)
    p.append("目当て: " + MOKUTEKI)
    rb = ("これまでの手:\n" + "\n".join("  %d. %s" % (i + 1, r) for i, r in enumerate(rireki))) if rireki else ""
    gb = "【画面（資料）】\n" + sousa._shiryou(g, mae)
    p += [gb, rb] if NARABI == "画面が先" else [rb, gb]
    return "\n\n".join(x for x in p if x)


G1 = _g(_MOJI, "メモ – 5件のメモ")
M2 = list(_MOJI); M2[11] = "新規メモを作成"; M2.append("カーネル試験0913")
G2 = _g(M2, "メモ – 6件のメモ")
M3 = list(M2); M3[3] = "書式"; M3.append("保存しました")
G3 = _g(M3, "メモ – 6件のメモ")
TE1 = _tanomi([], G1)
TE2 = _tanomi(["アプリ「Notes」を前に出す"], G2, {m["文"] for m in G1["文字"]})
TE3 = _tanomi(["アプリ「Notes」を前に出す", "キー cmd+n を押す"], G3, {m["文"] for m in G2["文字"]})


# ── モデルの上げ下げ ────────────────────────────────────────────
def _ikiteru():
    return subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True).returncode == 0


def kesu(p=None):
    if p is not None:
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except Exception:
            pass
    subprocess.run(["pkill", "-f", "llama-server.*--port %d" % PORT], capture_output=True)
    for _ in range(40):
        if not _ikiteru():
            return
        time.sleep(1)
    subprocess.run(["pkill", "-9", "-f", "llama-server.*--port %d" % PORT], capture_output=True)
    time.sleep(2)


def tateru(o, srvlog):
    srvlog.write(("\n===== %s =====\n" % " ".join(o)).encode()); srvlog.flush()
    p = subprocess.Popen([LSRV, "-m", MODEL, "-c", "8192", "-np", "1", "-cb", "--reasoning-format", "none",
                          "--host", "127.0.0.1", "--port", str(PORT)] + o,
                         stdout=srvlog, stderr=srvlog, stdin=subprocess.DEVNULL, start_new_session=True,
                         env=dict(os.environ, DYLD_LIBRARY_PATH=LBIN))
    t0 = time.time()
    while time.time() - t0 < 300:
        if p.poll() is not None:
            return None, "落ちた（%.0f秒）" % (time.time() - t0)
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/health" % PORT, timeout=2) as r:
                if r.status == 200:
                    return p, "%.0f秒で立った" % (time.time() - t0)
        except Exception:
            pass
        time.sleep(1)
    return None, "300秒たっても立たない"


def kiku(user, cache=True):
    body = {"model": "local", "temperature": 0, "max_tokens": 8, "cache_prompt": cache,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": sousa.SYSTEM}, {"role": "user", "content": user}]}
    req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % PORT,
                                 data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read().decode("utf-8"))
    tm = d.get("timings") or {}
    kotae = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return tm, time.time() - t0, kotae.strip()


def pageins_mb():
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if ln.startswith("Pageins:"):
            return int(ln.split(":")[1].strip().rstrip(".")) * 4096 / 1e6
    return 0.0


def hakaru(midashi, o, srvlog):
    print("── %s" % midashi)
    print("   指定: %s" % " ".join(o))
    p, koto = tateru(o, srvlog)
    if not p:
        print("   ×  %s\n" % koto)
        kesu()
        return None
    try:
        tm, byou, _ = kiku(TE1, cache=False)             # 最初の1回は捨てる（重みの初回読み）
        print("   立ち上げ: %s ／ 初回（捨て）: %d トークン %.0f秒" % (koto, tm.get("prompt_n", 0), byou))
        pi0 = pageins_mb()
        tps, n_tok = [], 0
        for _ in range(3):
            tm, byou, kotae = kiku(_tanomi([], G1, nonce=uuid.uuid4().hex[:10]), cache=False)
            tps.append(float(tm.get("prompt_per_second") or 0)); n_tok = tm.get("prompt_n", 0)
        pi = pageins_mb() - pi0
        med = statistics.median(tps)
        print("   冷えた読み込み: %s t/s → 中央 %.1f t/s（1000トークンで %.0f秒） ／ ページイン %.0f MB"
              % (" / ".join("%.1f" % x for x in tps), med, 1000 / med if med else 0, pi))
        kiku(TE1, cache=True)
        tm2, b2, _ = kiku(TE2, cache=True)
        tm3, b3, kotae = kiku(TE3, cache=True)
        print("   次の手: 読み直し %d トークン・%.1f秒（使い回し %s） ／ 3手目: %d・%.1f秒（使い回し %s）"
              % (tm2.get("prompt_n", 0), tm2.get("prompt_ms", 0) / 1000, tm2.get("cache_n", "?"),
                 tm3.get("prompt_n", 0), tm3.get("prompt_ms", 0) / 1000, tm3.get("cache_n", "?")))
        print("   答え: %s\n" % kotae[:60])
        return {"名": midashi, "tps": med, "次の手_tok": tm2.get("prompt_n", 0), "次の手_秒": tm2.get("prompt_ms", 0) / 1000,
                "3手目_tok": tm3.get("prompt_n", 0), "3手目_秒": tm3.get("prompt_ms", 0) / 1000, "ページイン": pi, "総": n_tok}
    except Exception as e:
        print("   ×  つまずいた: %s: %s\n" % (type(e).__name__, str(e)[:120]))
        return None
    finally:
        kesu(p)


def main():
    global NARABI, TE1, TE2, TE3
    if _ikiteru():
        print("llama-server がもう動いています（1本だけの決まり）。カーネル.app を閉じてから"); return 2
    os.makedirs(KEKKA, exist_ok=True)
    print("===== 読み込みの速さ %s =====" % time.strftime("%m/%d %H:%M"))
    print("  頼み文: SYSTEM %d字 ＋ 1手目 %d字 ／ 2手目 %d字 ／ 3手目 %d字\n" % (len(sousa.SYSTEM), len(TE1), len(TE2), len(TE3)))
    args = sys.argv[1:]
    if "--narabi" in args:
        i = args.index("--narabi"); NARABI = args[i + 1]; args = args[:i] + args[i + 2:]
        TE1 = _tanomi([], G1)
        TE2 = _tanomi(["アプリ「Notes」を前に出す"], G2, {m["文"] for m in G1["文字"]})
        TE3 = _tanomi(["アプリ「Notes」を前に出す", "キー cmd+n を押す"], G3, {m["文"] for m in G2["文字"]})
        print("  並び: %s（画面を履歴より前に置く）" % NARABI if NARABI == "画面が先" else "  並び: %s" % NARABI)
    erabu = [x for x in SHITEI if not args or any(x[0].startswith(a) for a in args)]
    kekka = []
    with open(os.path.join(KEKKA, "yomi_srv.log"), "ab") as srvlog:
        for midashi, o in erabu:
            r = hakaru(midashi, o, srvlog)
            if r:
                kekka.append(r)
    print("===== まとめ（読み込み t/s が高いほど速い。次の手 は 実際に読み直す量）=====")
    print("  %-38s %8s %14s %14s %8s" % ("指定", "t/s", "次の手 tok/秒", "3手目 tok/秒", "ページイン"))
    for r in kekka:
        print("  %-38s %8.1f %8d/%5.1f %8d/%5.1f %6.0fMB" % (r["名"][:38], r["tps"], r["次の手_tok"], r["次の手_秒"],
                                                          r["3手目_tok"], r["3手目_秒"], r["ページイン"]))
    with open(os.path.join(KEKKA, "yomi_%s.json" % time.strftime("%m%d_%H%M")), "w", encoding="utf-8") as f:
        json.dump(kekka, f, ensure_ascii=False, indent=1)
    print("===== おわり %s =====" % time.strftime("%H:%M"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
