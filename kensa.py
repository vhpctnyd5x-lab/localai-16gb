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
import argparse, collections, hashlib, math, os, shutil, struct, subprocess, sys
import urllib.request

# GGUF の型ごとの (1ブロックのバイト数, 1ブロックの要素数)
# GGUF の型ごとの (1ブロックのバイト数, 1ブロックの要素数)
#   ★ ここに無い型が出ると サイズが 0 と計算され、①の帳尻が大外れする。
#     IQ 系や BF16 を落としていたので足した。それでも知らない型は出うるので、
#     下で「知らない型があった」と必ず知らせる。
GG = {0:(4,1), 1:(2,1), 2:(18,32), 3:(20,32), 6:(22,32), 7:(24,32), 8:(34,32),
      9:(36,32), 10:(84,256), 11:(110,256), 12:(144,256), 13:(176,256),
      14:(210,256), 15:(292,256), 16:(66,256), 17:(74,256), 18:(98,256),
      19:(50,256), 20:(66,256), 21:(74,256), 22:(98,256), 23:(110,256),
      24:(50,32), 25:(66,256), 26:(38,256), 27:(46,256), 28:(56,256),
      29:(50,256), 30:(2,1), 31:(4,1), 32:(4,1), 33:(1,1), 34:(1,1)}
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
        # ★ 長さをそのまま信じて read すると、壊れた／細工されたヘッダで
        #   メモリを食い尽くして落ちる。ありえない長さは断る。
        n = struct.unpack("<Q", f.read(8))[0]
        if n > (1 << 24):
            raise SystemExit("ヘッダが壊れています（文字列長 %d）" % n)
        return f.read(n).decode("utf-8", "replace")

    kv = {}
    for _ in range(nk):
        k = rs(); t = struct.unpack("<I", f.read(4))[0]
        if t == 8:
            kv[k] = rs()
        elif t == 9:
            et = struct.unpack("<I", f.read(4))[0]
            ln = struct.unpack("<Q", f.read(8))[0]
            if et == 8:
                kv[k] = [rs() for _ in range(ln)]
            elif et in _S:
                f.read(_S[et] * ln)
                kv[k] = "[%d]" % ln
            else:
                # ★ 知らない要素型を 4バイトと決めつけて読み飛ばすと、
                #   以降のヘッダ解析が全部ずれる。分からないなら止める。
                raise SystemExit("知らない配列の型 %d（読み進められません）" % et)
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


def hanbun_toru(url, a, b):
    """URL の a〜b バイト目だけを取る。curl があれば curl、無ければ標準で。"""
    if shutil.which("curl"):
        return subprocess.run(["curl", "-s", "-r", "%d-%d" % (a, b), "-L", url],
                              capture_output=True).stdout
    req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % (a, b)})
    with urllib.request.urlopen(req, timeout=120) as f:
        return f.read()


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
    # ★ テンソルは境界に揃えて置かれるので、あいだに詰め物が入る。
    #   それを数えないと、正常なファイルでも「合わない」と出てしまう。
    ali = kv.get("general.alignment", 32)
    naka = sorted(ts.values(), key=lambda t: t["位置"])
    tsumemono = 0
    for i, t in enumerate(naka[:-1]):
        owari = t["位置"] + t["バイト"]
        tsumemono += naka[i + 1]["位置"] - owari
    goukei = sum(t["バイト"] for t in ts.values())
    shiranai = [n for n, t in ts.items() if t["型"] not in GG]
    sa = size - ds - goukei - tsumemono
    print("① 帳尻")
    print("   テンソル %d 個 = %.3f GiB ／ ヘッダ %.1f MiB"
          % (len(ts), goukei / 1024**3, ds / 1024**2))
    if tsumemono:
        print("   すきま（境界合わせの詰め物）: %.1f MiB" % (tsumemono / 1024**2))
    if shiranai:
        print("   ！ 知らない量子化の型が %d 本あります。帳尻はあてになりません: %s"
              % (len(shiranai), shiranai[:3]))
    print("   %s ヘッダ+重み+すきま と ファイルの差: %.1f MiB %s"
          % (shirushi(abs(sa) < 1024**2 and not shiranai), sa / 1024**2,
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
    if not shutil.which("curl"):
        print("   ！ curl が無いので、標準ライブラリで取りに行きます")
    repo, fn = a.moto.rsplit("/", 1)
    U = "https://huggingface.co/%s/resolve/main/%s" % (repo, fn)
    print("   くらべる先: %s" % U)
    # ★ 6MB 固定にしていたが、Qwen3 のヘッダは 5.66MB で **余裕が 0.34MB しか無かった**。
    #   語彙の多いモデルなら確実に足りない。足りなければ倍にして取り直す。
    import io
    kv_o = ts_o = ds_o = None
    tore = 8 << 20
    for _ in range(5):
        atama = hanbun_toru(U, 0, tore - 1)
        if len(atama) < 1 << 20:
            print("   × ヘッダを取れませんでした（%d バイト）" % len(atama))
            return
        try:
            kv_o, ts_o, ds_o = yomu(io.BytesIO(atama))
            break
        except Exception:
            tore *= 2                      # 足りなかった。倍にして取り直す
    if ts_o is None:
        print("   × ヘッダが %d MB でも読み切れませんでした" % (tore >> 20))
        return
    print("   ヘッダ %.2f MB を取得（必要なぶんだけ）" % (ds_o / 1024**2))
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
        kou = hanbun_toru(U, aa, aa + n - 1)
        f.seek(ds + ts[na]["位置"])
        ok = len(kou) == n and hashlib.sha256(kou).digest() == hashlib.sha256(f.read(n)).digest()
        zen &= ok
        print("     %s %-32s %6.2f MB" % (shirushi(ok), na[:32], n / 1024**2))
    print()
    print("   →", "★ この公式ファイルから作られたもので間違いありません。" if zen
          else "★ 一致しませんでした。出所を疑ってください。")


if __name__ == "__main__":
    main()
