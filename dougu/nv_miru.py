"""NVIDIA の画像が読めるモデルに、画面の写真を見てもらう（9/28）。

  python3 dougu/nv_miru.py "頼み" 写真1.png [写真2.png ...] [--model ID]

鍵はカーネルの nvidia.key()（~/.nvidia.env）から読む。値は出さない。
前から順に試し、答えたモデルの名前を先頭に出す。
"""
import base64, json, os, sys, urllib.request

sys.path.insert(0, os.path.expanduser("~/LocalAI_mirror/kernel"))
import nvidia  # noqa: E402

URL = "https://integrate.api.nvidia.com/v1/chat/completions"
JUNBAN = [
    "moonshotai/kimi-k3",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "meta/llama-3.2-90b-vision-instruct",
    "google/gemma-3-12b-it",
]


def miru(tanomi, shashin, model=None, max_tokens=2500):
    k = nvidia.key()
    if not k:
        return None, "NVIDIA の鍵が見つかりません（~/.nvidia.env）"
    naiyou = [{"type": "text", "text": tanomi}]
    for p in shashin:
        b = base64.b64encode(open(p, "rb").read()).decode()
        mime = "image/jpeg" if p.lower().endswith((".jpg", ".jpeg")) else "image/png"
        naiyou.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b}"}})
    ayamari = []
    for m in ([model] if model else JUNBAN):
        body = {"model": m, "messages": [{"role": "user", "content": naiyou}],
                "max_tokens": max_tokens, "temperature": 0.3, "stream": True}
        if "nemotron" in m:  # 考えを長く書いて答えが空になるので、考えは切る
            body["chat_template_kwargs"] = {"enable_thinking": False}
        req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={
            "Authorization": f"Bearer {k}", "Content-Type": "application/json"})
        try:
            # 流して受け取る（長く考えるモデルでも、読みの時間切れにならない）
            kotae, kangae = [], []
            with urllib.request.urlopen(req, timeout=300, context=nvidia._ctx()) as r:
                for line in r:
                    line = line.decode("utf-8", "replace").strip()
                    if not line.startswith("data:") or line == "data: [DONE]":
                        continue
                    try:
                        d = json.loads(line[5:])["choices"][0].get("delta") or {}
                    except (ValueError, KeyError, IndexError):
                        continue
                    kotae.append(d.get("content") or "")
                    kangae.append(d.get("reasoning_content") or "")
            if "".join(kotae).strip():
                return m, "".join(kotae).strip()
            if "".join(kangae).strip():
                return m, "（考えの部分だけ）" + "".join(kangae).strip()[-3000:]
            ayamari.append(f"{m}: 空の答え")
        except Exception as e:  # 次のモデルへ
            ayamari.append(f"{m}: {getattr(e, 'code', '')} {str(e)[:120]}")
    return None, "どのモデルも答えませんでした\n" + "\n".join(ayamari)


if __name__ == "__main__":
    args = sys.argv[1:]
    model = None
    if "--model" in args:
        i = args.index("--model"); model = args[i + 1]; del args[i:i + 2]
    m, kotae = miru(args[0], args[1:], model)
    print(f"[{m or 'なし'}]")
    print(kotae)
