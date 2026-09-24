#!/usr/bin/env python3
"""話し合い（2026-09-24 本人:「NVIDIA と Codex にちゃんと話し合ってもらって、その上で開発」）。
1回目: Luna（Codex）と Nemotron（NVIDIA）が それぞれ 次の一手を 3つ出す。
2回目: 相手の案を読んで 批判し、2人とも 上位 2つに絞る。最後は Claude が決める。
使い方: python3 dougu/hanashiai.py 資料.md → dougu/kekka/hanashiai_<日付>.md"""
import os, sys, time
SHIRYOU, sys.argv[1:] = sys.argv[1], []   # tsukuru_tehon は読み込むときに引数を数と読むので 先に外す
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.expanduser("~/LocalAI_mirror/kernel"))   # nvidia.py（鍵は ~/.nvidia.env を中で読む）
import nvidia
from tsukuru_tehon_luna import luna

shiryou = open(SHIRYOU, encoding="utf-8").read()
OUT = os.path.join(HERE, "kekka", "hanashiai_%s.md" % time.strftime("%m%d"))


def nv(p):
    for m in ("ultra", "super"):
        try:
            t = nvidia.ask(p, model=m, timeout=600, max_tokens=6000)
            if t and t.strip():
                return "（%s）\n%s" % (m, t.strip())
        except Exception as e:
            err = str(e)[:80]
    return "（NVIDIA 失敗: %s）" % err


IRAI1 = ("あなたは小さなローカル LLM を強くする研究の相談役です。ファイルやコマンドは使わず、資料だけ読んで考えてください。\n"
         "資料:\n" + shiryou + "\n\n問い: 未見の物差しで点を上げる次の一手を 3つ。各案に「何をする／なぜ効くと考えるか（資料の数字を根拠に）"
         "／期待する伸び（どの型で何問）／測り方／危険（過学習・遅さ・安全）」を書く。資料の不採用と同じ案は出さない。日本語、900字以内。")
a1, b1 = luna(IRAI1), nv(IRAI1)
IRAI2 = ("同じ資料について、2人の相談役が案を出しました。あなたは{who}です。相手の案の弱点を具体的に指摘し、"
         "自分の案も見直したうえで、2人の案から「最初に試す 2つ」を順位つきで選んでください。選んだ理由と、"
         "やめた案の理由を短く。日本語、700字以内。\n\n資料:\n" + shiryou + "\n\n【Luna の案】\n{a}\n\n【Nemotron の案】\n{b}")
a2 = luna(IRAI2.format(who="Luna", a=a1, b=b1))
b2 = nv(IRAI2.format(who="Nemotron", a=a1, b=b1))
with open(OUT, "w", encoding="utf-8") as w:
    w.write("# 話し合い %s\n\n## 1回目 Luna\n%s\n\n## 1回目 Nemotron\n%s\n\n## 2回目 Luna\n%s\n\n## 2回目 Nemotron\n%s\n"
            % (time.strftime("%F %H:%M"), a1, b1, a2, b2))
print("→", OUT, "Luna", len(a1), len(a2), "字 / Nemotron", len(b1), len(b2), "字")
