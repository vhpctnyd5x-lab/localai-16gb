#!/usr/bin/env python3
"""GGUF の語彙・arch・専門家のメタデータと、語彙ファイルの札を照合する。"""

import argparse
import math
import os
from pathlib import Path
import re
import struct


SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
MIMO_REPO = "XiaomiMiMo/MiMo-V2.6-Distill-Qwen-9B"
Q36_TOKENIZER_SHA256 = "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42"
FORMATS = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}


def gguf_metadata(path: Path) -> dict:
    result = {}
    with path.open("rb") as f:
        file_size = os.fstat(f.fileno()).st_size
        def read(fmt):
            data = f.read(struct.calcsize(fmt))
            if len(data) != struct.calcsize(fmt):
                raise ValueError("GGUF のメタデータが途中で切れています")
            return struct.unpack(fmt, data)[0]

        def string():
            size = read("<Q")
            if size > 1_000_000:
                raise ValueError("GGUF のキーが長すぎます")
            data = f.read(size)
            if len(data) != size:
                raise ValueError("GGUF の文字列が途中で切れています")
            return data.decode("utf-8")

        def skip(kind):
            if kind in SIZES:
                f.seek(SIZES[kind], 1)
            elif kind == 8:
                size = read("<Q")
                f.seek(size, 1)
            elif kind == 9:
                item_kind, count = read("<I"), read("<Q")
                if item_kind in SIZES:
                    f.seek(SIZES[item_kind] * count, 1)
                else:
                    for _ in range(count):
                        skip(item_kind)
            else:
                raise ValueError(f"未対応の GGUF メタデータ型: {kind}")
            if f.tell() > file_size:
                raise ValueError("GGUF のメタデータが途中で切れています")

        def value(kind):
            if kind in FORMATS:
                return read(FORMATS[kind])
            if kind == 8:
                return string()
            if kind == 9:
                item_kind, count = read("<I"), read("<Q")
                if count > 10_000 or item_kind not in FORMATS:
                    raise ValueError("専門家のメタデータ配列が不正です")
                return [read(FORMATS[item_kind]) for _ in range(count)]
            raise ValueError(f"未対応の GGUF メタデータ型: {kind}")

        if f.read(4) != b"GGUF" or read("<I") not in (2, 3):
            raise ValueError("GGUF v2/v3 ではありません")
        read("<Q")  # tensor count
        for _ in range(read("<Q")):
            key, kind = string(), read("<I")
            if key == "tokenizer.ggml.tokens":
                if kind != 9 or read("<I") != 8:
                    raise ValueError("GGUF の tokenizer.ggml.tokens が文字列配列ではありません")
                result[key] = read("<Q")
                for _ in range(result[key]):
                    skip(8)
            elif key == "general.architecture" or key.endswith((
                    ".expert_count", ".expert_used_count", ".expert_shared_count",
                    ".expert_shared_feed_forward_length")):
                result[key] = value(kind)
            else:
                skip(kind)
    if "tokenizer.ggml.tokens" not in result:
        raise ValueError("GGUF に tokenizer.ggml.tokens がありません")
    return result


def gguf_vocab_size(path: Path) -> int:
    return gguf_metadata(path)["tokenizer.ggml.tokens"]


def model_info(path: Path, family: str, experts: str = "") -> dict:
    metadata = gguf_metadata(path)
    arch = metadata.get("general.architecture")
    expected = "qwen35moe" if family in ("q36", "orn") else "qwen35" if family.startswith("m9") else "qwen3moe"
    if arch != expected:
        raise ValueError(f"arch が違います: {family} は {expected} / GGUF は {arch}")
    def integer(key, default=0):
        value = metadata.get(f"{arch}.{key}", default)
        if type(value) is not int or value < 0:
            raise ValueError(f"GGUF の {key} が非負整数ではありません")
        return value
    count = integer("expert_count")
    used = metadata.get(f"{arch}.expert_used_count", 0)
    used = used if isinstance(used, list) else [used]
    if not used or any(type(n) is not int or n < 0 or n > count for n in used):
        raise ValueError("GGUF の expert_used_count が不正です")
    if arch.endswith("moe") and (count == 0 or min(used) == 0):
        raise ValueError("MoE の専門家数がありません")
    if experts and (not re.fullmatch(r"[1-9][0-9]*", experts) or int(experts) > count):
        raise ValueError(f"-e は GGUF の専門家数 1〜{count} の範囲で指定してください")
    shared_ff = integer("expert_shared_feed_forward_length")
    shared_count = integer("expert_shared_count")
    if arch == "qwen35moe" and shared_count and not shared_ff:
        raise ValueError("共有専門家の FF 長がありません")
    if arch == "qwen35moe":
        p, minimum = os.environ.get("KOUKAI_EXPERT_P"), os.environ.get("KOUKAI_EXPERT_MIN")
        if p:
            if not math.isfinite(float(p)) or not 0 <= float(p) <= 1:
                raise ValueError("KOUKAI_EXPERT_P は 0〜1 で指定してください")
            if minimum and (not re.fullmatch(r"[1-9][0-9]*", minimum) or int(minimum) > min(min(used), int(experts) if experts else min(used))):
                raise ValueError("KOUKAI_EXPERT_MIN は有効な専門家数の範囲で指定してください")
        elif minimum:
            raise ValueError("KOUKAI_EXPERT_MIN には KOUKAI_EXPERT_P が必要です")
    return {"MODEL_ARCH": arch, "MODEL_EXPERTS": count,
            "MODEL_EXPERTS_USED": ",".join(map(str, sorted(set(used)))),
            "MODEL_SHARED_FF": shared_ff, "MODEL_HAS_SHARED": int(shared_ff > 0)}


def check_ids(path: Path, family: str, model_size: int | None = None) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    tags = dict(re.findall(r"^# (vocab_size|repo|tokenizer_sha256)=(.+)$", "\n".join(lines), re.M))
    mimo = family.startswith("m9")
    if family in ("q36", "orn"):
        # repo 名は照合しない。同じ tokenizer の別モデル（Ornith）でも ID は共通。
        if tags.get("tokenizer_sha256") != Q36_TOKENIZER_SHA256 or not re.fullmatch(r"[1-9][0-9]*", tags.get("vocab_size", "")):
            raise ValueError("Qwen3.6 / Ornith の語彙には共通 tokenizer_sha256 と vocab_size の札が必要です")
        size = int(tags["vocab_size"])
    elif mimo:
        if tags.get("repo") != MIMO_REPO or not re.fullmatch(r"[1-9][0-9]*", tags.get("vocab_size", "")):
            raise ValueError("MiMo の語彙ファイルには repo と vocab_size の札が必要です")
        size = int(tags["vocab_size"])
    else:
        if tags or not re.fullmatch(r"vocab_keep_(999|9999|99999)_ids\.txt", path.name):
            raise ValueError("Qwen3 の既存語彙ファイルではありません")
        size = 151_936
    ids = [int(line) for line in lines if line and not line.startswith("#") and re.fullmatch(r"[0-9]+", line)]
    if len(ids) != sum(bool(line and not line.startswith("#")) for line in lines):
        raise ValueError("語彙ファイルに不正な行があります")
    if not ids or ids != sorted(set(ids)) or ids[-1] >= size:
        raise ValueError("語彙 ID が未整列・重複・範囲外です")
    # qwen35 系のGGUFは末尾に未使用tokenを詰めることがある。
    # IDの由来は共通tokenizerのhashで検査し、追加のpaddingだけを許す。
    padded = family in ("q36", "orn") or family.startswith("m9")   # MiMo 9B も qwen35 系（248077 語 → GGUF 248320）
    mismatch = size > model_size if model_size is not None and padded else size != model_size
    if model_size is not None and mismatch:
        raise ValueError(f"語彙数が違います: ファイル {size} / GGUF {model_size}")
    return size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-info", action="store_true", help="GGUF family [experts] を読み、安全な shell 変数を出力")
    parser.add_argument("ids", type=Path, help="語彙ファイル。--model-info では GGUF")
    parser.add_argument("family", help="m9q4 / m9iq4 / m9iq3 / q36 / orn / Qwen3")
    parser.add_argument("gguf", nargs="?")
    args = parser.parse_args()
    try:
        if args.model_info:
            for key, value in model_info(args.ids, args.family, args.gguf or "").items():
                print(f"{key}={value}")
            return
        size = check_ids(args.ids, args.family,
                         gguf_vocab_size(Path(args.gguf)) if args.gguf else None)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"語彙の照合失敗: {exc}\n")
    print(f"語彙の照合 OK: {size} 語")


if __name__ == "__main__":
    main()
