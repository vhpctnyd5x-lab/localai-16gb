#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
renshu.py -- 自分で練習する。誰にも言われずに、手順の木を育てる

  【なぜ要るか】
  カーネルには、部品の順番を学ぶ係（policy.py）が最初からある。
  ところが、あなたが何か打ったときにしか学べない。
  そのため 440 回ぶんしか経験が溜まっていなかった（成功 6・失敗 434）。

  学ぶ仕組みがあるのに、経験が無い。それだけの話だった。

  【やること】
  練習用フォルダを相手に、ありうる言われ方を自分で作り、
  ひたすら解いてみる。うまくいった順番は覚え、駄目だった枝は覚えて避ける。
      ・本物のフォルダには触らない
      ・誰にも聞かない（先生も呼ばない）
      ・掛け算はしない（ウィルソン得点の中の割り算だけ）

  【木のかたち】
  policy が覚えているのは
      「いまどんな場面で、直前に何を置いたか」→「次に何を置くと通るか」
  という表。これは深さ1の木を、場面ごとに持っているのと同じ。
  練習するほど、枝ごとの勝ち負けが埋まっていく。
"""
import itertools, os, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kernel


def _goi():
    """SEED から、枠ごとの値を集める"""
    w = {}
    for _k, v in kernel.SEED.items():
        if isinstance(v, (list, tuple)) and len(v) == 2:
            w.setdefault(v[0], set()).add(v[1])
    return {k: sorted(v) for k, v in w.items()}


GOI = _goi()
# 練習する言われ方の作り方。動作は必ず要る。場所も要る。
# あとは付けたり付けなかったり
OMAKE = ["種類", "時期", "大きさ", "並べ方"]


def bamen(rnd, yomu_dake=True):
    """ありうる言われ方を、ひとつ作る"""
    doing = GOI["動作"]
    if yomu_dake:
        doing = [d for d in doing if d in ("数える", "一覧", "大きさ", "重複")]
    s = {"動作": rnd.choice(doing), "場所": rnd.choice(GOI["場所"])}
    for k in OMAKE:
        if k in GOI and rnd.random() < 0.45:
            s[k] = rnd.choice(GOI[k])
    return s


def renshu(kaisu=300, tane=0, yomu_dake=True, verbose=True):
    """練習する。(解けた数, かかった秒) を返す"""
    rnd = random.Random(tane)
    allow = set(kernel.PARTS) - kernel.DESTRUCTIVE if yomu_dake else None
    toketa = 0
    t0 = time.time()
    for i in range(kaisu):
        s = bamen(rnd, yomu_dake)
        try:
            plan, _st = kernel.solve(s, verbose=False, allow=allow, budget=400)
            toketa += bool(plan)
        except Exception:
            pass
        if verbose and (i + 1) % 50 == 0:
            print(f"\r  {i+1}/{kaisu} 回  解けた {toketa}", end="", flush=True)
    if verbose:
        print()
    return toketa, time.time() - t0


def keiken():
    """いま何回ぶんの経験があるか"""
    import json
    p = os.path.join(kernel.HERE, "policy.json")
    if not os.path.exists(p):
        return 0, 0, 0
    t = json.load(open(p)).get("table", {})
    w = sum(x["w"] for v in t.values() for x in v.values())
    l = sum(x["l"] for v in t.values() for x in v.values())
    return len(t), w, l


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    b, w, l = keiken()
    print(f"練習まえ: 場面 {b} ／ 成功 {w} ／ 失敗 {l}")
    t, sec = renshu(n)
    b, w, l = keiken()
    print(f"練習あと: 場面 {b} ／ 成功 {w} ／ 失敗 {l}")
    print(f"  {n} 回やって {t} 回解けた（{sec:.1f} 秒）")
