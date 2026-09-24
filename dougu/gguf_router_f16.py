#!/usr/bin/env python3
"""GGUF 内の blk.*.ffn_gate_inp.weight (F32) だけを F16/BF16 に変換する。"""

import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "llama_src/gguf-py"))


def convert(source: Path, destination: Path, bf16: bool = False) -> int:
    import numpy as np
    from gguf import GGUFReader, GGUFWriter, GGMLQuantizationType as Type
    from gguf import GGUFValueType, GGUFEndian

    if source.resolve() == destination.resolve():
        raise ValueError("入力と出力が同じです")
    if destination.exists():
        raise FileExistsError(destination)
    reader = GGUFReader(source)
    arch = reader.fields["general.architecture"].contents()
    writer = GGUFWriter(destination, arch, endianess=reader.endianess)
    writer.remove_key("general.architecture")
    count = 0
    try:
        for name, field in reader.fields.items():
            if name.startswith("GGUF."):
                continue  # header の version/count は writer が生成する
            value = field.contents()
            subtype = field.types[-1] if field.types[0] == GGUFValueType.ARRAY else None
            writer.add_key_value(name, value, field.types[0], subtype)
            if name == "general.alignment":
                writer.data_alignment = int(value)
        for tensor in reader.tensors:
            if re.fullmatch(r"blk\.\d+\.ffn_gate_inp\.weight", tensor.name) and tensor.tensor_type == Type.F32:
                if bf16:
                    # IEEE BF16: round to nearest, ties to even; GGUF は uint16 bit 列で保持。
                    bits = np.asarray(tensor.data, dtype=np.float32).view(np.uint32)
                    rounded = bits + (np.uint32(0x7fff) + ((bits >> 16) & 1))
                    data = (rounded >> 16).astype(np.uint16)
                    dtype = Type.BF16
                else:
                    data = tensor.data.astype(np.float16)
                    dtype = Type.F16
                writer.add_tensor(tensor.name, data, raw_shape=tensor.data.shape, raw_dtype=dtype)
                count += 1
            else:
                # 量子化済みも含めて元の byte 列・GGML type・形を保つ。
                writer.add_tensor(tensor.name, tensor.data, raw_shape=tensor.data.shape,
                                  raw_dtype=tensor.tensor_type, tensor_endianess=reader.endianess)
        if count == 0:
            raise ValueError("F32 の blk.*.ffn_gate_inp.weight がありません")
        writer.write_header_to_file()
        writer.write_kv_data_to_file()
        writer.write_tensors_to_file()
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        writer.close()
    return count


def self_test():
    """小さな偽 GGUF で metadata・順序・型・値の往復を検査する。"""
    import tempfile
    import numpy as np
    from gguf import GGUFReader, GGUFWriter, GGMLQuantizationType as Type

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.gguf"
        w = GGUFWriter(source, "qwen3moe")
        w.add_string("general.name", "router test")
        w.add_array("tokenizer.ggml.tokens", ["a", "日本語", "<think>"])
        target = np.array([[0.1, -1.25, 3.5], [0.0, 10.2, -0.01]], dtype=np.float32)
        other = np.arange(6, dtype=np.float32).reshape(2, 3)
        w.add_tensor("blk.0.ffn_gate_inp.weight", target)
        w.add_tensor("blk.0.attn_q.weight", other)
        w.write_header_to_file()
        w.write_kv_data_to_file()
        w.write_tensors_to_file()
        w.close()
        original = GGUFReader(source)
        for bf16, tol in ((False, 0.004), (True, 0.04)):
            result = Path(tmp) / ("bf16.gguf" if bf16 else "f16.gguf")
            assert convert(source, result, bf16) == 1
            read = GGUFReader(result)
            assert list(read.fields) == list(original.fields)
            assert [t.name for t in read.tensors] == [t.name for t in original.tensors]
            for name in original.fields:
                assert read.fields[name].contents() == original.fields[name].contents()
            changed, unchanged = read.tensors
            assert tuple(changed.shape) == tuple(original.tensors[0].shape), (bf16, changed.data.shape, changed.shape)
            assert changed.tensor_type == (Type.BF16 if bf16 else Type.F16)
            values = (changed.data.view(np.uint16).astype(np.uint32) << 16).view(np.float32) if bf16 else changed.data.astype(np.float32)
            assert np.allclose(values, target, atol=tol, rtol=0)
            assert unchanged.tensor_type == Type.F32 and unchanged.data.tobytes() == other.tobytes()
        print("GGUF 往復: F16/BF16、形・型・値・メタデータ・順序 OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("destination", nargs="?", type=Path)
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.source or not args.destination:
        parser.error("元.gguf 新.gguf が必要です")
    print(f"変換した案内係: {convert(args.source, args.destination, args.bf16)} 個")


if __name__ == "__main__":
    main()
