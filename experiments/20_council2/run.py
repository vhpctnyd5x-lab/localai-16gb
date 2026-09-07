import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
import council
H = os.path.dirname(os.path.abspath(__file__))
B = open(os.path.join(H, "brief.md")).read()
M = [
 ("ビット配分", "llama",
  "あなたは混合精度量子化の実務者です。層ごとの感度の測り方と、平均ビット数制約下での"
  "配分アルゴリズムを、実装が軽い順に具体的に述べてください。日本語で。"),
 ("壊れやすい層", "super",
  "LLM量子化で特に壊れやすい層について、経験則と理由、何割を高精度に残すのが定石かを"
  "述べてください。日本語で。"),
 ("軽量再構成", "glm",
  "勾配降下を使わず閉じた式や少数回反復で層出力を合わせ込む手法を、計算コストと"
  "期待効果を添えて挙げてください。日本語で。"),
]
council.run(M, B, os.path.join(H, "out"), workers=2)
