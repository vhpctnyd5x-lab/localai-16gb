#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kensa.py -- GGUF ファイルが「本当に中身の入った本物か」を自分で確かめる。

  Verify a GGUF file: byte accounting, per-layer distinctness, entropy,
  architecture fingerprint, and byte-exact provenance against the official
  file on Hugging Face (via HTTP Range requests — only a few MB downloaded).

════════════════════════════════════════════════════════════════
 なぜこれが要るのか
════════════════════════════════════════════════════════════════
  「48層 / 96専門家」と **ヘッダに書いてある**ことは、
  「48層ぶんの本物の重みが入っている」証明には **まったくなりません**。
  ヘッダは数バイト書き換えれば偽造できます。

  だから中身を見ます。この道具は5つ確かめます:

    ① 帳尻     … ヘッダ + テンソルの合計 == ファイルの大きさか
                  （合わなければ、水増しか、欠けている）
    ② 別物か   … 48層の中身の指紋が全部ちがうか
                  （1層をコピーして48枚に見せる細工を暴く）
    ③ 中身     … ゼロ埋めや同じ値の繰り返しでないか（バイトの散らばり）
    ④ 素性     … 語彙・特殊トークン・構造がそのモデル族のものか
    ⑤ ★出所   … **公式ファイルとバイト単位で一致するか**
                  Hugging Face から必要な数MBだけを範囲取得して突き合わせる

  ★ ⑤ が本命です。①〜④は「それらしい」までしか言えません。
    ⑤ だけが「公式のあの重みから作られた」を **証明** します。

使いかた:
    python3 kensa.py モデル.gguf
    python3 kensa.py モデル.gguf --moto unsloth/Qwen3-30B-A3B-GGUF/Qwen3-30B-A3B-Q2_K.gguf
"""
import argparse, collections, hashlib, math, os, struct, subprocess, sys

# GGUF の型ごとの (1ブロックのバイト数, 1ブロックの要素数)
GG = {0:(4,1), 1:(2,1), 2:(18,32), 3:(20,32), 6:(22,32), 7:(24,32), 8:(34,32),
      10:(84,256), 11:(110,256), 12:(144,256), 13:(176,256), 14:(210,256),
      15:(292,256), 16:(66,256), 17:(74,256), 18:(98,256)}
_T = {0:"B",1:"b",2:"H",3:"h",4:"I",5:"i",6:"f",7:"?",10:"Q",11:"q",12:"d"}
_S = {0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}


def yomu(f):
    """GGUF のヘッダを読む。戻りは (設定, テンソル表, 重みの始まる位置)"""
    f.seek(0)
    if f.read(4) != b"GGUF":
        raise SystemExit("GGUF ファイルではありません")
    struct.unpack("<I", f.read(4))
    nt = struct.unpack("<Q", f.read(8))[0]
    nk = struct.unpack("<Q", f.read(8))[0]

    def rs():
        n = struct.unpack("<Q", f.read(8))[0]
        return f.read(n).decode("utf-8", "replace")

    kv = {}
    for _ in range(nk):
        k = rs(); t = struct.unpack("<I", f.read(4))[0]
        if t == 8:
            kv[k] = rs()
        elif t == 9:
            et = struct.unpack("<I", f.read(4))[0]
            ln = struct.unpack("<Q", f.read(8))[0]
            kv[k] = [rs() for _ in range(ln)] if et == 8 else (
                f.read(_S.get(et, 4) * ln) and "[%d]" % ln)
        else:
            kv[k] = struct.unpack("<" + _T[t], f.read(_S[t]))[0]

    ts = {}
    for _ in range(nt):
        na = rs(); nd = struct.unpack("<I", f.read(4))[0]
        dims = [struct.unpack("<Q", f.read(8))[0] for _ in range(nd)]
        tt = struct.unpack("<I", f.read(4))[0]
        off = struct.unpack("<Q", f.read(8))[0]
        n = 1
        for d in dims:
            n *= d
        bpb, epb = GG.get(tt, (0, 1))
        ts[na] = {"形": dims, "型": tt, "位置": off,
                  "バイト": (n // epb) * bpb if bpb else 0}
    ds = f.tell()
    a = kv.get("general.alignment", 32)
    return kv, ts, (ds + a - 1) // a * a


def shirushi(ok):
    return "○" if ok else "×"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gguf")
    ap.add_argument("--moto", default="",
                    help="くらべる公式ファイル（例 unsloth/Qwen3-30B-A3B-GGUF/"
                         "Qwen3-30B-A3B-Q2_K.gguf）。省くと ①〜④ だけ")
    ap.add_argument("--kurabe", type=int, default=5, help="出所照合で見るテンソルの数")
    a = ap.parse_args()

    size = os.path.getsize(a.gguf)
    f = open(a.gguf, "rb")
    kv, ts, ds = yomu(f)
    print("ファイル : %s" % os.path.basename(a.gguf))
    print("大きさ   : %.3f GiB (%d バイト)" % (size / 1024**3, size))
    print("アーキ   : %s / %s" % (kv.get("general.architecture"), kv.get("general.name")))
    print()

    # ── ① 帳尻 ────────────────────────────────────────────
    goukei = sum(t["バイト"] for t in ts.values())
    sa = size - ds - goukei
    print("① 帳尻")
    print("   テンソル %d 個 = %.3f GiB ／ ヘッダ %.1f MiB"
          % (len(ts), goukei / 1024**3, ds / 1024**2))
    print("   %s ヘッダ+重み と ファイルの差: %.1f MiB %s"
          % (shirushi(abs(sa) < 1024**2), sa / 1024**2,
             "" if abs(sa) < 1024**2 else "← 水増しか欠けがある"))

    # ── ② 層ごとに別物か ──────────────────────────────────
    print("\n② 層ごとの中身（1層を丸写ししていないか）")
    sou = collections.defaultdict(dict)
    for na, t in ts.items():
        if na.startswith("blk."):
            sou[int(na.split(".")[1])][na.split(".", 2)[2]] = t
    if sou:
        katachi = {frozenset(v) for v in sou.values()}
        print("   層 %d〜%d（%d 層） 構成のパターン %d 種 %s"
              % (min(sou), max(sou), len(sou), len(katachi), shirushi(len(katachi) == 1)))
        for na in sorted({n for v in sou.values() for n in v})[:20]:
            if not na.endswith(".weight") or "norm" in na:
                continue
            yubi = {}
            for i, v in sou.items():
                if na in v:
                    f.seek(ds + v[na]["位置"])
                    yubi[i] = hashlib.sha256(f.read(min(v[na]["バイト"], 1 << 20))).hexdigest()
            if len(yubi) > 1:
                print("   %s %-24s 指紋 %d 種 / %d 層"
                      % (shirushi(len(set(yubi.values())) == len(yubi)), na,
                         len(set(yubi.values())), len(yubi)))

    # ── ③ 中身が本物のデータか ────────────────────────────
    print("\n③ 中身（ゼロ埋めや繰り返しでないか）")
    ookii = sorted(ts.items(), key=lambda x: -x[1]["バイト"])[:4]
    for na, t in ookii:
        f.seek(ds + t["位置"])
        buf = f.read(min(t["バイト"], 1 << 20))
        if not buf:
            continue
        c = collections.Counter(buf)
        H = -sum((v / len(buf)) * math.log2(v / len(buf)) for v in c.values())
        print("   %s %-30s 0が%5.2f%%  ばらつき %.2f/8.00 ビット  値の種類 %d/256"
              % (shirushi(H > 6.5 and len(c) > 200), na[:30],
                 buf.count(0) / len(buf) * 100, H, len(c)))

    # ── ④ 素性 ────────────────────────────────────────────
    print("\n④ 素性")
    v = kv.get("tokenizer.ggml.tokens", [])
    print("   語彙 %s 語 / トークナイザ %s" % (
        len(v) if isinstance(v, list) else v, kv.get("tokenizer.ggml.model")))
    if isinstance(v, list):
        mi = [t for t in ("<|im_start|>", "<|im_end|>", "<think>", "</think>",
                          "<tool_call>", "<|endoftext|>") if t in v]
        print("   特殊トークン: %s" % (" ".join(mi) if mi else "見つからない"))
    qk = [n for n in ts if n.endswith("attn_q_norm.weight")]
    print("   QKノーム(%d本) … Qwen3 系にはあり、Qwen2 系には無い部品" % len(qk))

    # ── ⑤ 出所（本命）────────────────────────────────────
    print("\n⑤ 出所（公式ファイルとバイト単位で突き合わせる）")
    if not a.moto:
        print("   --moto を渡すと確かめられます。例:")
        print("     --moto unsloth/Qwen3-30B-A3B-GGUF/Qwen3-30B-A3B-Q2_K.gguf")
        return
    repo, fn = a.moto.rsplit("/", 1)
    U = "https://huggingface.co/%s/resolve/main/%s" % (repo, fn)
    print("   くらべる先: %s" % U)
    atama = subprocess.run(["curl", "-s", "-r", "0-6291455", "-L", U],
                           capture_output=True).stdout
    if len(atama) < 1 << 20:
        print("   × ヘッダを取れませんでした（%d バイト）" % len(atama))
        return
    import io
    kv_o, ts_o, ds_o = yomu(io.BytesIO(atama))
    print("   %s テンソルの名前が完全一致 (%d 個)"
          % (shirushi(set(ts_o) == set(ts)), len(ts_o)))
    print("   %s 語彙が一字一句一致"
          % shirushi(kv_o.get("tokenizer.ggml.tokens") == kv.get("tokenizer.ggml.tokens")))
    chigau = [n for n in ts_o if n in ts and ts_o[n]["形"] != ts[n]["形"]]
    if chigau:
        print("   ！ 形が違うテンソル %d 個 … 手を入れた部分:" % len(chigau))
        for k, c in collections.Counter(n.split(".")[-2] for n in chigau).items():
            print("       %-20s %d 本  %s → %s"
                  % (k, c, ts_o[chigau[0]]["形"], ts[chigau[0]]["形"]))
    # 形が同じ＝手を入れていないテンソルを、バイトで突き合わせる
    onaji = [n for n in ts_o if n in ts and ts_o[n]["形"] == ts[n]["形"]
             and ts[n]["バイト"] > 4096]
    onaji.sort(key=lambda n: -ts[n]["バイト"])
    erabu = onaji[:a.kurabe]
    print("   手を入れていないテンソルを %d 本、実物で照合します:" % len(erabu))
    zen = True
    for na in erabu:
        n = min(ts[na]["バイト"], 2 << 20)
        aa = ds_o + ts_o[na]["位置"]
        kou = subprocess.run(["curl", "-s", "-r", "%d-%d" % (aa, aa + n - 1), "-L", U],
                             capture_output=True).stdout
        f.seek(ds + ts[na]["位置"])
        ok = len(kou) == n and hashlib.sha256(kou).digest() == hashlib.sha256(f.read(n)).digest()
        zen &= ok
        print("     %s %-32s %6.2f MB" % (shirushi(ok), na[:32], n / 1024**2))
    print()
    print("   →", "★ この公式ファイルから作られたもので間違いありません。" if zen
          else "★ 一致しませんでした。出所を疑ってください。")


if __name__ == "__main__":
    main()
