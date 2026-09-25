#!/usr/bin/env python3
"""Prune MoE FFN channels in a Q8_0 GGUF using llama.cpp imatrix data."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "llama_src" / "gguf-py"))
import gguf  # noqa: E402


def metadata_value(field):
    value = field.contents()
    if field.types[0] == gguf.GGUFValueType.ARRAY:
        return value, field.types[-1]
    return value, None


def make_writer(reader, out_path, replacement_ffn=None):
    arch = str(reader.get_field("general.architecture").contents())
    writer = gguf.GGUFWriter(out_path, arch)
    for key, field in reader.fields.items():
        if key in {"GGUF.version", "GGUF.tensor_count", "GGUF.kv_count", "general.architecture"}:
            continue
        val, subtype = metadata_value(field)
        if replacement_ffn and key == f"{arch}.expert_feed_forward_length":
            val = replacement_ffn
        writer.add_key_value(key, val, field.types[0], subtype)
    return writer


def save_gguf(reader, out_path, tensors, replacement_ffn=None):
    writer = make_writer(reader, out_path, replacement_ffn)
    for name, (array, raw_shape, raw_dtype) in tensors.items():
        writer.add_tensor(name, array, raw_shape=raw_shape, raw_dtype=raw_dtype,
                          tensor_endianess=reader.endianess)
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()


def read_imatrix(path):
    """Return name -> sums/counts, accepting both GGUF and legacy formats."""
    p = Path(path)
    with p.open("rb") as f:
        magic = f.read(4)
    if magic == b"GGUF":
        reader = gguf.GGUFReader(path)
        result = {}
        for t in reader.tensors:
            if t.name.endswith(".in_sum2"):
                base = t.name[:-8]
                result.setdefault(base, {})["sums"] = t.data.astype(np.float32).reshape(-1)
            elif t.name.endswith(".counts"):
                base = t.name[:-7]
                result.setdefault(base, {})["counts"] = t.data.astype(np.float32).reshape(-1)
        for name, e in result.items():
            if "sums" not in e or "counts" not in e:
                raise ValueError(f"imatrix entry {name} lacks sums or counts")
        return ("gguf", reader, result)

    # llama.cpp legacy imatrix: entries followed by call count and source filename.
    import struct
    entries = {}
    footer = b""
    with p.open("rb") as f:
        raw = f.read(4)
        if len(raw) != 4:
            raise ValueError("empty legacy imatrix")
        (n_entries,) = struct.unpack("<i", raw)
        for _ in range(n_entries):
            (length,) = struct.unpack("<i", f.read(4))
            name = f.read(length).decode("utf-8")
            ncall, nval = struct.unpack("<ii", f.read(8))
            sums = np.frombuffer(f.read(nval * 4), dtype="<f4").copy()
            entries[name] = {"sums": sums, "counts": np.array([ncall], dtype=np.float32)}
        trailer = f.read()
        if trailer:
            if len(trailer) < 8:
                raise ValueError("truncated legacy imatrix footer")
            (name_len,) = struct.unpack_from("<i", trailer, 4)
            if name_len < 0 or len(trailer) != 8 + name_len:
                raise ValueError("invalid legacy imatrix footer")
            trailer[8:].decode("utf-8")
            footer = trailer
    return ("legacy", footer, entries)


def write_imatrix(kind, reader, entries, path):
    if kind == "legacy":
        import struct
        with Path(path).open("wb") as f:
            f.write(struct.pack("<i", len(entries)))
            for name, entry in entries.items():
                encoded = name.encode("utf-8")
                sums = np.asarray(entry["sums"], dtype="<f4")
                count = int(np.asarray(entry["counts"]).reshape(-1)[0])
                f.write(struct.pack("<i", len(encoded))); f.write(encoded)
                f.write(struct.pack("<ii", count, len(sums))); f.write(sums.tobytes())
            if reader:
                f.write(reader)
        return
    tensors = {}
    for t in reader.tensors:
        suffix = ".in_sum2" if t.name.endswith(".in_sum2") else ".counts"
        base = t.name[:-len(suffix)]
        values = entries.get(base)
        data = values["sums"] if suffix == ".in_sum2" else values["counts"]
        values = np.asarray(data, dtype=np.float32).reshape(-1)
        tensors[t.name] = (values, (len(values),), gguf.GGMLQuantizationType.F32)
    save_gguf(reader, path, tensors)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--imatrix", required=True)
    ap.add_argument("--imatrix-out", required=True)
    ap.add_argument("--frac", type=float, required=True)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    if not 0 < args.frac < 1:
        ap.error("--frac must be between 0 and 1")

    model = gguf.GGUFReader(args.input)
    im_kind, im_reader, im_entries = read_imatrix(args.imatrix)
    by_name = {t.name: t for t in model.tensors}
    down_names = sorted(n for n in by_name if re.fullmatch(r"blk\.\d+\.ffn_down_exps\.weight", n))
    if not down_names:
        raise ValueError("no blk.N.ffn_down_exps.weight tensors found")
    plans = {}
    new_im = {k: {q: v.copy() for q, v in ent.items()} for k, ent in im_entries.items()}
    common_keep = None
    layers = set()
    for down_name in down_names:
        down = by_name[down_name]
        if down.tensor_type != gguf.GGMLQuantizationType.Q8_0:
            raise ValueError(f"{down_name} is {down.tensor_type.name}, expected Q8_0")
        layer = int(re.search(r"blk\.(\d+)", down_name).group(1))
        layers.add(layer)
        raw_shape = tuple(int(x) for x in down.shape)
        # GGUF dimensions use ggml order. The down tensor is [neurons, embedding, experts].
        neurons, embedding, experts = raw_shape
        entry_name = down_name + ".in_sum2"
        base_name = down_name
        if base_name not in im_entries and entry_name.removesuffix(".in_sum2") in im_entries:
            base_name = entry_name.removesuffix(".in_sum2")
        if base_name not in im_entries:
            raise ValueError(f"imatrix has no entry for {down_name}")
        scores = np.asarray(im_entries[base_name]["sums"], dtype=np.float64)
        if scores.size != experts * neurons:
            raise ValueError(f"{base_name} imatrix has {scores.size} values; expected experts*neurons={experts*neurons}")
        scores = scores.reshape(experts, neurons)
        keep_n = max(32, int(round((neurons * (1.0 - args.frac)) / 32.0)) * 32)
        keep_n = min(neurons, keep_n)
        if common_keep is not None and common_keep != keep_n:
            raise ValueError("expert_ffn dimensions differ across layers")
        common_keep = keep_n
        indices = np.stack([np.argsort(row, kind="stable")[-keep_n:] for row in scores])
        indices.sort(axis=1)
        plans[layer] = (indices, raw_shape, keep_n)

    writer = make_writer(model, args.output, common_keep)
    for t in model.tensors:
        match = re.fullmatch(r"blk\.(\d+)\.ffn_(down|gate|up)_exps\.weight", t.name)
        raw_dims = list(map(int, t.shape))
        if match:
            layer = int(match.group(1))
            if layer not in plans:
                raise ValueError(f"no down expert tensor found for {t.name}")
            raw_dims[0 if match.group(2) == "down" else 1] = plans[layer][2]
            elements = int(np.prod(raw_dims))
            if elements % 32:
                raise ValueError(f"Q8_0 tensor size is not a multiple of 32: {t.name}")
            nbytes = elements // 32 * 34
            raw_dtype = gguf.GGMLQuantizationType.Q8_0
        else:
            nbytes = t.data.nbytes
            raw_dtype = t.tensor_type
        # add_tensor_info treats uint8 shapes as packed-byte shapes; these are element shapes.
        writer.add_tensor_info(t.name, tuple(reversed(raw_dims)), np.dtype(np.float32), nbytes, raw_dtype=raw_dtype)
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()

    def tensor_data(t):
        name = t.name
        match = re.fullmatch(r"blk\.(\d+)\.ffn_(down|gate|up)_exps\.weight", name)
        if not match:
            return t.data  # GGUFReader data is a view of its file mmap.
        layer = int(match.group(1)); kind = match.group(2)
        if layer not in plans:
            raise ValueError(f"no down expert tensor found for {name}")
        ids, raw_shape, keep_n = plans[layer]
        tensor_raw_shape = tuple(int(x) for x in t.shape)
        if kind == "down":
            deq = gguf.dequantize(t.data, t.tensor_type).reshape(tuple(reversed(raw_shape)))
            # numpy layout [expert, embedding, neurons]
            pruned = np.stack([deq[e][:, ids[e]] for e in range(len(ids))])
            quantized = gguf.quantize(pruned, gguf.GGMLQuantizationType.Q8_0)
            base = name
            entry = new_im.get(base)
            if entry:
                old = entry["sums"].reshape(len(ids), -1)
                entry["sums"] = np.stack([old[e, ids[e]] for e in range(len(ids))]).reshape(-1)
                if len(entry["counts"]) == old.size:
                    oldc = entry["counts"].reshape(old.shape)
                    entry["counts"] = np.stack([oldc[e, ids[e]] for e in range(len(ids))]).reshape(-1)
        else:
            arr = gguf.dequantize(t.data, t.tensor_type).reshape(tuple(reversed(tensor_raw_shape)))
            if arr.shape[0] != len(ids) or arr.shape[1] < max(ids.flatten()) + 1:
                raise ValueError(f"unexpected {kind} expert tensor shape: {arr.shape}")
            pruned = np.stack([arr[e, ids[e], :] for e in range(len(ids))])
            quantized = gguf.quantize(pruned, gguf.GGMLQuantizationType.Q8_0)
        return quantized

    for t in model.tensors:
        writer.write_tensor_data(tensor_data(t), tensor_endianess=model.endianess)
    writer.close()
    write_imatrix(im_kind, im_reader, new_im, args.imatrix_out)
    old_width = next(iter(plans.values()))[1][0]
    print(f"pruned {len(layers)} layers: expert FFN width {old_width} -> {keep_n}")


if __name__ == "__main__":
    main()
