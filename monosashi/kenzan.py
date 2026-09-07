#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kenzan.py -- 物差しそのものを疑う。NVIDIA の大きいモデルに独立に解かせて、
Python が出した答えと突き合わせる。

★ なぜやるか（引き継ぎ書2 の一番大事な教訓）:
    前回は「測り方の穴」を2つ踏み、一度は嘘の数字を報告して撤回した。
    問題集は Python が作っているので答えは構造上正しい **はず** だが、
    「問題文が答えを一意に決めていない」「日本語が曖昧」は 別の穴。
    ★ ここで見たいのは Nemotron の点ではなく **食い違った問題**。
      食い違ったものだけ人が見て、問題の方が悪ければ捨てる。

使いかた:
    python3 kenzan.py                 # 全件
    python3 kenzan.py --kagiri 10     # まず10件で試す（★必ずこれを先に）
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
from hakaru import _seikai

# ★ 公開版では 鍵を **環境変数から** 読む（手元の版は macOS キーチェーンから
#   承認ダイアログ越しに取っている。鍵を平文で置かないこと）。
#     export NVIDIA_API_KEY=...        https://build.nvidia.com/
import concurrent.futures, threading, urllib.request

NV_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def _kiku(prompt, system, model, max_tokens=2000):
    kagi = os.environ.get("NVIDIA_API_KEY", "")
    if not kagi:
        return "__ERR__ NVIDIA_API_KEY が設定されていません"
    body = {"model": model, "temperature": 0.0, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        NV_URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + kagi})
    try:
        with urllib.request.urlopen(req, timeout=180) as f:
            d = json.loads(f.read().decode("utf-8"))
        return d["choices"][0]["message"]["content"] or ""
    except Exception as e:
        return "__ERR__ %s" % e


def _nagasu(shigoto, dedokoro, narabi=2, max_tokens=2000):
    """中断・再開つきで並べて投げる。既に出来ている id は飛ばす。"""
    sumi = set()
    if os.path.exists(dedokoro):
        for ln in open(dedokoro, encoding="utf-8"):
            if ln.strip():
                try:
                    sumi.add(json.loads(ln)["id"])
                except Exception:
                    pass
    nokori = [s for s in shigoto if s[0] not in sumi]
    print("全%d件 / 済み%d件 / これから%d件" % (len(shigoto), len(sumi), len(nokori)))
    if not nokori:
        return
    f = open(dedokoro, "a", encoding="utf-8")
    kaku = threading.Lock()

    def hitotsu(s):
        i, p, sy, mo = s
        r = _kiku(p, sy, mo, max_tokens)
        with kaku:
            f.write(json.dumps({"id": i, "kotae": r}, ensure_ascii=False) + "\n")
            f.flush()

    with concurrent.futures.ThreadPoolExecutor(max_workers=narabi) as ex:
        list(ex.map(hitotsu, nokori))
    f.close()

SYSTEM = ("あなたは 算数と なぞときの係です。ていねいに考えてから、"
          "最後の行に「答え: 〜」の形で **答えだけ** を書いてください。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mondai", default=os.path.join(HERE, "mondai.jsonl"))
    ap.add_argument("--out", default=os.path.join(HERE, "kekka", "kenzan.jsonl"))
    ap.add_argument("--model", default="nvidia/nemotron-3-ultra-550b-a55b")
    ap.add_argument("--kagiri", type=int, default=0)
    ap.add_argument("--narabi", type=int, default=2)   # 6 だと 429 が出た
    a = ap.parse_args()

    mondai = [json.loads(l) for l in open(a.mondai, encoding="utf-8") if l.strip()]
    if a.kagiri:
        mondai = mondai[:a.kagiri]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)

    shigoto = [(m["id"], m["問"], SYSTEM, a.model) for m in mondai]
    _nagasu(shigoto, a.out, narabi=a.narabi, max_tokens=2000)

    kotae = {}
    for ln in open(a.out, encoding="utf-8"):
        ln = ln.strip()
        if ln:
            d = json.loads(ln)
            kotae[d["id"]] = d["kotae"]

    chigau, err = [], 0
    for m in mondai:
        t = kotae.get(m["id"], "")
        if not t or t.startswith("__ERR__"):
            err += 1
            continue
        # 「答え: 〜」の行を優先して見る。無ければ全文で照合する
        saigo = t.strip().splitlines()[-1] if t.strip() else ""
        if not _seikai(m, saigo) and not _seikai(m, t):
            chigau.append({"id": m["id"], "段": m["段"], "型": m["型"],
                           "問": m["問"], "こちらの答": m["答"],
                           "NVIDIA": saigo[:160]})

    michi = os.path.join(HERE, "kekka", "kenzan_chigau.json")
    json.dump(chigau, open(michi, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n全%d件 / 通信できず%d件 / **食い違い %d件**（%.1f%%）"
          % (len(mondai), err, len(chigau), 100.0 * len(chigau) / max(1, len(mondai))))
    print("→", michi)
    from collections import Counter
    if chigau:
        print("段ごと:", dict(Counter(c["段"] for c in chigau)))
        print("型ごと:", dict(Counter(c["型"] for c in chigau)))


if __name__ == "__main__":
    main()
