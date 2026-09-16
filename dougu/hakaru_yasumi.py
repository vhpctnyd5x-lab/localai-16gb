#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hakaru_yasumi.py -- 物差し: 手元のモデルが「使われないと畳まれ、次の頼みで起きる」こと（server.py の MODERU_IDLE）。

  ★ なぜ（2026-09-16・「安い」）
    16GB の機械で 11GB を握ったままだと、カーネルを開いているだけで他が重い。
    使われずに一定時間たったら畳み、次の頼みで起こし直す。ここでは 45秒 に縮めて確かめる。

  ★ 見るもの
    ① 立ち上げ直後の頼みに答える  ② 45秒＋見張りの間隔で llama-server が消える（RSS が返る）
    ③ その次の頼みにも答える（起こし直し。何秒かかったかも出す）  ④ 畳んだ後は /state が「休止中」を言う
"""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.request
KERNEL = os.environ.get("KERNEL_DIR") or next((d for d in (os.path.expanduser("~/LocalAI_mirror/kernel"), "/Volumes/Mac Windows/LocalAI/kernel")
                                                if os.path.isfile(os.path.join(d, "server.py"))), "/Volumes/Mac Windows/LocalAI/kernel")


def _llama_iru():
    return subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True).returncode == 0


def _post(url, michi, obj):
    base, _, t = url.partition("?t=")
    req = urllib.request.Request(base.rstrip("/") + michi, data=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-Token": t, "Authorization": "Bearer " + t})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(url, michi):
    base, _, t = url.partition("?t=")
    req = urllib.request.Request(base.rstrip("/") + michi + "?t=" + t, headers={"X-Token": t, "Authorization": "Bearer " + t})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    if _llama_iru():
        print("llama-server がもう動いています（1本だけの決まり）"); return 2
    env = dict(os.environ, KERNEL_MODERU_IDLE="45", DYLD_LIBRARY_PATH=os.path.expanduser("~/LocalAI_mirror/llama-latest/build/bin"))
    p = subprocess.Popen(["/usr/local/bin/python3", "server.py"], cwd=KERNEL, stdout=subprocess.PIPE, stderr=open(os.path.join(os.path.dirname(__file__), "kekka", "yasumi_srv.log"), "ab"),
                         text=True, start_new_session=True, env=env)
    url = (p.stdout.readline() or "").strip()
    print("===== 休みの物差し %s =====" % time.strftime("%m/%d %H:%M"))
    print("  URL: %s…" % url[:28])
    maru = 0
    try:
        t0 = time.time(); r = _post(url, "/ask", {"text": "1+1は？ 数字だけ答えて"}); b1 = time.time() - t0
        ok1 = "2" in str(r.get("出力", "")); maru += ok1
        print("  %s ① 最初の頼み %.0f秒: %s" % ("○" if ok1 else "×", b1, str(r.get("出力", ""))[:40].replace("\n", " ")))
        print("     llama-server: %s" % ("居る" if _llama_iru() else "居ない"))
        kieta = None
        for i in range(24):
            time.sleep(5)
            if not _llama_iru():
                kieta = (i + 1) * 5; break
        ok2 = kieta is not None; maru += ok2
        print("  %s ② 使わずに待つ → %s" % ("○" if ok2 else "×", "%d秒ほどで畳まれた" % kieta if kieta else "120秒たっても畳まれない"))
        time.sleep(3)                      # 畳み終えて印が立つまで少し待つ（プロセスが消えるのが先）
        st = _get(url, "/state")
        ok4 = bool(st.get("手元は休止中")); maru += ok4
        print("  %s ④ /state が休止中を言う: %s" % ("○" if ok4 else "×", st.get("手元は休止中")))
        t0 = time.time(); r = _post(url, "/ask", {"text": "2+2は？ 数字だけ答えて"}); b2 = time.time() - t0
        ok3 = "4" in str(r.get("出力", "")); maru += ok3
        print("  %s ③ 起こし直しての頼み %.0f秒（うち起こすのに数十秒）: %s" % ("○" if ok3 else "×", b2, str(r.get("出力", ""))[:40].replace("\n", " ")))
    except Exception as e:
        print("  × つまずいた: %s: %s" % (type(e).__name__, str(e)[:160]))
    finally:
        p.terminate()
        for _ in range(20):
            time.sleep(1)
            if p.poll() is not None and not _llama_iru():
                break
        print("  片づけ: server.py %s ／ llama-server %s" % ("終わった" if p.poll() is not None else "まだ", "居ない" if not _llama_iru() else "居る！"))
        subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
    print("  休みの物差し: %d/4" % maru)
    return 0 if maru == 4 else 1


if __name__ == "__main__":
    sys.exit(main())
