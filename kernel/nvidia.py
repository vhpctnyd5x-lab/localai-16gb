#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nvidia.py -- カーネルから NVIDIA の API を呼ぶ

  サブエージェントではない。NVIDIA Build（NIM）の HTTP API を直接叩く。

  【鍵の扱い】
  API キーは、このファイルにも、カーネルのどこにも書かない。
  次の順で探して、見つかったものを使う。

    ① 環境変数 NVIDIA_API_KEY
    ② ~/.nvidia.env の  NVIDIA_API_KEY=...  の行
    ③ 手元の nv コマンド（キーチェーンから承認つきで取り出す）
       … 呼ぶたびに macOS の承認ダイアログが出る

  ①②なら、ダイアログ無しで動く。
  ③しか無いときは、そのつど承認を求められる（安全側の既定）。

  【使いどころ】
  外の大きなモデルは、うまい／へたがはっきり分かれる。実測:

    述語を225個ならべさせる … 負け。52個しか出ず、命令にならない形も混ざった
                              （規則で作ったら1,112個・全部正しい）
    server.py の安全性を見る … 勝ち。本物のバグを2つ見つけた

  だから「作らせる」より「見てもらう・言い換えてもらう」に使う。
"""
import json, os, subprocess, ssl, urllib.request, urllib.error

BASE = "https://integrate.api.nvidia.com/v1/chat/completions"
ENV_FILE = os.path.expanduser("~/.nvidia.env")

# 短い呼び名。長いモデル名を覚えなくていいように
ALIASES = {
    "super": "nvidia/nemotron-3-super-120b-a12b",      # ふつう。釣り合いがよい
    "ultra": "nvidia/nemotron-3-ultra-550b-a55b",      # いちばん賢い。遅い
    "fast":  "nvidia/nemotron-3.5-lightning-30b-a3b",  # 速い。軽い
    "code":  "openai/gpt-oss-120b",                    # プログラム向き
    "deep":  "deepseek-ai/deepseek-v4-pro-0813",       # よく考える
    # 2026-08-27 実測で、この鍵から呼べないもの（消した）:
    #   meta/llama-3.3-70b-instruct   → 410 提供終了
    #   z-ai/glm-5.2                  → 410 提供終了
    #   nvidia/nemotron-4-340b        → 404
    #   mistralai/mistral-large-2     → 404
    # 一覧(/v1/models)には出るのに投げると通らないものが多い。
    # 「一覧にある」＝「使える」ではない
}
DEFAULT = "fast"


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _key_from_file():
    if not os.path.exists(ENV_FILE):
        return None
    try:
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line.startswith("NVIDIA_API_KEY"):
                _k, _eq, v = line.partition("=")
                return v.strip().strip('"').strip("'") or None
    except OSError:
        return None
    return None


def tadashii(k):
    """鍵らしい形をしているか。

    「鍵はあるのに使えない」ときの原因を、はっきり言うために要る。
    実際、説明の例文（NVIDIA_API_KEY=あなたの鍵）を そのまま
    書き込んだ状態で
        'latin-1' codec can't encode characters in position 7-11
    という、何が悪いのか誰にも分からないエラーが出ていた。
    （HTTP の見出しに日本語は書けない、という意味だった）
    """
    if not k:
        return False, "鍵がありません"
    if not k.isascii():
        return False, ("鍵に日本語が入っています。"
                       "説明の例文（あなたの鍵）が そのまま書かれていませんか。\n"
                       "  NVIDIA のページで作った本物の鍵（nvapi- で始まる長い文字列）"
                       "に書き換えてください")
    if len(k) < 20:
        return False, f"鍵が短すぎます（{len(k)} 文字）。写し間違いかもしれません"
    return True, None


def key():
    """鍵を探す。見つからなければ None（＝nv コマンド経由に回る）"""
    k = os.environ.get("NVIDIA_API_KEY") or _key_from_file()
    ok, _riyuu = tadashii(k)
    return k if ok else None


def naze():
    """鍵が使えない理由を、日本語で返す。使えるなら None"""
    k = os.environ.get("NVIDIA_API_KEY") or _key_from_file()
    ok, riyuu = tadashii(k)
    return None if ok else riyuu


def how():
    """いま、どうやって呼べる状態か"""
    if os.environ.get("NVIDIA_API_KEY"):
        return "環境変数（ダイアログ無し）"
    if _key_from_file():
        return f"{ENV_FILE}（ダイアログ無し）"
    if _nv_path():
        return "nv コマンド（呼ぶたびに承認ダイアログが出ます）"
    return None


def _nv_path():
    for p in (os.path.expanduser("~/.local/bin/nv"), "/usr/local/bin/nv"):
        if os.path.exists(p):
            return p
    return None


def models():
    return dict(ALIASES)


def ask(prompt, model=DEFAULT, system="", timeout=90, max_tokens=1024,
        temperature=0.2):
    """ひとこと聞いて、返事の文字列を返す。

    つながらなければ、日本語で理由を書いた例外を投げる
    """
    name = ALIASES.get(model, model)
    k = key()
    if k:
        return _http(name, prompt, system, k, timeout, max_tokens, temperature)
    nv = _nv_path()
    if not nv:
        raise Exception(
            "NVIDIA の鍵が見つかりません。\n"
            f"  {ENV_FILE} に  NVIDIA_API_KEY=... の1行を書くと、"
            "ダイアログ無しで使えるようになります")
    return _via_nv(nv, name, prompt, system, timeout)


def _http(name, prompt, system, k, timeout, max_tokens, temperature):
    msgs = ([{"role": "system", "content": system}] if system else []) \
        + [{"role": "user", "content": prompt}]
    body = json.dumps({"model": name, "messages": msgs,
                       "max_tokens": max_tokens,
                       "temperature": temperature,
                       "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        BASE, data=body,
        headers={"Authorization": "Bearer " + k,
                 "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=_ctx()) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        if e.code == 401:
            raise Exception("鍵がはじかれました（401）。鍵を確かめてください")
        if e.code == 403:
            raise Exception(
                "鍵は本人確認を通りましたが、推論を実行する権限がありません（403）。\n"
                "  実測: モデル一覧（/v1/models）は 84個 返るのに、\n"
                "        どのモデルに投げても Authorization failed になります。\n"
                "  鍵の形もモデル名も正しいので、アカウント側の話です。\n"
                "  よくある原因:\n"
                "    ・build.nvidia.com のモデルのページで作った鍵ではない\n"
                "      （NGC の鍵は 一覧は見られても 推論は通らないことがあります）\n"
                "    ・無料ぶんが尽きている／まだ有効になっていない\n"
                "  直し方: build.nvidia.com で使いたいモデルのページを開き、\n"
                "          そのページの「Get API Key」から鍵を作り直してください")
        if e.code == 410:
            raise Exception(f"そのモデルは提供が終わっています（410）: {name}")
        if e.code == 429:
            raise Exception("急かしすぎです（429）。少し待ってからにしてください")
        raise Exception(f"NVIDIA が {e.code} を返しました： {detail}")
    except Exception as e:
        raise Exception(f"NVIDIA につながりませんでした（{e}）")
    try:
        return d["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        raise Exception("返事の形が読めませんでした")


def _via_nv(nv, name, prompt, system, timeout):
    """nv コマンド経由。呼ぶたびに承認ダイアログが出る"""
    full = f"{system}\n\n{prompt}" if system else prompt
    try:
        r = subprocess.run([nv, "ask", full, "-m", name],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Exception(f"{timeout}秒たっても返事がありませんでした")
    if r.returncode != 0:
        raise Exception((r.stderr or r.stdout or "うまくいきませんでした").strip()[:200])
    return (r.stdout or "").strip()


def check():
    """つながるかどうかを、実際に1回だけ確かめる"""
    h = how()
    if not h:
        return False, "鍵もコマンドも見つかりません"
    try:
        t = ask("「はい」とだけ返してください。", model="fast",
                max_tokens=16, timeout=30)
        return True, f"{h} ／ 返事: {t[:40]}"
    except Exception as e:
        return False, f"{h} ／ {e}"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        m = DEFAULT
        args = sys.argv[1:]
        if args[0] in ALIASES:
            m, args = args[0], args[1:]
        print(ask(" ".join(args), model=m))
    else:
        print("  呼び方:", how() or "（使えません）")
        print("  モデル:", ", ".join(ALIASES))
        ok, msg = check()
        print(("  ✓ " if ok else "  ✗ ") + msg)
