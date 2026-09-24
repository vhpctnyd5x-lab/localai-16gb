#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mondai_run.py -- 作った問題を 裏で解かせて、どこが弱いかを出す

  ────────────────────────────────────────────────
  この道具の使い道を、はじめに はっきりさせておく
  ────────────────────────────────────────────────
  自分で問題を作って、自分で解いて、その成績が上がるように直したら、
  **その問題に特化するだけ** で、外の言い方には効かない。
  ご本人の言う通り「ずっとそれになるから 意味なさそう」は 正しい。

  なので この道具は 二つを はっきり分ける。

      ✓ 使う  : バグ取りの網（落ちる・答えが違う所を 見つける）
      ✗ 使わない: 成績を上げるための 練習台

  今日 直したバグ3件は、どれも「問題を1問足したら出てきた」もの。
  手で書ける問題は 83問が限界だった。工場なら 何千問でも出る。
  **見つけるのは 機械。直すのは 人（と私）。**

  ────────────────────────────────────────────────
  過適合していないか、自分で見張る
  ────────────────────────────────────────────────
  ① 型番ごとの正答率を出す。ばらつきが大きい＝ある型に頼っている
  ② 型番を丸ごと伏せて測る（伏せた型だけ落ちる＝型を覚えただけ）
  ③ **手で書いた83問との差**を毎回いっしょに出す。
     作った問題だけ上がって 手書きが上がらないなら、その直しは偽物。
     これが いちばん効く見張り（NVIDIA も同じことを言っていた）。
"""
import io, json, os, sys, time, contextlib, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mondai

LOG = os.path.join(HERE, "mondai_kekka.json")


def _kernel_wo_ba_ni_mukeru():
    """カーネルの見る先を 問題用の場に向ける"""
    import kernel
    kernel.SANDBOX = mondai.BA
    return kernel


def toku(kernel, toi):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            ans = kernel.handle(toi, quiet=True)
        return (ans or ""), None
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def _sugata(d):
    """その場の いまの姿（名前だけ）。触られていないかを見るのに使う"""
    out = []
    for root, dirs, files in os.walk(d):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for f in sorted(files):
            if not f.startswith("."):
                out.append(os.path.relpath(os.path.join(root, f), d))
        for x in dirs:
            out.append(os.path.relpath(os.path.join(root, x), d) + "/")
    return tuple(sorted(out))


def hitomawari(kazu=300, tane=1, muzukashisa=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
               fuseru=None, verbose=True):
    """問題を kazu 問 解いて、成績を返す

    fuseru に型番を渡すと、その型は 出題しない（伏せる）
    """
    kernel = _kernel_wo_ba_ni_mukeru()
    mondaishu = mondai.tsukuru(kazu, tane, muzukashisa)
    if fuseru:
        mondaishu = [m for m in mondaishu if m[2] not in fuseru]

    atari = collections.Counter()
    zen = collections.Counter()
    ochita, chigau, sawatta = [], [], []
    t0 = time.time()
    for i, (toi, kotae, kata, muzu) in enumerate(mondaishu):
        # 一問ごとに 場を作り直す。
        # そうしないと、前の問題で作られたフォルダが 次の問題の数に入り、
        # 正解のほうが古くなる。実際「まとめ」というフォルダが増えていて、
        # 「ものはいくつ」の答えが 1つずつ ずれていた
        mondai.ba_tsukuru(tane)
        mae = _sugata(mondai.BA)
        ans, err = toku(kernel, toi)
        ato = _sugata(mondai.BA)
        ugokasu = kata.startswith("うごかす/")
        if mae != ato and not ugokasu:
            # 数えるだけの問いで ものが増減したら、それ自体がバグ
            fueta = sorted(set(ato) - set(mae))
            hetta = sorted(set(mae) - set(ato))
            sawatta.append((toi, fueta, hetta))
        if ugokasu and mae == ato:
            # 動かす頼みなのに 何も動いていない。
            # 答えの文だけ立派で 中身が伴っていない形は、いちばん質が悪い
            sawatta.append((toi, ["（何も動いていない）"], []))
        zen[kata] += 1
        if err:
            ochita.append((toi, kotae, err))
        elif kotae in ans:
            atari[kata] += 1
        else:
            chigau.append((toi, kotae, ans.replace("\n", " ")[:60]))
        if verbose and i % 25 == 0:
            print(f"\r  {i}/{len(mondaishu)}", end="", flush=True)
    if verbose:
        print(f"\r  {len(mondaishu)} 問 おわり（{time.time()-t0:.0f} 秒）")
    return {"型別": {k: (atari[k], zen[k]) for k in zen},
            "落ちた": ochita, "ちがう": chigau, "触った": sawatta,
            "合計": (sum(atari.values()), sum(zen.values()))}


def tegaki_seiseki():
    """手で書いた 83問 の成績。これが上がらない直しは 偽物"""
    import subprocess
    out = {}
    for name, path in (("bench33", "bench.py"),
                       ("言い換え25", "iikae_bench.py"),
                       ("難しい25", "iikae_bench2.py")):
        try:
            r = subprocess.run([sys.executable, os.path.join(HERE, path)],
                               capture_output=True, text=True, timeout=900)
            atari = None
            for line in r.stdout.splitlines():
                if "正解" in line and "/" in line:
                    atari = line.strip()
            out[name] = atari or "（読めず）"
        except Exception as e:
            out[name] = f"（動かず: {e}）"
    return out


def _hyouji(k):
    a, z = k["合計"]
    print(f"\n■ 作った問題 {z} 問 : {a}/{z} （{a*100//max(1,z)}%）")
    print("\n  型番ごと（ばらつきが大きい＝その型に頼っている）")
    for kata, (x, y) in sorted(k["型別"].items()):
        print(f"    {kata:　<22} {x}/{y} （{x*100//max(1,y)}%）")
    if k.get("触った"):
        print(f"\n  ★ 場のことで おかしい {len(k['触った'])} 件"
              f"（聞かれただけで変えた／動かす頼みなのに動いていない）")
        for toi, fueta, hetta in k["触った"][:6]:
            print(f"    ・{toi}\n        増えた {fueta}　減った {hetta}")
    if k["落ちた"]:
        print(f"\n  ★ 落ちた {len(k['落ちた'])} 件（バグ。まず これを直す）")
        for toi, kotae, err in k["落ちた"][:8]:
            print(f"    ・{toi}\n        {err}")
    if k["ちがう"]:
        print(f"\n  答えが違う {len(k['ちがう'])} 件（先頭8件）")
        for toi, kotae, ans in k["ちがう"][:8]:
            print(f"    ・{toi}\n        ほしい「{kotae}」／ 出た「{ans}」")


def main():
    kazu = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    tane = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    print(f"問題を {kazu} 問 作って解きます（たね {tane}）")
    k = hitomawari(kazu, tane)
    _hyouji(k)

    print("\n" + "=" * 60)
    print("■ 手で書いた問題（作った問題だけ上がっていないか の見張り）")
    print("=" * 60)
    for name, s in tegaki_seiseki().items():
        print(f"  {name:　<10} {s}")
    print("=" * 60)

    json.dump({"時刻": time.strftime("%Y-%m-%d %H:%M"), "たね": tane,
               "合計": k["合計"],
               "型別": {a: list(b) for a, b in k["型別"].items()},
               "落ちた数": len(k["落ちた"]), "違う数": len(k["ちがう"])},
              open(LOG, "a", encoding="utf-8"), ensure_ascii=False)
    open(LOG, "a", encoding="utf-8").write("\n")


if __name__ == "__main__":
    main()
