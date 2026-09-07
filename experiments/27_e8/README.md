# 実験33: E8格子量子化（2026-09-02）

- `test_e8.py`      復号器の検算（テータ級数・最近点・重み付き最近点・形状利得 0.65dB）
- `test_e8_ball.py` 球外入力の量子化が総当たりと一致するか
- `cmp_e8.py`       最初の比較（球外処理が弱かった版の結果 = cmp_e8_old_ball_handling.out）
- `cmp_e8f.py`      最終比較（attn_output / ffn_down、結果 = cmp_e8f.out）

結論は RESULTS.md の実験33を参照。使い方: `LATTICE=e8 R2=10 K=8` を quantize4.py に渡す。
