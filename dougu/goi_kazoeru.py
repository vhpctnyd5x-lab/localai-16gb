#!/usr/bin/env python3
"""固定 revision の tokenizer で実際の文書の token 頻度を数える。

実行には datasets, huggingface_hub, tokenizers が必要。--revision には
Hugging Face の 40 桁 commit SHA を渡す（branch 名や最新状態は受け付けない）。
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
QWEN_REPO = "Qwen/Qwen3-30B-A3B"
MIMO_REPO = "XiaomiMiMo/MiMo-V2.6-Distill-Qwen-9B"
MIMO_REVISION = "2367e865d009c13ac81713a2878291d33ab28177"
Q36_REPO = "Qwen/Qwen3.6-35B-A3B"
Q36_REVISION = "995ad96eacd98c81ed38be0c5b274b04031597b0"
Q36_TOKENIZER_SHA256 = "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42"
SPECIAL_NAMES = {"<think>", "</think>"}


def byte_tokens(vocab: dict[str, int]) -> set[int]:
    """GPT-2/ByteLevel の 256 個の単一 byte token を検証して返す。"""
    visible = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    missing = [b for b in range(256) if b not in visible]
    alphabet = {b: chr(b) for b in visible}
    alphabet.update({b: chr(256 + i) for i, b in enumerate(missing)})
    absent = [b for b, token in alphabet.items() if token not in vocab]
    if absent:
        raise ValueError(f"単一 byte token が {len(absent)} 個欠けています: {absent[:10]}")
    # 任意の UTF-8 は byte 列になり、その各 byte が一語で表現できる。
    inverse = {token: b for b, token in alphabet.items()}
    for sample in ("日本語🙂", "English", "\x00\xff"):
        encoded = sample.encode("utf-8")
        assert bytes(inverse[alphabet[b]] for b in encoded) == encoded
    return {vocab[alphabet[b]] for b in range(256)}


def text_rows(code_dataset: str):
    from datasets import load_dataset

    for lang, limit in (("ja", 30_000), ("en", 20_000)):
        rows = load_dataset("wikimedia/wikipedia", f"20231101.{lang}", split="train", streaming=True)
        count = 0
        for row in rows:
            value = row.get("text")
            if value:
                yield value
                count += 1
            if count == limit:
                break
        if count != limit:
            raise RuntimeError(f"Wikipedia {lang}: {count}/{limit} 記事のみ")
        print(f"Wikipedia {lang}: {count} 記事", flush=True)

    # プログラムの文は 手元のコードを使う（9/24: ネットの大きなコードデータの読み込みで 2時間 固まった）
    import pathlib
    home = pathlib.Path.home() / "LocalAI_mirror"
    kinds = ("*.py", "*.sh", "*.c", "*.cpp", "*.h", "*.js", "*.ts", "*.md", "*.json", "*.yml", "*.toml")
    count = 0
    for top in (home / "koukai", home / "kernel", home / "koukai" / "llama_src"):
        for kind in kinds:
            for path in sorted(top.rglob(kind)):
                if path.name.startswith("._") or any(p in path.parts for p in ("kiroku", "corpus", "node_modules", ".git", "kekka")) or path.stat().st_size > 2_000_000:
                    continue
                try:
                    yield path.read_text(encoding="utf-8", errors="ignore")
                    count += 1
                except OSError:
                    pass
    print(f"手元のコード: {count} ファイル", flush=True)

    count = 0
    for path in sorted((ROOT / "monosashi").glob("*.jsonl")):
        if path.name.startswith("._"):   # macOS の付けたおまけ（中身は文ではない。9/24 これで止まった）
            continue
        for line in path.open(encoding="utf-8", errors="ignore"):
            row = json.loads(line)
            question = row.get("問") or row.get("question")
            if isinstance(question, str) and question:
                yield question
                count += 1
    print(f"monosashi 問題文: {count} 件", flush=True)


def make_keeps(counts: Counter, vocab: dict[str, int], special: set[int], output: Path,
               suffix: str = "", repo: str = MIMO_REPO, tokenizer_sha256: str = ""):
    required = byte_tokens(vocab) | special
    by_id = {i: token for token, i in vocab.items()}
    total = sum(counts.values())
    if total == 0:
        raise ValueError("token が一つもありません")
    ranked = sorted(range(len(vocab)), key=lambda i: (-counts[i], i))
    for digits, denominator in (("999", 1_000), ("9999", 10_000), ("99999", 100_000)):
        threshold = (total * (denominator - 1) + denominator - 1) // denominator
        covered = 0
        keep = set(required)
        for token_id in ranked:
            if covered >= threshold:
                break
            covered += counts[token_id]
            keep.add(token_id)
        target = output / f"vocab_keep_{digits}{suffix}.txt"
        with target.open("w", encoding="utf-8") as f:
            for token_id in sorted(keep):
                f.write(f"{token_id}\t{json.dumps(by_id[token_id], ensure_ascii=False)}\n")
        if suffix:
            ids = output / f"vocab_keep_{digits}{suffix}_ids.txt"
            with ids.open("w", encoding="utf-8") as f:
                f.write(f"# vocab_size={len(vocab)}\n# repo={repo}\n")
                if tokenizer_sha256:
                    f.write(f"# tokenizer_sha256={tokenizer_sha256}\n")
                for token_id in sorted(keep):
                    f.write(f"{token_id}\n")
        print(f"{target.name}: {len(keep)} 語 / {len(vocab)} ({len(keep)/len(vocab):.3%})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", choices=(QWEN_REPO, MIMO_REPO, Q36_REPO), default=QWEN_REPO)
    parser.add_argument("--revision", help="Qwen3 の 40 桁 commit SHA。MiMo / Qwen3.6 は固定 revision")
    parser.add_argument("--output", type=Path, default=ROOT / "dougu/jikken")
    parser.add_argument("--code-dataset", default="codeparrot/github-code-clean",
                        help="Python/JavaScript/Shell の config がある代替データセット")
    args = parser.parse_args()
    fixed = {MIMO_REPO: MIMO_REVISION, Q36_REPO: Q36_REVISION}.get(args.repo)
    if fixed:
        if args.revision and args.revision != fixed:
            parser.error(f"{args.repo} の revision は {fixed} に固定しています")
        args.revision = fixed
    elif not args.revision or not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("--revision には固定した 40 桁 commit SHA が必要です")
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    path = hf_hub_download(args.repo, "tokenizer.json", revision=args.revision)
    tokenizer_sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if args.repo == Q36_REPO and tokenizer_sha256 != Q36_TOKENIZER_SHA256:
        raise ValueError("Qwen3.6 / Ornith 共通 tokenizer の sha256 が違います")
    tokenizer = Tokenizer.from_file(path)
    vocab = tokenizer.get_vocab(with_added_tokens=True)
    by_id = {i: token for token, i in vocab.items()}
    if set(by_id) != set(range(len(by_id))):
        raise ValueError("token ID が連続していません")
    special = {token_id for name in SPECIAL_NAMES
               for token_id in tokenizer.encode(name, add_special_tokens=False).ids}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    # 新tokenizerは special=false の道具・画像等の札も残す。
    special.update(x["id"] for x in raw.get("added_tokens", [])
                   if args.repo in (MIMO_REPO, Q36_REPO) or x.get("special"))
    special.update(i for t, i in vocab.items() if t.startswith("<|") and t.endswith("|>"))
    args.output.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    for text in text_rows(args.code_dataset):
        counts.update(tokenizer.encode(text, add_special_tokens=False).ids)
    suffix = {MIMO_REPO: "_mimo9", Q36_REPO: "_q36"}.get(args.repo, "")
    with (args.output / f"goi_count{suffix}.tsv").open("w", encoding="utf-8") as f:
        f.write("番号\t回数\t文字\n")
        for i in range(len(by_id)):
            f.write(f"{i}\t{counts[i]}\t{json.dumps(by_id[i], ensure_ascii=False)}\n")
    make_keeps(counts, vocab, special, args.output, suffix, args.repo,
               tokenizer_sha256 if args.repo == Q36_REPO else "")
    print("単一 byte token 256 個と UTF-8 往復: OK")


if __name__ == "__main__":
    main()
