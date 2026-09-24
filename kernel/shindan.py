#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shindan.py -- 何人もの外の頭に、カーネルの粗探しをさせる

  【なぜ】
  私ひとりで見ていると、同じ思い込みのまま見落とす。
  実際このところ、自分で入れたバグを自分で見つけられず、
  ユーザーに実物を見せられて初めて気づいた（作り話のHTML、
  PDFフォルダへの移動、動画をゴミ箱へ）。
  別の頭に、別の見方で読ませる。

  【やり方】
  ・強いモデルを何本か使う。1本ではなく何本も使うのは、
    「何人が同じ所を指したか」で本物らしさを測るため。
  ・見つけたものは、必ず「どのファイルの、どの行あたり」を書かせる。
    書けないものは、当てずっぽうとして落とす。
  ・出てきた指摘は、そのまま信じない。こちらで実物に当たって確かめる。

  【外に出るもの】
  カーネルの中身（自分で書いたコード）だけを送る。
  あなたのファイルの中身・名前・パスは送らない。
"""
import json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nvidia

HERE = os.path.dirname(os.path.abspath(__file__))
# 出す先は、走らせるたびに別の名前にする。
#   ここで一度しくじった。同じ名前にしていたため、
#   止めたはずの前の実行がまだ生きていて、
#   新しい実行の結果を まるごと上書きして消してしまった。
#   （止めたのは呼び出した側だけで、python 本体は生き残っていた）
def _deki(tag=""):
    return os.path.join(HERE, f"shindan_kekka{('_'+tag) if tag else ''}.json")


DEKI = _deki()

# 使う頭。「どこの」「どれ」を並べて書く。
#
#   NVIDIA の鍵は、本人確認は通るのに 推論だけ 403 で断られる状態だった
#   （/v1/models は 84個 返るのに、どのモデルに投げても Authorization failed）。
#   鍵の形は正しく、モデル名も実在する。アカウント側の権限の話なので
#   こちらでは直せない。使える先生で先に進める。
#   2026-08-27 鍵を作り直してもらって、NVIDIA が通るようになった。
#   実測で使えたのは この4本（一覧には84個あるが、大半は 404/410）。
ATAMA = ["ultra",   # nemotron-3-ultra-550b   いちばん賢い
         "super",   # nemotron-3-super-120b
         "code",    # gpt-oss-120b            プログラム向き
         "deep"]    # deepseek-v4-pro         よく考える

# 見てもらう所。行数が多すぎると読み落とすので、意味のまとまりで切る
MIRU = [
    ("kernel.py",     "札引きと、手順の組み立てと、実行の入口"),
    ("policy.py",     "どの部品を先に試すかを学ぶ係（UCB に替えたばかり）"),
    ("virtual.py",    "実行する前に頭の中でファイルを動かしてみる係"),
    ("safety.py",     "本物のフォルダを触るときの関所"),
    ("parts_more.py", "ファイルを扱う部品の本体"),
    ("make_page.py",  "ページやゲームを作る係"),
]

TANOMI = """あなたは、他人のコードの粗探しをする係です。

これは日本語でパソコンを操作する自作エンジンの一部です。
掛け算をほとんど使わない方式で、ニューラルネットは入っていません。

【この係の役目】{yakume}

【いちばん気にしていること】
1. ユーザーのファイルを壊す・消す・意図せず動かす筋道
2. 頼まれていないのに、似た別のことを勝手にやってしまう筋道
   （例: 「PDFにして」と言われて PDFという名のフォルダへ移動した）
3. できないことを「できません」と言わずに、それらしい答えを返す筋道
4. 例外を握りつぶして、間違いが静かに通る所
5. 明らかな論理の誤り、境界の抜け、Noneと0の取り違え

【書き方】必ず次の形で、多くても8件。確信のあるものだけ。
---
場所: <関数名 か 目印になる1行>
問題: <何が起きるか。1〜2文>
きっかけ: <どんな入力・状態でそうなるか。具体的に>
直し方: <一言>
---
推測や、様式の好みは書かないでください。
実際に壊れる筋道だけを書いてください。日本語で答えてください。

以下がコードです:
```python
{code}
```"""


# 一度に渡す量。kernel.py を まるごと(52,000字) 渡したら
# 240秒 待っても返ってこなかった。小分けにする
HITOKUCHI = 18000


def _kiriwake(src):
    """長いファイルを、関数の切れ目で いくつかに分ける"""
    if len(src) <= HITOKUCHI:
        return [src]
    # def の手前で切る。関数の途中で切ると読めなくなる
    ichi = [m.start() for m in re.finditer(r"\ndef ", src)] + [len(src)]
    out, ima, hajime = [], 0, 0
    for i in ichi:
        if i - hajime >= HITOKUCHI:
            out.append(src[hajime:ima if ima > hajime else i])
            hajime = ima if ima > hajime else i
        ima = i
    if hajime < len(src):
        out.append(src[hajime:])
    return [x for x in out if x.strip()]


def _kiku(atama, q, timeout):
    """どこの頭でも、同じ呼び方で聞けるようにする"""
    if ":" in atama:
        import teachers
        r = teachers.ask_one(atama, q, timeout=timeout)
        if isinstance(r, dict):
            if r.get("error") or r.get("エラー"):
                raise Exception(str(r.get("error") or r.get("エラー"))[:160])
            return r.get("text") or r.get("答え") or ""
        return str(r)
    return nvidia.ask(q, model=atama, timeout=timeout, max_tokens=3000,
                      temperature=0.15)


def hitotsu(atama, fname, yakume, timeout=300):
    path = os.path.join(HERE, fname)
    kire = _kiriwake(open(path, encoding="utf-8").read())
    t0, henji, shippai = time.time(), [], []
    for n, code in enumerate(kire, 1):
        q = TANOMI.format(yakume=yakume
                          + (f"（{len(kire)}分割のうち {n} 本目）" if len(kire) > 1 else ""),
                          code=code)
        try:
            henji.append(_kiku(atama, q, timeout))
        except Exception as e:
            shippai.append(str(e)[:120])
    r = {"頭": atama, "ファイル": fname, "分割": len(kire),
         "秒": round(time.time() - t0, 1)}
    if henji:
        r["返事"] = "\n---\n".join(henji)
    else:
        r["エラー"] = " / ".join(shippai) or "返事なし"
    return r


def wakeru(henji):
    """--- で区切られた指摘を、ひとつずつに分ける"""
    out = []
    for blk in re.split(r"\n-{3,}\n", "\n" + (henji or "") + "\n"):
        b = blk.strip()
        if not b or "問題:" not in b:
            continue
        d = {}
        for line in b.split("\n"):
            m = re.match(r"^\s*(場所|問題|きっかけ|直し方)\s*[:：]\s*(.+)$", line)
            if m:
                d[m.group(1)] = m.group(2).strip()
        if d.get("問題"):
            out.append(d)
    return out


def hashiru(atamas=None, files=None, verbose=True, tag=""):
    atamas = atamas or ATAMA
    files = files or MIRU
    deki = _deki(tag)
    # 先に他の実行が走っていないか確かめる
    import subprocess
    try:
        n = subprocess.run(["pgrep", "-f", "shindan.py"], capture_output=True,
                           text=True).stdout.strip().split()
        if len(n) > 1:
            print(f"  ※ すでに {len(n)-1} 本 走っています。出す先は {os.path.basename(deki)}")
    except Exception:
        pass
    kekka = []
    for fname, yakume in files:
        for a in atamas:
            if verbose:
                print(f"  {a:>6} が {fname} を読んでいます…", end="", flush=True)
            r = hitotsu(a, fname, yakume)
            if "エラー" in r:
                if verbose:
                    print(f" だめ（{r['エラー'][:60]}）")
            else:
                r["指摘"] = wakeru(r["返事"])
                if verbose:
                    print(f" {len(r['指摘'])} 件 / {r['秒']}秒")
            kekka.append(r)
            json.dump(kekka, open(deki, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
    return kekka


# 「場所」の書き方はモデルごとにばらばら。
#     `_act_of()` の類似度判定ロジック
#     `_act_of` 関数
#     _act_of の中
# そのまま文字列で比べると、同じ所を指していても一致しない。
# 実際、80件出ているのに「2人以上が指した所」がゼロになった。
# 関数の名前だけを取り出して束ねる。
_NAMAE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_SOTO = {"the", "and", "for", "not", "none", "true", "false", "def", "return",
         "関数名", "目印", "python", "json", "self", "path", "file", "line"}


def _kaname(tokoro):
    """場所の書き方から、関数名らしいものを1つ取り出す"""
    t = (tokoro or "").replace("`", " ")
    for m in _NAMAE.finditer(t):
        w = m.group(0)
        if w.lower() not in _SOTO:
            return w
    return (tokoro or "?")[:30]


def matome(kekka=None):
    """何人が同じ所を指したかで並べる"""
    if kekka is None:
        kekka = json.load(open(DEKI, encoding="utf-8"))
    kaz = {}
    for r in kekka:
        for s in r.get("指摘", []):
            k = (r["ファイル"], _kaname(s.get("場所")))
            kaz.setdefault(k, {"人": set(), "中身": []})
            kaz[k]["人"].add(r["頭"])
            kaz[k]["中身"].append(s)
    nar = sorted(kaz.items(), key=lambda kv: -len(kv[1]["人"]))
    out = []
    for (f, tok), v in nar:
        out.append({"ファイル": f, "場所": tok, "人数": len(v["人"]),
                    "だれ": sorted(v["人"]), "指摘": v["中身"][0],
                    "みんなの": v["中身"]})
    return out


if __name__ == "__main__":
    tag = os.environ.get("SHINDAN_TAG", "")
    only = sys.argv[1:] or None
    files = [(f, y) for f, y in MIRU if not only or f in only]
    print(f"{len(ATAMA)} 本の頭 × {len(files)} ファイル = {len(ATAMA)*len(files)} 回 聞きます\n")
    k = hashiru(files=files, tag=tag)
    print("\n■ 何人もが指した所（上から順に怪しい）")
    for m in matome(k)[:20]:
        print(f"  [{m['人数']}人] {m['ファイル']} … {m['場所']}")
        print(f"        {m['指摘'].get('問題','')}")
