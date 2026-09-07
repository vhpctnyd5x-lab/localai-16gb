"""実験24: NVIDIA の複数モデルに、圧縮技術を一斉に聞いて突き合わせる。

【この調査の限界。読む前に必ず理解すること】
  NVIDIA の NIM モデルは **ウェブ検索ができない**。学習した知識から答えるだけ。
  したがって:
    ・論文名、著者、年、数値は **捏造されることがある**（もっともらしい嘘が出る）
    ・2024年以降の新しい手法は、モデルによっては知らない
  そこで **複数のモデルに同じ質問をぶつけ、何人が同じことを言ったかで信頼度を測る**。
  3モデル以上が独立に挙げた手法は、実在する可能性が高い。1モデルだけのものは要検証。

  つまりこれは「検索」ではなく「複数の専門家への聞き取り」。
  出てきた論文名は、必ず自分の目で実在を確かめてから使うこと。

【質問の設計】
  一般論を聞いても役に立たない。**我々の状況を全部渡してから**聞く。
  CPUのみ / numpy / 1.15bit / 実装済みの手札 / 欠けている工程 まで書いて、
  「この条件で使えるもの」に絞らせる。
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/Volumes/Mac Windows/LocalAI/kernel")
import nvidia

OUT = os.path.join(HERE, "results")
os.makedirs(OUT, exist_ok=True)

# 我々の状況。毎回これを頭に付ける
JOKYO = """【私の状況】
・目的: LLM(qwen2.5-coder 3B)を **2ビット未満** に圧縮しつつ、賢さを保ちたい
・実測: 1.154bit まで削れたが PPL が 5.58 → 4267 に崩壊。出力は "n n n n..." の繰り返し
・環境: **Intel Mac / CPU のみ / GPU も CUDA も無い / RAM 16GB / numpy で自作**
        PyTorch の学習ループは回せない。層ごとに閉じた計算なら回せる
・実装済みの手札:
   低ランク分解＋残差ベクトル量子化 / 誤差補償(GPTQ, 厳密解と15桁一致) /
   トレリス符号化(QTIP方式, シャノン限界まで2%) / アダマール回転(因子の内側) /
   チャンネル重要度スケーリング(本物のimatrix使用) / エントロピー符号化 /
   層ごとのビット配分(レート歪み配分, 今日実装)
・**欠けていると分かっている工程**: 出力の再構成・知識蒸留（元モデルの出力に合わせ込む）
・分かっている教訓: 重み誤差は出力誤差と無相関(順位相関 -0.111)。重み誤差で判断してはいけない
"""

SHITSUMON = [
    ("01_蒸留",
     JOKYO + """
【質問】
**GPUなし・numpyだけ**で実装できる「ブロック単位の出力再構成／知識蒸留」の
具体的なアルゴリズムを、実装できる粒度で教えてください。

各手法について:
  ■ 手法名（論文名があれば。**自信が無ければ「論文名は不確か」と正直に書くこと**）
  何をするか（3行以内）
  なぜ効くか（1行）
  CPUで回るか（計算量。層あたりの目安）
  実装の要点（擬似コードか式で。numpyで書ける粒度）

GDN/AdaRound/BRECQ/QuaRot などの名前を知っていれば、それも含めて。
**知らないことは知らないと書いてください。捏造は最も困ります。**"""),

    ("02_極低ビット",
     JOKYO + """
【質問】
**2ビット未満**の量子化で、いま世界で実際に効いているとされる手法を、
効果の大きい順に挙げてください。私が既に持っている手札（上記）は除外してください。

各手法について:
  ■ 手法名（**自信が無ければ「不確か」と明記**）
  中核のアイデア（3行以内）
  報告されている効果（数値があれば。**不確かなら「数値は不確か」と書く**）
  私のCPU環境で実装可能か（可/不可/条件つき）

特に「1bit前後でモデルが崩壊するのを防ぐ」ために効く手法を重視してください。"""),

    ("03_崩壊の原因",
     JOKYO + """
【質問】
1.15bit でPPLが 5.58 → 4267 に崩壊し、出力が "n n n n..." の繰り返しになりました。
**この症状から特定できる原因**を、可能性の高い順に挙げてください。

各原因について:
  ■ 原因
  なぜその症状が出るか（2行以内）
  **切り分ける方法**（私が実際に測れる具体的な手順。これが最重要）
  直し方

「出力が特定トークンの繰り返しになる」という症状は何を示唆しますか。
また、埋め込み層・出力層・LayerNorm・KVキャッシュなど、
**量子化してはいけない部分**を見落としている可能性はありますか。"""),

    ("04_落とし穴",
     JOKYO + """
【質問】
極低ビット量子化を自作する人が **必ずと言っていいほど踏む落とし穴** を挙げてください。
特に「数字は良くなっているのに、モデルは壊れている」という状況を生む原因。

各項目:
  ■ 落とし穴
  なぜ起きるか（2行以内）
  気づく方法（測り方）
  避け方

私は既に「合成活性化で評価して手法の優劣が反転した」「重み誤差で判断していた」
の2つを踏んでいます。それ以外を教えてください。"""),
]

MODELS = ["super", "ultra", "code", "deep", "fast"]
RES = os.path.join(OUT, "survey.json")
done = json.load(open(RES)) if os.path.exists(RES) else {}


def say(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


for tag, q in SHITSUMON:
    for m in MODELS:
        key = f"{tag}|{m}"
        if key in done and done[key].get("答え"):
            say(f"[済] {key}")
            continue
        say(f"聞く: {tag} ← {m}")
        t0 = time.time()
        ans, err = None, None
        for kai in range(3):                     # 503(混雑)は時間をおけば通る
            try:
                ans = nvidia.ask(q, model=m, max_tokens=2400, timeout=300,
                                 temperature=0.3)
                break
            except Exception as e:
                err = str(e)[:150]
                say(f"   しくじり({kai+1}/3): {err}")
                time.sleep(10 * (kai + 1))
        done[key] = {"問": tag, "モデル": m, "答え": ans, "error": err,
                     "秒": round(time.time() - t0)}
        json.dump(done, open(RES, "w"), ensure_ascii=False, indent=1)
        if ans:
            say(f"   → {len(ans)}文字 ({done[key]['秒']}秒)")

# ---- 読める形にまとめる ----
md = ["# 実験24: NVIDIA 複数モデルへの聞き取り",
      "",
      "**重要**: NVIDIAのモデルはウェブ検索ができない。学習知識から答えているだけなので、",
      "**論文名・数値は捏造されうる**。複数モデルが独立に同じことを言った項目ほど信頼できる。",
      "実際に使う前に、必ず自分で実在を確かめること。", ""]
for tag, _ in SHITSUMON:
    md.append(f"\n---\n\n# {tag}\n")
    for m in MODELS:
        d = done.get(f"{tag}|{m}")
        if not d:
            continue
        md.append(f"\n## モデル: {m}\n")
        md.append(d["答え"] if d.get("答え") else f"（失敗: {d.get('error')}）")
open(os.path.join(OUT, "survey.md"), "w", encoding="utf-8").write("\n".join(md))
say(f"まとめ: {os.path.join(OUT,'survey.md')}")
ok = sum(1 for v in done.values() if v.get("答え"))
say(f"完了 {ok}/{len(SHITSUMON)*len(MODELS)} 件")
