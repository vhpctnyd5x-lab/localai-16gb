#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hayaku.py -- Qwen3-MoE の順伝播を差し替えて速くする。

  なぜ遅いか（2026-09-07 実測 97.1秒/step・GPU利用率9%）:
    transformers の Qwen3MoeSparseMoeBlock は、その層で使われた専門家を
    1個ずつ Python の for で回す。しかも
        for expert_idx in expert_hit:      # expert_idx は「テンソル」
            expert_layer = self.experts[expert_idx]
    と**テンソルで添字を引く**ので、1回ごとに GPU→CPU の同期が起きる。
    128専門家 × 48層 = 6,144回/順伝播。GPUは遊んでいて、同期待ちで時間が溶ける。

  直しかた（計算そのものは1つも変えない）:
    ・どの専門家が何件持つかを bincount で数え、**1層につき1回だけ**同期する
    ・専門家の添字は Python の int にする（同期しない）
    ・並べ替えを1回やって、専門家ごとの区間を切り出すだけにする

  ★ 使う前に必ず  python3 hayaku.py --check  で元の実装と答えが一致することを見る。
    ここが違っていると、学習が静かに壊れる。
"""
import torch


def _atarashii_forward(self, hidden_states):
    katachi = hidden_states.shape
    hidden_states = hidden_states.view(-1, katachi[-1])
    router_logits = self.gate(hidden_states)
    routing_weights = torch.nn.functional.softmax(router_logits, dim=1, dtype=torch.float)
    routing_weights, selected_experts = torch.topk(routing_weights, self.top_k, dim=-1)
    if self.norm_topk_prob:
        routing_weights = routing_weights / routing_weights.sum(dim=-1, keepdim=True)
    routing_weights = routing_weights.to(hidden_states.dtype)

    deki = torch.zeros_like(hidden_states)

    hira = selected_experts.reshape(-1)                     # [T*k] どの専門家に行くか
    jun = torch.argsort(hira, stable=True)                  # 専門家ごとにまとめる
    kazu = torch.bincount(hira, minlength=self.num_experts).tolist()   # ★同期はここ1回だけ
    tok = torch.div(jun, self.top_k, rounding_mode='floor')  # 何番目のトークンか
    waku = jun % self.top_k                                  # k個のうち何番目か

    hajime = 0
    for e in range(self.num_experts):
        c = kazu[e]
        if c == 0:
            continue
        t = tok[hajime:hajime + c]
        w = waku[hajime:hajime + c]
        hajime += c
        deki.index_add_(0, t,
                        (self.experts[e](hidden_states[t]) *
                         routing_weights[t, w, None]).to(hidden_states.dtype))
    return deki.view(katachi), router_logits


def ateru():
    """差し替える。戻り値は元の forward（戻したいとき用）"""
    from transformers.models.qwen3_moe import modeling_qwen3_moe as M
    moto = M.Qwen3MoeSparseMoeBlock.forward
    M.Qwen3MoeSparseMoeBlock.forward = _atarashii_forward
    return moto


def _check():
    """元の実装と答えが一致するか、小さな模型で確かめる"""
    from transformers.models.qwen3_moe import modeling_qwen3_moe as M
    from transformers.models.qwen3_moe.configuration_qwen3_moe import Qwen3MoeConfig
    torch.manual_seed(0)
    cfg = Qwen3MoeConfig(hidden_size=64, intermediate_size=128, moe_intermediate_size=32,
                         num_experts=16, num_experts_per_tok=4, num_hidden_layers=1,
                         num_attention_heads=4, num_key_value_heads=2, vocab_size=100)
    blk = M.Qwen3MoeSparseMoeBlock(cfg).eval()
    x = torch.randn(2, 7, 64)
    with torch.no_grad():
        moto_out, moto_log = M.Qwen3MoeSparseMoeBlock.forward(blk, x)
        ateru()
        atara_out, atara_log = blk(x)
    d1 = (moto_out - atara_out).abs().max().item()
    d2 = (moto_log - atara_log).abs().max().item()
    print(f"出力の差 {d1:.3e} / ルータの差 {d2:.3e}")
    ok = d1 < 1e-5 and d2 < 1e-6
    print("一致した。使ってよい。" if ok else "★一致しない。使ってはいけない。")
    return ok


if __name__ == '__main__':
    import sys
    raise SystemExit(0 if _check() else 1)


# ─────────────────────────────────────────────────────────────────────
#  VRAM を食っている本当の犯人は logits だった（2026-09-07 実測）
#
#  Qwen3 の語彙は 151,936。全位置ぶん logits を作ると、1065トークンで
#      1065 × 151936 × 4バイト(fp32) = 647 MB
#  さらに交差エントロピーの途中結果でその2〜3倍。**これだけで数GB。**
#  L4 の残り 5.25 GiB を、バッチ1でも食い潰す。
#
#  ところが損失が掛かるのは「答え」だけで、1件あたり約21トークン。
#  **損失の掛かる位置だけ lm_head に通せば、50分の1で済む。**
# ─────────────────────────────────────────────────────────────────────

def moto_wo_toru(model):
    """PEFT に包まれていても、素の ...ForCausalLM を取り出す"""
    return model.get_base_model() if hasattr(model, 'get_base_model') else model


def sonshitsu(model, input_ids, attention_mask, labels):
    """損失。全位置の logits を作らない版。"""
    moto = moto_wo_toru(model)
    out = moto.model(input_ids=input_ids, attention_mask=attention_mask)
    h = out.last_hidden_state[:, :-1, :]        # 1つずらす
    t = labels[:, 1:]
    m = t != -100                                # 答えの位置だけ
    if not bool(m.any()):
        return h.sum() * 0.0
    return torch.nn.functional.cross_entropy(moto.lm_head(h[m]).float(), t[m])
