#!/usr/bin/env python3
"""qwen35moe の専門家を、imatrix の使用回数順に残す（再量子化しない）。

例（モデル起動・imatrix 作成は、頭脳を使っていない時に別途行う）:
  export PYTHONPATH=~/LocalAI_mirror/llama-koukai/src/gguf-py
  PY=~/LocalAI_mirror/goi_venv/bin/python3
  "$PY" -B dougu/kazoe_bun.py
  ~/LocalAI_mirror/llama-koukai/src/build/bin/llama-imatrix \
    -m "$MODEL" -f dougu/kekka/kazoe_bun.txt -c 512 \
    --output-format gguf -o dougu/kekka/kazoe_imatrix.gguf
  "$PY" -B dougu/senmonka_kezuru.py --model "$MODEL" \
    --imatrix dougu/kekka/kazoe_imatrix.gguf --keep 192 --drop-mtp \
    --out dougu/kekka/qwen35-192.gguf
  "$PY" -B dougu/tameshi_kezuru.py

出力と同名の .experts.json に、新番号順の元の専門家番号を保存する。
counts は gate/up/down の利用可能な記録間で一致を確認し、重複加算しない。
同数なら各記録の in_sum2 の総和、さらに同じなら元番号で決める。
MTP を使わず集めた imatrix では MTP の統計がないため --drop-mtp が必要。
MTP 除去の根拠: llama-model.cpp:1230-1232、llama-hparams.cpp:347-349、
models/qwen35moe.cpp:195-200（総層数から NextN を引き、末尾だけを MTP として読む）。
品質・実際のロードは別途検証する。元モデル・本番への書き込みは禁止。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

import numpy as np
import gguf

ARCH = "qwen35moe"
EXPERTS = ("ffn_gate_exps", "ffn_up_exps", "ffn_down_exps")
LAYER_ARRAYS = {
    "feed_forward_length", "expert_feed_forward_length", "expert_used_count",
    "attention.head_count", "attention.head_count_kv", "attention.recurrent_layers",
}


def value(reader, key, default=None):
    field = reader.fields.get(key)
    return field.contents() if field is not None else default


def choose_experts(stats, layer, count, keep):
    counts = None
    energy = np.zeros(count, dtype=np.float64)
    sources = []
    for kind in EXPERTS:
        name = f"blk.{layer}.{kind}.weight"
        ct, sm = stats.get(name + ".counts"), stats.get(name + ".in_sum2")
        if ct is None and sm is None:
            continue
        if ct is None or sm is None:
            raise ValueError(f"imatrix の counts/in_sum2 が片方だけ: {name}")
        if ct.tensor_type != gguf.GGMLQuantizationType.F32 or sm.tensor_type != gguf.GGMLQuantizationType.F32:
            raise ValueError(f"imatrix は F32 が必要: {name}")
        c = np.asarray(ct.data, dtype=np.float64).reshape(-1)
        if len(c) != count or list(sm.shape)[-1] != count or len(sm.shape) != 2:
            raise ValueError(f"imatrix の専門家数/形が不一致: {name}")
        s = np.asarray(sm.data, dtype=np.float64).reshape(count, -1)
        if not np.isfinite(c).all() or not np.isfinite(s).all() or (c < 0).any() or (s < 0).any():
            raise ValueError(f"imatrix に負値/非有限値: {name}")
        if counts is not None and not np.array_equal(counts, c):
            raise ValueError(f"gate/up/down の counts が不一致: blk.{layer}")
        counts = c
        energy += s.sum(axis=1)
        sources.append(name)
    if counts is None or not counts.any():
        raise ValueError(f"blk.{layer} の使用統計がない（MTP なら --drop-mtp）")
    ids = np.lexsort((np.arange(count), -energy, -counts))[:keep].tolist()
    return ids, {"sources": sources, "counts": counts[ids].tolist(),
                 "in_sum2_total": energy[ids].tolist(),
                 "zero_count_kept": int((counts[ids] == 0).sum())}


def expert_axis(tensor, count):
    """GGML の次元順。量子化のブロックを壊す配置は拒否する。"""
    name = tensor.name.split(".", 2)[-1]
    shape = list(map(int, tensor.shape))
    if any(name == f"{kind}.weight" for kind in EXPERTS):
        if len(shape) != 3 or shape[-1] != count:
            raise ValueError(f"専門家の次元が一番外側でない: {tensor.name} {shape}")
        return len(shape) - 1
    if name == "ffn_gate_inp.weight":
        if len(shape) != 2:
            raise ValueError(f"router の形が不明: {tensor.name} {shape}")
        # 正式な qwen35moe は [n_embd, n_expert]。転置した非量子化も扱う。
        if shape[1] == count:
            return 1
        if shape[0] == count:
            if tensor.tensor_type not in (gguf.GGMLQuantizationType.F32, gguf.GGMLQuantizationType.F16):
                raise ValueError(f"量子化 router の内側次元は切れない: {tensor.name}")
            return 0
        raise ValueError(f"router に専門家次元がない: {tensor.name} {shape}")
    if (("exps" in name and name.endswith(".bias"))
            or name in ("ffn_gate_inp.bias", "exp_probs_b.bias", "exp_probs_b")):
        if shape[-1] != count:
            raise ValueError(f"専門家 bias の形が不明: {tensor.name} {shape}")
        return len(shape) - 1
    # 未知の専門家別テンソルを黙ってコピーしない。
    if "exps" in name or "exp_probs_b" in name:
        raise ValueError(f"未対応の専門家テンソル: {tensor.name}")
    return None


def tensor_bytes(tensor, ids, axis):
    raw = tensor.data.view(np.uint8).reshape(-1)
    if axis is None:
        return raw
    shape = list(map(int, tensor.shape))
    if axis == len(shape) - 1:
        if tensor.n_bytes % shape[-1]:
            raise ValueError(f"専門家バイト境界が不正: {tensor.name}")
        return np.ascontiguousarray(raw.reshape(shape[-1], -1)[ids]).reshape(-1)
    # 内側の router は F32/F16 のみ。GGUFReader.data は GGML 順の逆。
    data = tensor.data.reshape(tuple(reversed(shape)))
    return np.ascontiguousarray(np.take(data, ids, axis=len(shape) - 1 - axis)).view(np.uint8).reshape(-1)


def safe_output(path):
    path = Path(path).expanduser().resolve()
    for root in (Path.home() / "LocalAI_mirror/models", Path.home() / "LocalAI_mirror/kernel"):
        if path.is_relative_to(root.resolve()):
            raise ValueError(f"読み取り専用の場所には出力しない: {root}")
    if path.exists():
        raise FileExistsError(f"既存の出力は上書きしない: {path}")
    return path


def prune(model, imatrix, keep, drop_mtp, out):
    model, imatrix = Path(model).expanduser().resolve(), Path(imatrix).expanduser().resolve()
    out = safe_output(out)
    selection_path = safe_output(out.with_suffix(".experts.json"))
    if out in (model, imatrix) or selection_path in (model, imatrix):
        raise ValueError("入力を出力に指定できない")
    reader = gguf.GGUFReader(model)
    im = gguf.GGUFReader(imatrix)
    if reader.byte_order != "I" or im.byte_order != "I":
        raise ValueError("この道具は native-endian GGUF のみ対応")
    if value(reader, "general.architecture") != ARCH:
        raise ValueError("qwen35moe のモデルが必要")
    if value(reader, "split.count", 1) != 1:
        raise ValueError("分割 GGUF は先に llama-gguf-split --merge する")
    if value(im, "general.type") != "imatrix":
        raise ValueError("llama-imatrix の GGUF (--output-format gguf) が必要")
    count = int(value(reader, f"{ARCH}.expert_count"))
    layers = int(value(reader, f"{ARCH}.block_count"))
    mtp = int(value(reader, f"{ARCH}.nextn_predict_layers", 0))
    if not 0 <= mtp < layers:
        raise ValueError("NextN の層数が不正")
    remaining = layers - mtp if drop_mtp else layers
    used = value(reader, f"{ARCH}.expert_used_count")
    used_values = used if isinstance(used, list) else [used]
    if not used_values or any(v is None for v in used_values):
        raise ValueError("expert_used_count がない")
    if len(used_values) > 1 and len(used_values) != layers:
        raise ValueError("expert_used_count 配列の長さが層数と違う")
    minimum = max(used_values[:remaining])
    if not minimum <= keep <= count:
        raise ValueError(f"--keep は expert_used_count={minimum} 以上、{count} 以下")
    stats = {t.name: t for t in im.tensors}
    selected, details = {}, {}
    for layer in range(remaining):
        selected[layer], details[layer] = choose_experts(stats, layer, count, keep)
    tensors = {t.name: t for t in reader.tensors}
    for layer in range(remaining):
        for name in (*[f"{kind}.weight" for kind in EXPERTS], "ffn_gate_inp.weight"):
            if f"blk.{layer}.{name}" not in tensors:
                raise ValueError(f"必須テンソルがない: blk.{layer}.{name}")
    # 書き込み前に全ての形と出力バイト数を確認する。
    plan = []
    removed = []
    for tensor in reader.tensors:
        match = re.match(r"^blk\.(\d+)\.", tensor.name)
        layer = int(match[1]) if match else None
        if layer is not None and layer >= layers:
            raise ValueError(f"block_count 外のテンソル: {tensor.name}")
        if drop_mtp and layer is not None and layer >= remaining:
            removed.append(tensor.name)
            continue
        axis = expert_axis(tensor, count) if layer is not None else None
        shape = list(map(int, tensor.shape))
        nbytes = tensor.n_bytes
        if axis is not None:
            if nbytes % count:
                raise ValueError(f"専門家バイト境界が不正: {tensor.name}")
            shape[axis] = keep
            nbytes = nbytes // count * keep
        plan.append((tensor, layer, axis, shape, nbytes))
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=out.name + ".", suffix=".part", dir=out.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    writer = gguf.GGUFWriter(tmp, ARCH)
    try:
        writer.data_alignment = reader.alignment
        writer.remove_key("general.architecture")  # 元の値と型を下でそのまま写す
        for key, field in reader.fields.items():
            if key.startswith("GGUF.") or key.startswith("split."):
                continue  # reader 内部値・単一ファイル化で無効になる分割情報
            val = field.contents()
            if key == f"{ARCH}.expert_count":
                val = keep
            elif drop_mtp and key == f"{ARCH}.block_count":
                val = remaining
            elif drop_mtp and key == f"{ARCH}.nextn_predict_layers":
                val = 0
            elif drop_mtp and key.removeprefix(ARCH + ".") in LAYER_ARRAYS and isinstance(val, list):
                if len(val) != layers:
                    raise ValueError(f"層別付帯情報の長さが不正: {key}")
                val = val[:remaining]
            subtype = field.types[-1] if field.types[0] == gguf.GGUFValueType.ARRAY else None
            writer.add_key_value(key, val, field.types[0], subtype)
        if drop_mtp and f"{ARCH}.nextn_predict_layers" not in reader.fields:
            writer.add_uint32(f"{ARCH}.nextn_predict_layers", 0)
        for tensor, _, _, shape, nbytes in plan:
            # dtype=F32 は writer の uint8→量子化形状再解釈を避けるため。
            # 実際の型は raw_dtype、実際のバイト数は nbytes で渡す。
            writer.add_tensor_info(tensor.name, tuple(reversed(shape)), np.dtype(np.float32),
                                   nbytes, raw_dtype=tensor.tensor_type)
        writer.write_header_to_file()
        writer.write_kv_data_to_file()
        writer.write_ti_data_to_file()
        for tensor, layer, axis, _, _ in plan:
            data = tensor_bytes(tensor, selected.get(layer), axis)
            writer.write_tensor_data(data)
            del data  # 最大でも元テンソル1個分。全モデルを RAM に溜めない。
        writer.close()
        report = {"model": str(model), "imatrix": str(imatrix), "keep": keep,
                  "expert_used_count": used_values[:remaining] if isinstance(used, list) else used,
                  "drop_mtp": drop_mtp, "block_count_before": layers, "block_count_after": remaining,
                  "nextn_predict_layers_after": 0 if drop_mtp else mtp,
                  "ranking": "counts desc, sum(in_sum2) desc, original id asc",
                  "layers": {str(k): v for k, v in selected.items()},
                  "statistics": {str(k): v for k, v in details.items()},
                  "removed_tensors": removed, "bytes_before": model.stat().st_size,
                  "bytes_after": tmp.stat().st_size}
        # 出力が完成してから公開。元ファイルと既存出力は上書きしない。
        with selection_path.open("x", encoding="utf-8") as fp:
            json.dump(report, fp, ensure_ascii=False, indent=2)
            fp.write("\n")
        os.link(tmp, out)
        print(f"{report['bytes_before']:,} → {report['bytes_after']:,} bytes "
              f"({report['bytes_before']/1e9:.3f} → {report['bytes_after']/1e9:.3f} GB)")
        print(f"モデル: {out}\n専門家一覧: {selection_path}")
        return report
    finally:
        writer.close()
        tmp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--imatrix", type=Path, required=True)
    parser.add_argument("--keep", type=int, required=True)
    parser.add_argument("--drop-mtp", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        prune(args.model, args.imatrix, args.keep, args.drop_mtp, args.out)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"エラー: {exc}\n")


if __name__ == "__main__":
    main()
