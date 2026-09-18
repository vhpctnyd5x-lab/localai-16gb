#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雲の上の先生（Groq／NVIDIA の無料 API）を、手元の頭脳と同じ物差し（monosashi の問題・同じ採点）で測る。

  python3 hakaru_kumo.py --sensei groq:openai/gpt-oss-120b --mondai ../monosashi/mondai_7dan.jsonl [--narabi 4] [--kagiri 0]
  python3 hakaru_kumo.py --sensei nvidia:fast ...     （nvidia の呼び名は kernel/nvidia.py の ALIASES）
  鍵は ~/.groq.env / ~/.nvidia.env から台本が読む（画面にも記録にも出さない）。
  出すもの: 正答・1問の秒（中央値）・書いた速さ（tokens/秒・API の usage から）・しくじり。結果は kekka/kumo_<名札>_<日時>.json
"""
import argparse, json, os, re, statistics, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "monosashi"))
sys.path.insert(0, os.path.join(HERE, ".."))
import hakaru as H                      # 採点（_seikai）と SYSTEM を同じにする
KERNEL = os.path.expanduser("~/LocalAI_mirror/kernel")
sys.path.insert(0, KERNEL)
import nvidia as NV


def _env_key(path, name):
    try:
        for l in open(os.path.expanduser(path), encoding="utf-8"):
            l = l.strip()
            if l.startswith(name + "="):
                return l.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


def _post(url, key, payload, timeout):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "curl/8.7.1"})   # Python-urllib は Cloudflare(1010) に弾かれる
    with urllib.request.urlopen(req, timeout=timeout, context=NV._ctx()) as f:
        return json.loads(f.read().decode("utf-8"))


def kiku(sensei, prompt, system, timeout=120, max_tokens=1200):
    kind, model = sensei.split(":", 1)
    if kind == "groq":
        url, key = "https://api.groq.com/openai/v1/chat/completions", _env_key("~/.groq.env", "GROQ_API_KEY")
    elif kind == "nvidia":
        url, key = NV.BASE, _env_key("~/.nvidia.env", "NVIDIA_API_KEY")
        model = NV.ALIASES.get(model, model)
    else:
        raise ValueError(sensei)
    if not key:
        raise RuntimeError("%s の鍵が無い" % kind)
    payload = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
               "temperature": 0.0, "max_tokens": max_tokens}
    t0 = time.monotonic()
    for kai in range(4):
        try:
            d = _post(url, key, payload, timeout)
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            if e.code in (429, 500, 502, 503) and kai < 3:
                m = re.search(r"try again in ([0-9.]+)\s*s", body)
                time.sleep(float(m.group(1)) + 1 if m else 10 * (kai + 1))
                continue
            return {"text": "", "error": "HTTP %s: %s" % (e.code, body), "秒": time.monotonic() - t0}
        except Exception as e:
            if kai < 3:
                time.sleep(5); continue
            return {"text": "", "error": "%s: %s" % (type(e).__name__, e), "秒": time.monotonic() - t0}
    sec = time.monotonic() - t0
    msg = (d.get("choices") or [{}])[0].get("message") or {}
    text = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip()
    u = d.get("usage") or {}
    return {"text": text, "error": None, "秒": sec, "書いた": u.get("completion_tokens"), "読んだ": u.get("prompt_tokens")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sensei", default="groq:openai/gpt-oss-120b")
    ap.add_argument("--mondai", default=os.path.join(HERE, "..", "monosashi", "mondai_7dan.jsonl"))
    ap.add_argument("--narabi", type=int, default=4)
    ap.add_argument("--kagiri", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.mondai, encoding="utf-8") if l.strip()]
    if a.kagiri:
        rows = rows[:a.kagiri]
    name = os.path.basename(a.mondai).replace("mondai_", "").replace(".jsonl", "").replace("mondai", "120")
    print("===== 雲の先生 %s ／ %s %d問 ／ 並び %d（%s） =====" % (a.sensei, name, len(rows), a.narabi, time.strftime("%m/%d %H:%M")))
    t_all = time.monotonic()
    def work(d):
        r = kiku(a.sensei, d["問"], H.SYSTEM, timeout=a.timeout)
        out = (r.get("text") or "").strip()
        return {"id": d["id"], "段": d.get("段"), "型": d.get("型"), "問": d["問"], "答": d["答"], "出力": out[:400],
                "○": H._seikai(d, out) if out else False, "秒": round(r["秒"], 1), "書いた": r.get("書いた"), "しくじり": r.get("error")}
    kekka = []
    with ThreadPoolExecutor(max_workers=a.narabi) as ex:
        for i, r in enumerate(ex.map(work, rows), 1):
            kekka.append(r)
            if i % 16 == 0 or i == len(rows):
                print("  %3d/%d  ○ %d  %.0f秒" % (i, len(rows), sum(1 for k in kekka if k["○"]), time.monotonic() - t_all))
    ok = sum(1 for k in kekka if k["○"]); byou = sorted(k["秒"] for k in kekka)
    tps = [k["書いた"] / k["秒"] for k in kekka if k.get("書いた") and k["秒"] > 0]
    shikujiri = [k for k in kekka if k["しくじり"]]
    print("正答 %d/%d ／ 1問 中央 %.1f秒（最長 %.1f）／ 書いた速さ 中央 %.0f tokens/秒 ／ しくじり %d ／ 全体 %.0f秒（並び %d）"
          % (ok, len(kekka), statistics.median(byou), byou[-1], statistics.median(tps) if tps else 0, len(shikujiri), time.monotonic() - t_all, a.narabi))
    from collections import Counter
    ochi = Counter(k["型"] for k in kekka if not k["○"])
    if ochi:
        print("  落とした型:", dict(ochi.most_common(8)))
    if shikujiri:
        print("  しくじり例:", shikujiri[0]["しくじり"][:120])
    os.makedirs(os.path.join(HERE, "kekka"), exist_ok=True)
    fn = os.path.join(HERE, "kekka", "kumo_%s_%s_%s.json" % (re.sub(r"[^\w.-]", "_", a.sensei), name, time.strftime("%Y%m%d_%H%M")))
    json.dump({"先生": a.sensei, "問題": name, "正答": ok, "問数": len(kekka), "中央秒": statistics.median(byou), "tokens毎秒": statistics.median(tps) if tps else None,
               "一件ずつ": kekka}, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→", os.path.relpath(fn, HERE))


if __name__ == "__main__":
    main()
