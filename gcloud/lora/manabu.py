#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""manabu.py -- 教材で Qwen3-30B-A3B に LoRA を焼く（L4 24GB / QLoRA 4bit）

★ なぜ attention だけに当てるのか（ここを変えると全部が無駄になる）
   手元の本番モデル Qwen3-30B-REAP96-mix-Q2_K.gguf は
   専門家(*_exps.weight)とルータ(ffn_gate_inp.weight)**だけ**を削ったもの。
   attention (q/k/v/o) は元の Qwen3-30B-A3B と1バイトも違わない。
   だから128専門家の元モデルで attention だけ学べば、
   96専門家の手元モデルに**そのまま乗る**。
   専門家に当てると番号がずれて乗らない。--target を触らないこと。

★ 形は本番と完全に一致させてある
   system : "JSON をひとつだけ返す係です。説明を書かないこと。"（dougu.py と同一）
   kernel は /v1/chat/completions を chat_template_kwargs={"enable_thinking":false}
   で叩くので、生成の頭は  <|im_start|>assistant\n<think>\n\n</think>\n\n  になる。
   ここを外すと学習と推論がずれて効かない。

★ 損失は「答え」だけに掛ける
   頼み文は毎回同じ765字の頭を含む。そこに損失を掛けると頭を丸暗記するだけ。
"""
import argparse, json, os, sys, time, math

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base',   default='Qwen/Qwen3-30B-A3B')
    ap.add_argument('--data',   default='kyouzai.jsonl')
    ap.add_argument('--out',    default='lora_out')
    ap.add_argument('--epochs', type=float, default=3.0)
    ap.add_argument('--lr',     type=float, default=1e-4)
    ap.add_argument('--rank',   type=int, default=16)
    ap.add_argument('--alpha',  type=int, default=32)
    ap.add_argument('--dropout',type=float, default=0.05)
    ap.add_argument('--bs',     type=int, default=1)
    ap.add_argument('--accum',  type=int, default=8)
    ap.add_argument('--maxlen', type=int, default=1280)
    ap.add_argument('--save-steps', type=int, default=20)
    ap.add_argument('--target', default='q_proj,k_proj,v_proj,o_proj')
    ap.add_argument('--probe',  type=int, default=0, help='N ステップだけ回して速度とVRAMを見る')
    ap.add_argument('--gcs',    default='', help='gs://... 途中保存の同期先（SPOT対策）')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--nama', action='store_true',
                    help='MoE の順伝播を差し替えない（元のまま。遅い）')
    a = ap.parse_args()

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig,
                              TrainingArguments, Trainer, TrainerCallback)
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    print(f"torch {torch.__version__} / cuda {torch.version.cuda} / GPU {torch.cuda.get_device_name(0)}", flush=True)

    # ★ MoE の順伝播を差し替えて速くする（計算は1つも変えない。hayaku.py の説明を読むこと）
    #   元の実装は専門家をテンソル添字で引くので 1層128回の GPU→CPU 同期が起きる。
    #   差し替え版は 1層1回にまとめる。答えはビット単位で一致することを確認済み。
    if not a.nama:
        global hayaku
        import hayaku
        hayaku.ateru()
        print("MoE の順伝播を差し替えた（hayaku.py）", flush=True)

    # ---------- 教材を、本番と同じ形のトークン列にする ----------
    tok = AutoTokenizer.from_pretrained(a.base, trust_remote_code=True)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token

    def kumitateru(msgs):
        """(input_ids, labels) を返す。labels は答えの部分だけ生かす。"""
        atama = tok.apply_chat_template(msgs[:-1], tokenize=False,
                                        add_generation_prompt=True,
                                        enable_thinking=False)
        kotae = msgs[-1]["content"] + "<|im_end|>"
        ai = tok(atama, add_special_tokens=False)["input_ids"]
        ki = tok(kotae, add_special_tokens=False)["input_ids"]
        ids = ai + ki
        lab = [-100] * len(ai) + ki[:]
        return ids[:a.maxlen], lab[:a.maxlen], len(ai)

    recs, kire = [], 0
    for line in open(a.data, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        ids, lab, nprompt = kumitateru(d["messages"])
        if len(ids) >= a.maxlen:
            kire += 1                       # maxlen で切れた ＝ 答えが落ちている恐れ
        recs.append({"input_ids": ids, "labels": lab})

    ln = [len(r["input_ids"]) for r in recs]
    nsup = sum(sum(1 for x in r["labels"] if x != -100) for r in recs)
    print(f"教材 {len(recs)}件 / 長さ 平均{sum(ln)/len(ln):.0f} 最長{max(ln)} / "
          f"maxlen({a.maxlen})で切れた {kire}件 / 損失の掛かるトークン {nsup}", flush=True)
    if kire:
        print(f"★注意: {kire}件が切れている。--maxlen を上げること。", flush=True)

    # ---------- 一番最初の1件を目で見られる形で出す（形のずれを人が確認するため）----------
    d0 = json.loads(open(a.data, encoding='utf-8').readline())
    a0 = tok.apply_chat_template(d0["messages"][:-1], tokenize=False,
                                 add_generation_prompt=True, enable_thinking=False)
    print("---- 生成の頭（末尾120字）----\n" + repr(a0[-120:]) + "\n----", flush=True)

    # ---------- モデル ----------
    bnb = BitsAndBytesConfig(load_in_4bit=True,
                             bnb_4bit_quant_type='nf4',
                             bnb_4bit_use_double_quant=True,
                             bnb_4bit_compute_dtype=torch.bfloat16)
    t0 = time.time()
    try:
        model = AutoModelForCausalLM.from_pretrained(
            a.base, quantization_config=bnb, dtype=torch.bfloat16,
            device_map={'': 0}, trust_remote_code=True, low_cpu_mem_usage=True)
    except TypeError:                        # 古い transformers は dtype= を知らない
        model = AutoModelForCausalLM.from_pretrained(
            a.base, quantization_config=bnb, torch_dtype=torch.bfloat16,
            device_map={'': 0}, trust_remote_code=True, low_cpu_mem_usage=True)
    print(f"読み込み {time.time()-t0:.0f}秒 / VRAM {torch.cuda.memory_allocated()/2**30:.2f} GiB", flush=True)

    model.config.use_cache = False
    # ★ prepare_model_for_kbit_training は使わない。
    #   あれは量子化されていない重み（埋め込みと lm_head）を fp32 に上げるが、
    #   ここでは両方とも凍っているので上げる意味がなく、**1.24 GiB を無駄にする**。
    #   欲しいのは下の2行だけ。use_reentrant=False は Trainer と同じ条件。
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.enable_input_require_grads()
    print(f"仕度のあと VRAM {torch.cuda.memory_allocated()/2**30:.2f} GiB", flush=True)

    lcfg = LoraConfig(r=a.rank, lora_alpha=a.alpha, lora_dropout=a.dropout,
                      bias='none', task_type='CAUSAL_LM',
                      target_modules=[s for s in a.target.split(',') if s])
    model = get_peft_model(model, lcfg)
    model.print_trainable_parameters()

    # ---------- 並べる ----------
    pad = tok.pad_token_id
    def matomeru(batch):
        n = max(len(b["input_ids"]) for b in batch)
        ii, ll, am = [], [], []
        for b in batch:
            k = n - len(b["input_ids"])
            ii.append(b["input_ids"] + [pad] * k)
            ll.append(b["labels"]    + [-100] * k)
            am.append([1] * len(b["input_ids"]) + [0] * k)
        return {"input_ids": torch.tensor(ii), "labels": torch.tensor(ll),
                "attention_mask": torch.tensor(am)}

    class Sokudo(TrainerCallback):
        """速さとVRAMを出す。SPOTで消える前に「あと何分か」が分かるように。"""
        def on_step_end(self, args, state, control, **kw):
            if state.global_step in (1, 2, 5) or state.global_step % 20 == 0:
                el = time.time() - self.t0
                sps = el / max(state.global_step, 1)
                nokori = (state.max_steps - state.global_step) * sps
                print(f"[{state.global_step}/{state.max_steps}] "
                      f"{sps:.1f}秒/step / VRAM {torch.cuda.max_memory_allocated()/2**30:.2f} GiB / "
                      f"残り約{nokori/60:.0f}分", flush=True)
        def on_train_begin(self, args, state, control, **kw):
            self.t0 = time.time()
        def on_save(self, args, state, control, **kw):
            if a.gcs:
                os.system(f"gsutil -q -m rsync -r {a.out} {a.gcs} >/dev/null 2>&1 &")

    steps_per_epoch = math.ceil(len(recs) / (a.bs * a.accum))
    targs = dict(output_dir=a.out,
                 per_device_train_batch_size=a.bs,
                 gradient_accumulation_steps=a.accum,
                 learning_rate=a.lr, lr_scheduler_type='cosine', warmup_ratio=0.05,
                 logging_steps=10, save_steps=a.save_steps, save_total_limit=3,
                 bf16=True, optim='paged_adamw_8bit',
                 gradient_checkpointing=True,
                 gradient_checkpointing_kwargs={'use_reentrant': False},
                 # ★0 にすること。1以上だと DataLoader が os.fork() する。
                 #   親は 57GB を読み込んだ直後で仮想メモリが巨大なので、
                 #   overcommit_memory=0 の既定だと fork が拒否される
                 #   （OSError: [Errno 12] Cannot allocate memory。GPUではなくホストのRAM）。
                 #   教材は先にトークン化してあるので、ワーカーは要らない。
                 report_to=[], seed=42, dataloader_num_workers=0,
                 # 長さの近いものを同じ塊にする。MoE は専門家の数で律速するので
                 # 詰め物(padding)は無駄でしかない。
                 group_by_length=True,
                 remove_unused_columns=False)
    if a.probe:
        targs['max_steps'] = a.probe
        targs['save_steps'] = 10**9
    else:
        targs['num_train_epochs'] = a.epochs

    class WagaTrainer(Trainer):
        """損失を自前で計算する。理由は hayaku.sonshitsu の説明を読むこと。
           （全位置ぶんの logits を作ると語彙15万×長さぶんで数GB飛ぶ）"""
        def compute_loss(self, model, inputs, return_outputs=False, **kw):
            return hayaku.sonshitsu(model, inputs['input_ids'],
                                    inputs['attention_mask'], inputs['labels'])

    Waga = Trainer if a.nama else WagaTrainer
    tr = Waga(model=model, args=TrainingArguments(**targs),
              train_dataset=recs, data_collator=matomeru, callbacks=[Sokudo()])
    print(f"1エポック {steps_per_epoch} step / 合計 約{int(steps_per_epoch*a.epochs)} step", flush=True)

    tr.train(resume_from_checkpoint=a.resume or None)

    if not a.probe:
        tr.save_model(a.out)
        tok.save_pretrained(a.out)
        print(f"書いた: {a.out}", flush=True)
        if a.gcs:
            os.system(f"gsutil -q -m rsync -r {a.out} {a.gcs}")

if __name__ == '__main__':
    main()
