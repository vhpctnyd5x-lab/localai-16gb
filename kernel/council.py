#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
council.py -- 何人かで考えて、多数決で決める（＝考える時間で賢くする）

  ────────────────────────────────────────────────
  「掛け算を増やさずに賢くする」いちばん確実な道は、
  考える時間を増やすこと。いま世の中で
  「test-time compute（答えるときに考える時間）」と呼ばれているもの。
  ────────────────────────────────────────────────

  やることは3つだけ。

    ① 何人かに、ちがう順番で探させる（視点を変える）
    ② 出てきた案を、ぜんぶ下見で確かめる（通らない案はここで落ちる）
    ③ 残った案を多数決で選ぶ

  ここで大事なこと。
  ③の多数決は「たし算」です。掛け算ではありません。
  ですが、探せる範囲は 人数 × 深さ で増えます。
      5人 × 深さ4 = 5⁴ = 625通り
  掛け算を1回も使わずに、探せる広さだけが掛け算で増える。

  多数決には、1万ビットの「たばねる」をそのまま使う。
  手順を1本のビット列にして、みんなの分をたばね、
  たばねたものにいちばん近い手順を選ぶ。
  （票を数えるのと同じことだが、
    「ほとんど同じで1手だけ違う案」もちゃんと近いと分かる）
"""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hdv


# ------------------------------------------------------------------
# 視点 -- 部品の並べ方を変える係
#   同じ問題でも、どの手から試すかで、たどりつく案が変わる
# ------------------------------------------------------------------
def _v_normal(names, slots, path):
    """ふつう。実績の順（policy が決めた順）のまま"""
    return names


def _v_narrow_first(names, slots, path):
    """条件を先に使い切る人。「しぼる」を早めに置く"""
    return sorted(names, key=lambda n: 0 if n.startswith("しぼる") else 1)


def _v_short_first(names, slots, path):
    """短く済ませたい人。終わりの部品を早めに置く"""
    import kernel
    return sorted(names, key=lambda n: 0 if kernel.PARTS[n].get("terminal") else 1)


def _v_reverse(names, slots, path):
    """へそ曲がり。実績の逆から試す。
    実績どおりだと、いつも同じ案しか出てこないので、わざと逆を見る"""
    return list(reversed(names))


def _v_alpha(names, slots, path):
    """名前順。実績にまったく引きずられない、まっさらな視点"""
    return sorted(names)


# 視点 = (名前, 部品の並べ方, 探し方)
#
#   【はじめ失敗したやり方と、その理由】
#     最初は5人ぜんぶ「幅（横に広く）」で、部品の順番だけ変えていた。
#     測ったら、ひとりで探すのと まったく同じ数しか解けなかった。
#
#         考える量      ひとり    5人で合議
#            8通り      2/10      2/10
#           20通り      3/10      3/10
#           40通り      6/10      6/10
#
#     理由は単純で、探し方が同じだと、順番を変えても
#     同じ場所を同じ順に見に行くから。人数だけ増やしても意味がない。
#
#   【直したやり方】
#     半分を「深（一本の道を先まで掘る）」にした。
#     広く見る人と、深く掘る人がいて、はじめて見る場所が変わる。
VIEWS = [
    ("ふつうの人",       _v_normal,       "幅"),
    ("しぼり優先の人",   _v_narrow_first, "幅"),
    ("深く掘る人",       _v_normal,       "深"),
    ("深く掘るへそ曲がり", _v_reverse,     "深"),
    ("深く掘る名前順",   _v_alpha,        "深"),
    ("短く済ます人",     _v_short_first,  "幅"),
]


# ------------------------------------------------------------------
# 手順を1万ビットにする
# ------------------------------------------------------------------
def plan_vec(plan):
    """手順を1本のビット列にする。

    「1番目がさがす」「2番目がしぼる」…を、それぞれ
    ずらし(permute) で順番を表してから、たばねる。
    順番が違えば違うビット列になる。
    """
    if not plan:
        return 0
    return hdv.bundle_bits([hdv.permute(hdv.atom("手:" + n), i + 1)
                            for i, n in enumerate(plan)])


# ------------------------------------------------------------------
# 合議
# ------------------------------------------------------------------
def deliberate(slots, allow=None, per_view=3, budget=400, max_depth=6,
               verbose=True):
    """何人かで考えて、多数決で1つ選ぶ。

    戻り値: (手順, 結果, 記録)  見つからなければ (None, None, 記録)
    """
    import kernel

    t0 = time.time()
    log = {"視点": [], "案": [], "採用": None}
    cands = []                     # [(手順, 結果, 出した視点のならび)]

    # --- ① 何人かに、ちがう順番で探させる ---
    for who, bias, strategy in VIEWS:
        try:
            got = kernel.solve(slots, verbose=False, allow=allow,
                               bias=bias, budget=budget, strategy=strategy,
                               max_depth=max_depth, collect=per_view)
        except Exception as e:
            log["視点"].append((who, f"できなかった（{e}）"))
            continue
        got = got if isinstance(got, list) else ([got] if got and got[0] else [])
        log["視点"].append((who, f"{len(got)} 案"))
        for plan, st in got:
            for c in cands:
                if c[0] == plan:
                    c[2].append(who)
                    break
            else:
                cands.append([list(plan), st, [who]])

    if not cands:
        return None, None, log

    # --- ② ぜんぶ下見で確かめる。通らない案はここで落とす ---
    ok = []
    for plan, st, voters in cands:
        try:
            chk, bad = kernel.try_plan(plan, slots)
        except Exception as e:
            bad, chk = str(e), {}
        good = (not bad) and bool(chk.get("files")) \
            and kernel.goal_reached(chk, slots, plan)
        log["案"].append({"手順": plan, "票": list(voters),
                          "通った": good, "理由": bad or ("" if good else "条件不足")})
        if good:
            ok.append((plan, st, voters))
    if not ok:
        return None, None, log

    # --- ③ 多数決 ---
    #
    # 【はじめ失敗したやり方と、その理由】
    #   最初は「1万ビットでたばねて、真ん中にいちばん近い案」を選んだ。
    #   結果はこうなった:
    #       ✓ さがす → かさなり                       票5
    #       ✓ さがす → つくる → かさなり               票5
    #       ★ さがす → つくる → ふるいじゅん → かさなり  票5  ← 選ばれた
    #   いちばん長い、むだな手が2つ入った案が選ばれてしまった。
    #   理由は単純で、長い案ほど材料が多く、
    #   みんなをたばねた真ん中に「なんとなく近く」なるから。
    #   つまり真ん中との近さは、案の良し悪しではなく長さを測っていた。
    #
    # 【直したやり方】
    #   ① 票の多さ   … 何人がその案にたどりついたか
    #   ② 手数の少なさ … 同じことができるなら短いほうがよい
    #   ③ 真ん中との近さ … ①②が同点のときの、最後の決め手だけに使う
    #
    #   1万ビットのたばねは、ここでは「同点をほどく係」に格下げした。
    #   本当は主役にしたかったが、測ったら主役には向いていなかった。
    vecs, ws = [], []
    for plan, _st, voters in ok:
        vecs.append(plan_vec(plan))
        ws.append(len(voters))
    center = hdv.bundle_bits(vecs, ws)

    scored = []
    for (plan, st, voters), v in zip(ok, vecs):
        scored.append((len(voters), -len(plan), hdv.near(center, v),
                       plan, st, voters))
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    nvote, _neg, near, plan, st, voters = scored[0]

    log["採用"] = {"手順": plan, "票": voters, "近さ": round(near, 3),
                   "案の数": len(cands), "通った案": len(ok),
                   "ミリ秒": round((time.time() - t0) * 1000, 1)}
    if verbose:
        show(log)
    return plan, st, log


def show(log):
    print("  ── 合議 ──")
    for who, r in log["視点"]:
        print(f"     {who:<12} {r}")
    for a in log["案"]:
        mark = "✓" if a["通った"] else "✗"
        print(f"     {mark} {' → '.join(a['手順'])}"
              f"   票{len(a['票'])}"
              + ("" if a["通った"] else f"   （{a['理由']}）"))
    d = log.get("採用")
    if d:
        print(f"     ★ 採用: {' → '.join(d['手順'])}"
              f"   票{len(d['票'])}/{d['通った案']}   "
              f"みんなの真ん中との近さ {d['近さ']}   {d['ミリ秒']}ミリ秒")


if __name__ == "__main__":
    import kernel
    kernel.make_demo()
    for slots in [
        {"動作": "移動", "場所": "Desktop", "種類": "画像", "時期": "去年"},
        {"動作": "数える", "場所": "Downloads", "種類": "PDF"},
        {"動作": "重複", "場所": "Desktop"},
    ]:
        print(f"\n■ {slots}")
        plan, st, log = deliberate(slots)
        print(f"   → {' → '.join(plan) if plan else '見つからず'}")
