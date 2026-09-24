#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grow_all.py -- 辞書ぜんぶを一度なめて、カードを作る

  【この方法は使っていません。記録として残してあります】

  やってみた結果（2026-08-24）:
      ゆるい条件      421 枚  宇宙飛行士→画像、かたゆでたまご→画像
      きつい条件      212 枚  醤油→PDF、エアガン→圧縮
      極端にきつい     30 枚  へび→画像、ふぐ→画像

  条件をどれだけきつくしても質が上がらなかった。理由ははっきりしている。
  「説明の中に『写真』が出てくる」ことと
  「その語がファイルの種類として写真を指す」ことは、別の話だから。
  頭からの位置でも、説明の短さでも、この差は埋められなかった。

  ここから学んだこと:
      札の枚数を増やしても賢くはならない。
      賢さは、部品の組み合わせ方から出てくる。
      札は「その語を聞いたら、どのファイルを指すか」が
      はっきりしているものだけでよく、それは百枚あれば足りる。

  一方で、操作の「言い方」の表（machine.PATTERNS）は増やす価値がある。
  あちらは意味の分類ではなく、動詞の言い回しを写しているだけなので、
  増やせば増やしただけ、素直に効く。

------------------------------------------------------------------
もとの説明:

  grow.py と同じ考え方（説明文で裏を取る）を、108,332語すべてに当てる。
  ただし一気にやると間違いも大量に増えるので、条件をきつくする：

    ・根拠の語は「最初の語義」の中に出てくること
      （後ろの方の語義は、まったく別の意味であることが多い）
    ・根拠になった札は、種類か場所のものだけ（動作・時期は使わない）
    ・答えが1つに決まること（画像と動画が両方出てきたら覚えない）

  結果は grown_cards.json に貯まる。/grown で全部見られるし、消せる。
"""
import os, sys, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import kernel, grow, lookup

# 見出し語として弱いもの。1文字や、記号・数字だけのもの
def _ok_word(w):
    if not (2 <= len(w) <= 12):
        return False
    if w in grow.SKIP or w in kernel.SEED:
        return False
    if any(c.isdigit() for c in w):
        return False
    # ひらがなだけの短い語は、助詞や活用の断片であることが多い
    if len(w) <= 3 and all("぀" <= c <= "ゟ" for c in w):
        return False
    return True


def first_sense(text):
    """説明の最初の1行だけ。後ろの語義は別の意味であることが多い"""
    for line in (text or "").split("\n"):
        line = line.strip()
        if line:
            return line
    return ""


# 説明の中に「写真」が出てくるだけでは足りない。
#   宇宙飛行士 →「…宇宙船に乗り組む人。写真…」→ 写真の一種ではない
#   撮影       →「写真や映画をとること」        → こちらは近い
# 根拠の語が、説明の頭のほうに来ていることを求める。
NEAR = 12          # 根拠の語は、頭から何文字目までに出ること
MAXLEN = 40        # 説明そのものが短いこと（長い説明は話が広がっている）

# 人・場所・団体を表す末尾。これらは「ファイルの種類」ではない
NOT_A_KIND = ("士", "者", "家", "員", "師", "官", "館", "所", "店", "社",
              "会", "школ", "校", "部", "科", "課", "局", "省", "庁",
              "人", "民", "王", "神", "党", "軍", "隊")


def strict_ok(word, body, why):
    """きつい条件。これを通ったものだけ札にする"""
    if len(body) > MAXLEN:
        return False
    if body.find(why) > NEAR:
        return False
    if word.endswith(NOT_A_KIND):
        return False
    return True


def main():
    t0 = time.time()
    d = lookup.Dict()
    # 根拠に使う札は、最初から持っているものだけに固定する
    base = {k: v for k, v in kernel.SEED.items()
            if v[0] in ("種類", "場所") and len(k) >= 2}
    print(f"根拠に使う札: {len(base)} 枚")
    print(f"見る語      : {len(d.idx):,} 語")

    found, seen, out = 0, 0, {}
    for w in d.idx:
        seen += 1
        if seen % 20000 == 0:
            print(f"  {seen:,} 語まで見た（{found} 枚）… {time.time()-t0:.0f}秒")
        if not _ok_word(w):
            continue
        try:
            body = first_sense(d.look(w))
        except Exception:
            continue
        if not body:
            continue
        r = grow.from_definition(w, body, base)
        if not r:
            continue
        slot, val, why = r
        if not strict_ok(w, body, why):
            continue
        out[w] = {"枠": slot, "値": val, "自信": 1.0,
                  "出どころ": f"辞書：最初の語義に「{why}」",
                  "覚えた日": time.strftime("%Y-%m-%d")}
        found += 1

    cur = grow.load()
    cur.update(out)
    grow._save(cur)
    print(f"\n覚えたカード: {found} 枚 （合計 {len(cur)} 枚）")
    print(f"かかった時間: {time.time()-t0:.1f} 秒")

    # 中身を少しだけ見せる（信用してよいか、目で確かめるため）
    print("\n見本:")
    for w, v in list(out.items())[:25]:
        print(f"  {w} → 【{v['値']}】 {v['枠']}   {v['出どころ']}")


if __name__ == "__main__":
    main()
