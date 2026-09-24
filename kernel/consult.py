#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
consult.py -- 行き詰まった時だけ、複数の先生(LLM)に相談する層

方針:
  ・先生は「案」を出すだけ。正しいかどうかは一切信用しない
  ・採用の可否は kernel 側の検証装置(下見実行 + goal判定)が決める
  ・採用された案はノートに残るので、次から先生は不要になる
"""

TEACHERS = ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"]

SYS = ("あなたはPC操作エンジンの助手です。JSONだけを出力し、説明・前置き・"
       "コードフェンスは一切書かないこと。分からない項目は省略すること。")


def _kimeru():
    """相談する先生を決める。/model の設定を見て、無ければ上の既定。

    ここが設定を見ていなかった（2026-09-06 に気づいた）。
    /model local:main に替えても、ページ作り(make_page)だけが手元に移り、
    **スロット読みと手順立案は Groq に出たまま**だった。
    「完全に手元で閉じる」と言えるためには、ここも設定に従う必要がある。
    """
    try:
        import settings
        t = settings.load().get("先生")
        if isinstance(t, list) and t:
            return [x for x in t if isinstance(x, str) and x.strip()]
    except Exception:
        pass
    return list(TEACHERS)


def _panel(prompt, teachers=None, timeout=25):
    """先生団に同時に聞く。teachers.py が無い/壊れていても落ちない"""
    try:
        from teachers import ask_panel
    except Exception as e:
        return [], f"先生に接続できません: {e}"
    panel = teachers or _kimeru()
    # 手元の先生は 20 t/s 級。Groq(500 t/s 級) と同じ 25 秒だと
    # 出てくるのは「時間切れ」であって 判断の質ではない。
    if any(str(x).startswith("local:") or str(x).startswith("ollama:")
           for x in panel):
        timeout = max(timeout, 90)
    try:
        # ★ 2026-09-12: 分類は JSON を出すだけなので考えさせない（深さ0）。
        #   既定の深さ2だと、雑談のたびに 200字考えてから JSON を書いていた（遅い・無駄）。
        return ask_panel(prompt, system=SYS, teachers=panel,
                         timeout=timeout, fukasa=0), None
    except Exception as e:
        return [], f"相談に失敗: {e}"


def ask_slots(text, vocab):
    """相談その1: 言葉からスロットを読み取ってもらう

    戻り値: [(先生名, スロットdict), ...]  速く返った順
    """
    choices = "\n".join(f"  {k}: {' / '.join(v)}" for k, v in vocab.items())
    # ★ 並び順が 速さを決める（2026-09-06 に実測）
    #   llama.cpp のサーバーは「前と同じ頭の部分」を **覚えていて読み直さない**。
    #   だから **毎回同じもの（選べる値・書き方・出力例）を先に、
    #   毎回ちがうもの（命令）を最後に** 置く。
    #   同じ長さの頼み文で:
    #       同じ頭 → ちがう尾 : 75.6s → 3.3s → 7.9s（1666中1637を再利用）
    #       ちがう頭 → 同じ尾 : 81.1s → 77.6s → 85.3s（毎回3しか再利用しない）
    #   **23倍。** 手元の先生は読解が 28 t/s しか出ないので、ここが効く。
    #   （Groq には関係ないが、悪くもならない）
    prompt = (
        f"次の日本語の命令を読み、下の選択肢から当てはまるものだけを選んでJSONにしてください。\n"
        f"選択肢に無い値は絶対に作らないこと。\n\n"
        f"【選べる値】\n{choices}\n\n"
        f"各項目について、命令文の中の『どの言葉』がそれを表しているかも、"
        f"命令文からそのまま抜き出して答えてください。\n"
        f'出力例: {{"動作":{{"値":"移動","言葉":"寄せといて"}},'
        f'"場所":{{"値":"Desktop","言葉":"机の上"}}}}\n\n'
        f"【命令】{text}"
    )
    results, err = _panel(prompt)
    out = []
    for r in results:
        j = r.get("json")
        if not isinstance(j, dict):
            continue
        # 選択肢に無い値は、この時点で捨てる（先生の作り話への一次防御）
        clean, words = {}, {}
        for k, v in j.items():
            if k not in vocab:
                continue
            val = v.get("値") if isinstance(v, dict) else v
            wrd = v.get("言葉") if isinstance(v, dict) else None
            if isinstance(val, str) and val in vocab[k]:
                clean[k] = val
                # 命令文に実在する言葉だけを、新しいカードの候補にする
                if isinstance(wrd, str) and 1 < len(wrd) <= 12 and wrd in text:
                    words[wrd] = (k, val)
        if clean:
            out.append((r["teacher"], clean, words))
    return out, err


def ask_plans(text, slots, parts_desc):
    """相談その2: 部品の組み方を提案してもらう

    戻り値: [(先生名, 手順list), ...]  速く返った順
    """
    parts = "\n".join(f"  {n}: {d}" for n, d in parts_desc.items())
    # ★ ask_slots と同じ理由で、毎回ちがう「命令」を最後に置く。
    #   ここは部品表が 873 トークンあり、手元の先生だと 読むだけで 30 秒かかっていた。
    prompt = (
        f"PC操作エンジンの部品を並べて、命令を達成する手順を作ってください。\n\n"
        f"【使える部品】\n{parts}\n\n"
        f"規則:\n"
        f"  ・最初は必ず「さがす」\n"
        f"  ・条件(種類・時期など)が与えられていれば、対応する「しぼる」を必ず使う\n"
        f"  ・「うつす」の前には必ず「つくる」\n"
        f"  ・部品名は一字一句そのまま使うこと\n\n"
        f'出力例: {{"手順":["さがす","しぼる(種類)","かぞえる"]}}\n\n'
        f"【命令】{text}\n"
        f"【読み取れた条件】{slots}"
    )
    results, err = _panel(prompt)
    out = []
    for r in results:
        j = r.get("json")
        plan = None
        if isinstance(j, dict):
            plan = j.get("手順") or j.get("plan") or j.get("steps")
        elif isinstance(j, list):
            plan = j
        if isinstance(plan, list) and plan and all(isinstance(x, str) for x in plan):
            out.append((r["teacher"], plan))
    return out, err
