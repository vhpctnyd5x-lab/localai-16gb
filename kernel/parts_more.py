#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parts_more.py -- kernel.py に足す「部品」の追加箱

kernel.py は一切いじらない。ここに部品(最小単位の操作)を足して、
PARTS_EXTRA / SEED_EXTRA として公開する。

規約(kernel.py と同じ):
  - 部品は def p_xxx(st, slots) -> dict
  - st は壊さない。必ず新しい dict を返す({**st, ...})
  - 前提が満たせないときは例外を投げてよい(探索側が枝を切る)

【安全上の絶対条件】
  下見(dry)かどうかは、モジュール全体のグローバルではなく
  st.get("dry", True) で判断する。既定は True(=下見)。
  dry のときはファイルシステムを1バイトも変更しない。
"""

import re as _re
import os, shutil, hashlib, datetime

# kernel.py の設定(サンドボックスの場所・拡張子表)を借りる。
# 読むだけで、kernel.py は書き換えない。
try:
    from kernel import SANDBOX, EXT
except Exception:  # 単体テストなどで kernel が読めないとき用の控え
    SANDBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sandbox")
    EXT = {
        "画像":     {".png", ".jpg", ".jpeg", ".gif", ".heic", ".webp"},
        "PDF":      {".pdf"},
        "動画":     {".mp4", ".mov", ".avi", ".mkv"},
        "テキスト": {".txt", ".md", ".rtf"},
    }

def _trash_dir():
    """ゴミ箱の場所。練習中は練習用フォルダの中に置く。

    ここを常に ~/.Trash にしていたため、練習モードなのに
    本物のゴミ箱へファイルが出ていってしまった（練習の外に出ていた）。
    練習は練習の中で完結させる。
    """
    import kernel as _k
    if _k.ROOT == "real":
        return os.path.expanduser("~/.Trash")
    # ここで作ってはいけない。
    # 「場所はどこか」を尋ねただけで フォルダができてしまう。
    # 下見(dry)や、答えの文を組み立てるだけの所からも呼ばれるので、
    # 数えるだけの問いでも ごみ箱フォルダが増えていた
    # （作った問題500問のうち48問で 場が変わっていた）。
    # 本当に捨てるときに、捨てる側で作る。
    return os.path.join(_k.SANDBOX, "ごみ箱")


def _trash_dir_tsukuru():
    """本当に捨てる直前に、ゴミ箱を用意する"""
    d = _trash_dir()
    if not d.startswith(os.path.expanduser("~/.Trash")):
        os.makedirs(d, exist_ok=True)
    return d


TRASH = os.path.expanduser("~/.Trash")   # 本番用（後方互換）


# ============================================================
# 小道具
# ============================================================
def _is_dry(st):
    """下見モードか? 既定は True(安全側に倒す)"""
    return bool(st.get("dry", True))


def _need_files(st):
    """files が用意されているか確認して返す"""
    fs = st.get("files")
    if fs is None:
        raise Exception("まだファイルを集めていない")
    return list(fs)


def _human(n):
    """バイト数を人間が読める形に"""
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            return (f"{int(x)} {u}" if u == "B" else f"{x:.1f} {u}")
        x /= 1024


def _uniq_dest(dirpath, name):
    """同名衝突したら 連番 を足した空きパスを返す"""
    base, ext = os.path.splitext(name)
    cand = os.path.join(dirpath, name)
    i = 1
    while os.path.exists(cand):
        cand = os.path.join(dirpath, f"{base} {i}{ext}")
        i += 1
    return cand


def _quick_sig(path, head=64 * 1024):
    """
    巨大ファイルでも遅くならない「粗い指紋」。
    先頭 head バイトと末尾 head バイトだけを読んでハッシュする。
    (サイズで先にグループ分けしてから使う前提)
    """
    size = os.path.getsize(path)
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as f:
        h.update(f.read(head))
        if size > head * 2:
            f.seek(-head, os.SEEK_END)
            h.update(f.read(head))
    return h.hexdigest()


def _same_content(a, b, chunk=1024 * 1024):
    """最後の詰め : 本当に中身が同じかを一度だけきっちり比べる"""
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            ca, cb = fa.read(chunk), fb.read(chunk)
            if ca != cb:
                return False
            if not ca:
                return True


# ============================================================
# 読み取り系(安全)
# ============================================================
def p_dive(st, slots):
    """もぐる : サブフォルダも含めて再帰的に集める

    「その場所に何がある？」と聞かれているのに、奥まで潜って
    サブフォルダの中身を並べるのは、聞かれたことへの答えではない。
    だから、その場所に見えているものが在るなら、自分から降りる。
    （しわけ が「絞り込みがあるなら使わない」と降りるのと同じ）

    実際に起きていた事故:
      デスクトップに PDF / 画像 / 整理済み_2026-06-17 の3つが在る状態で
      「デスクトップには何がある？」と聞いたら、
      3つのフォルダではなく、その中の 46個 のファイル名が並んでいた。
    """
    # 場所の解決は必ず kernel 側に任せる（本番では安全層の関所を通るため）
    if st.get("src"):
        d = st["src"]
    else:
        import kernel as _k
        d = _k.dig_into(_k.place_dir(slots["場所"]), slots)
    if not os.path.isdir(d):
        raise Exception(f"{d} が無い")

    # 奥まで見ろと言われたか？（「サブフォルダ」「中まで」「奥まで」など）
    iwareta = slots.get("動作") == "もぐる" or slots.get("深く")
    if not iwareta:
        # その場所に、見えているものが在るなら、そこで足りている
        try:
            mieru = [x for x in os.listdir(d) if not x.startswith(".")]
        except OSError:
            mieru = []
        if mieru:
            raise Exception("その場所に見えているもので足りるので、奥までは見ない")
    fs = []
    for root, dirs, names in os.walk(d):
        dirs[:] = [x for x in dirs if not x.startswith(".")]   # 隠しフォルダは見ない
        for n in names:
            if n.startswith("."):
                continue
            p = os.path.join(root, n)
            if os.path.isfile(p):
                fs.append(p)
    # 「もともと何件あったか」を控える。さがす だけに入れて
    # こちらに入れ忘れたため、もぐる で始まる手順が
    # 「未記録＝0件」と読まれ、即打ち切られていた（実測 24/40 → 0/40）
    return {**st, "files": fs, "src": d, "もと": len(fs)}


# 絞り込んだら、フォルダは持ち越さない（kernel.p_search が dirs を入れてくる）。
# フォルダには拡張子も中身の大きさも無いので、
# 絞り込みを言われた時点で相手はファイルに決まる。
def _dirs_nashi(st):
    return {k: v for k, v in st.items() if k != "dirs"}


def p_filter_size(st, slots):
    """
    しぼる(大きさ) : slots["大きさ"] が「大きい」なら上位、「小さい」なら下位に絞る。
    しきい値は「中央値」。全部同じ大きさだと絞れないので、その時は例外。
    """
    fs = _need_files(st)
    if len(fs) < 2:
        raise Exception("大きさで絞るには2個以上いる")
    sizes = sorted(os.path.getsize(f) for f in fs)
    mid = sizes[len(sizes) // 2]
    want = slots["大きさ"]
    if want == "大きい":
        out = [f for f in fs if os.path.getsize(f) >= mid]
    else:
        out = [f for f in fs if os.path.getsize(f) <= mid]
    if not out or len(out) == len(fs):
        raise Exception("大きさで分けられなかった")
    return {**_dirs_nashi(st), "files": out}


def p_filter_name(st, slots):
    """しぼる(名前) : slots["名前"] を含む名前のファイルだけ"""
    fs = _need_files(st)
    key = str(slots["名前"]).lower()
    out = [f for f in fs if key in os.path.basename(f).lower()]
    return {**_dirs_nashi(st), "files": out}


def p_except_kind(st, slots):
    """のぞく(種類) : その種類「以外」だけを残す

    「画像以外を数えて」のような、裏返しの言い方に答えるため。
    しぼる(種類) の逆。
    """
    import kernel as _k
    exts = _k.EXT[slots["除く"]]
    fs = [f for f in _need_files(st)
          if os.path.splitext(f)[1].lower() not in exts]
    return {**_dirs_nashi(st), "files": fs}


def p_dup(st, slots):
    """
    かさなり : 中身が同一のファイル(重複)を見つける(終端)

    速さの工夫:
      1) まずサイズでグループ分け(読み込み0回)
      2) 同じサイズの中だけ、先頭+末尾のバイトの粗いハッシュで分ける
      3) それでも同じ組だけ、最後に全体を1回だけ突き合わせる
    """
    fs = _need_files(st)
    by_size = {}
    for f in fs:
        try:
            n = os.path.getsize(f)
        except OSError:
            continue
        # 中身が空のファイル同士は、たしかに一致するが「同じ写真が2枚ある」
        # という意味ではない。空は空として、重複から外す
        if n == 0:
            continue
        by_size.setdefault(n, []).append(f)

    groups = []
    for size, cand in by_size.items():
        if len(cand) < 2:
            continue
        by_sig = {}
        for f in cand:
            try:
                by_sig.setdefault(_quick_sig(f), []).append(f)
            except OSError:
                continue
        for sig, same in by_sig.items():
            if len(same) < 2:
                continue
            # 粗いハッシュが一致した組を、実際の中身で確定させる
            rest = list(same)
            while rest:
                head = rest.pop(0)
                grp = [head]
                keep = []
                for other in rest:
                    if _same_content(head, other):
                        grp.append(other)
                    else:
                        keep.append(other)
                rest = keep
                if len(grp) > 1:
                    groups.append(sorted(grp))

    groups.sort(key=lambda g: os.path.basename(g[0]))
    if not groups:
        answer = "重複はありませんでした"
        flat = []
    else:
        lines = []
        flat = []
        for g in groups:
            lines.append("  ・" + " = ".join(os.path.basename(x) for x in g))
            flat.extend(g)
        answer = f"中身が同じ組が {len(groups)} 組ありました\n" + "\n".join(lines)
    return {**st, "files": flat, "dups": groups, "answer": answer}


def p_total_size(st, slots):
    """おおきさ : 合計サイズを人間が読める形で答える(終端)"""
    fs = _need_files(st)
    total = 0
    for f in fs:
        try:
            total += os.path.getsize(f)
        except OSError:
            pass
    return {**st, "total_bytes": total,
            "answer": f"{len(fs)} 個で 合計 {_human(total)}"}


def p_sort_old(st, slots):
    """ふるいじゅん : 古い順(更新日時の古い方が先)に並べ替え"""
    fs = _need_files(st)
    fs.sort(key=lambda f: os.path.getmtime(f))
    names = [os.path.basename(f) for f in fs]
    return {**st, "files": fs, "並んだ": True,
            "answer": "\n".join("  - " + n for n in names)}


def p_sort_big(st, slots):
    """おおきいじゅん : 大きい順に並べ替え"""
    fs = _need_files(st)
    fs.sort(key=lambda f: os.path.getsize(f), reverse=True)
    names = [f"{os.path.basename(f)}（{_human(os.path.getsize(f))}）" for f in fs]
    return {**st, "files": fs, "並んだ": True,
            "answer": "\n".join("  - " + n for n in names)}


def p_taishou(st, slots):
    """しぼる(対象) : ファイルだけ／フォルダだけ に絞る

    「デスクトップにフォルダはいくつ」で 8個 と答えていた。
    札は 対象=フォルダ を引けていたのに、それを見る部品が無く、
    引いた札が どこにも使われないまま捨てられていた。
    """
    t = (slots or {}).get("対象")
    if t == "フォルダ":
        return {**st, "files": [], "dirs": st.get("dirs") or []}
    if t == "ファイル":
        return {k: v for k, v in st.items() if k != "dirs"}
    raise Exception("対象が言われていない")


def p_sort_new(st, slots):
    """あたらしいじゅん : 新しい順(更新日時の新しい方が先)に並べ替え

    「いちばん新しいのは」に答えられなかったので足した。
    並べ替えは 古い順 の向きを変えるだけ。
    """
    fs = _need_files(st)
    fs.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    names = [os.path.basename(f) for f in fs]
    return {**st, "files": fs, "並んだ": True,
            "answer": "\n".join("  - " + n for n in names)}


def p_sort_small(st, slots):
    """ちいさいじゅん : 小さい順に並べ替え

    「いちばん小さいのは」に答えられなかったので足した。
    """
    fs = _need_files(st)
    fs.sort(key=lambda f: os.path.getsize(f))
    names = [f"{os.path.basename(f)}（{_human(os.path.getsize(f))}）" for f in fs]
    return {**st, "files": fs, "並んだ": True,
            "answer": "\n".join("  - " + n for n in names)}


# ============================================================
# 変更系(危険なので慎重に)
# ============================================================
def p_rename(st, slots):
    """
    なまえかえ : slots に基づく連番リネーム(終端)

    名前の元は slots["名前"] → 種類 → 時期 → 「ファイル」の順で決める。
    「<元> 01.jpg」のように、拡張子は元のまま。
    dry のときは、つけるはずの名前を計算するだけで、実際には変えない。
    """
    fs = _need_files(st)
    if not fs:
        raise Exception("名前を変える相手がいない")
    # 「新名」＝これから付ける名前。言われていれば、それがいちばん強い。
    # ここを見ていなかったので「名前を旅行に変えて」が
    # 「名前01.jpg」になり、言われた「旅行」が捨てられていた。
    base = (slots.get("新名") or slots.get("名前") or slots.get("種類")
            or slots.get("時期") or "ファイル")
    dry = _is_dry(st)

    fs = sorted(fs, key=lambda f: os.path.getmtime(f))
    out, pairs, real_pairs = [], [], []
    used = set()
    for i, f in enumerate(fs, 1):
        d = os.path.dirname(f)
        ext = os.path.splitext(f)[1]
        newname = f"{base}{i:02d}{ext}"
        target = os.path.join(d, newname)
        # 衝突を避ける(下見でも同じ計算になるよう used で管理)
        if target != f and (target in used or os.path.exists(target)):
            target = _uniq_dest(d, newname)
        used.add(target)
        if not dry and target != f:
            os.rename(f, target)
        out.append(target)
        pairs.append((os.path.basename(f), os.path.basename(target)))
        if target != f:
            # 下見のときも「どこへ行くか」を残す。
            # 以前は not dry の時しか残していなかったので、
            # 仮想に渡すものが空になり、
            # 「動くものはありません」と表示した直後に
            # 5件の名前を変えていた（実測で再現）。
            # p_trash では直してあったのに、ここだけ残っていた。
            real_pairs.append((f, target))

    head = "（下見）" if dry else ""
    lines = [f"  {a} → {b}" for a, b in pairs]
    return {**st, "files": out, "renamed": len(out),
            "pairs": st.get("pairs", []) + real_pairs,
            "answer": f"{head}{len(out)} 個の名前を変えました\n" + "\n".join(lines)}


def p_trash(st, slots):
    """
    ごみばこ : ゴミ箱へ移すだけ(終端)

    本番では macOS のゴミ箱(~/.Trash)、練習では sandbox/ごみ箱。

    【重要】完全削除は絶対にしない。os.remove / shutil.rmtree は使わない。
    同名がすでにゴミ箱にあるときは連番を付ける。
    dry のときは何もしない(移したつもりの答えだけ返す)。
    """
    fs = _need_files(st)
    if not fs:
        raise Exception("捨てる相手がいない")
    dry = _is_dry(st)
    trash = _trash_dir() if dry else _trash_dir_tsukuru()
    if not dry and not os.path.isdir(trash):
        raise Exception("ゴミ箱フォルダが見つからない")

    done, real_pairs = [], []
    for f in fs:
        name = os.path.basename(f)
        if dry:
            # 下見でも「どこへ行くか」を残す。
            # 残していなかったので、下見の欄に何も出ず、
            # 「消して」と言ったのに何が消えるのか見えなかった
            done.append(name)
            real_pairs.append((f, os.path.join(trash, name)))
            continue
        target = _uniq_dest(trash, name)
        shutil.move(f, target)      # 移動のみ。削除はしない
        done.append(os.path.basename(target))
        real_pairs.append((f, target))

    head = "（下見）" if dry else ""
    where = "ゴミ箱" if _trash_dir().startswith(os.path.expanduser("~/.Trash")) \
        else "練習用のゴミ箱"
    return {**st, "files": [], "trashed": len(done), "trashed_names": done,
            "pairs": st.get("pairs", []) + real_pairs,
            "answer": f"{head}{len(done)} 個を{where}へ移しました（削除はしていません）\n"
                      + "\n".join("  - " + n for n in done)}


def p_html(st, slots):
    """HTMLをつくる : ブラウザで開けるページを1枚つくる(終端)

    種類や時期で絞ったあとに置くと、その中身の一覧ページになる。
    何も無ければ、白紙のひな形になる。
    """
    import html_make
    import kernel as _k
    place = slots.get("場所") or "Desktop"
    d = _k.dig_into(_k.place_dir(place), slots) or _k.place_dir(place)
    if not os.path.isdir(d):
        raise Exception(f"{place} が見つからない")

    title = slots.get("名前") or slots.get("題") or None
    fs = st.get("files")
    if fs:
        body = html_make.listing_body(fs, place)
        title = title or f"{place} の中身"
        name = title
    else:
        title = title or "あたらしいページ"
        body = html_make.blank_body(title)
        name = title

    if _is_dry(st):
        return {**st, "created": name,
                "answer": f"（下見）{name}.html を {place} に作ります"}
    path = html_make.write(d, name, title, body)
    n = len(fs) if fs else 0
    what = f"{n} 個ぶんを載せました" if n else "白紙のひな形です"
    return {**st, "created": path,
            "answer": f"{os.path.basename(path)} を {place} に作りました\n"
                      f"  {what}（{os.path.getsize(path)} バイト）\n"
                      f"  そのままブラウザで開けます"}


# ============================================================
# 公開するもの
# ============================================================
PARTS_EXTRA = {
    "もぐる":         dict(fn=p_dive,        needs=["場所"],   uses_files=False, terminal=False),
    "しぼる(大きさ)": dict(fn=p_filter_size, needs=["大きさ"], uses_files=True,  terminal=False),
    "しぼる(名前)":   dict(fn=p_filter_name, needs=["名前"],   uses_files=True,  terminal=False),
    "のぞく(種類)":   dict(fn=p_except_kind, needs=["除く"],   uses_files=True,  terminal=False),
    "HTMLをつくる":   dict(fn=p_html,        needs=[],         uses_files=True,  terminal=True),
    "ふるいじゅん":   dict(fn=p_sort_old,    needs=[],         uses_files=True,  terminal=False),
    "おおきいじゅん": dict(fn=p_sort_big,    needs=[],         uses_files=True,  terminal=False),
    "しぼる(対象)":   dict(fn=p_taishou,    needs=["対象"],   uses_files=True,  terminal=False),
    "あたらしいじゅん": dict(fn=p_sort_new,  needs=[],         uses_files=True,  terminal=False),
    "ちいさいじゅん": dict(fn=p_sort_small,  needs=[],         uses_files=True,  terminal=False),
    "かさなり":       dict(fn=p_dup,         needs=[],         uses_files=True,  terminal=True),
    "おおきさ":       dict(fn=p_total_size,  needs=[],         uses_files=True,  terminal=True),
    "なまえかえ":     dict(fn=p_rename,      needs=[],         uses_files=True,  terminal=True),
    "ごみばこ":       dict(fn=p_trash,       needs=[],         uses_files=True,  terminal=True),
}

# 新しく増えた概念スロットを言葉から拾うためのカード
SEED_EXTRA = {
    # --- 大きさ ---
    "でかい":   ("大きさ", "大きい"), "大きい": ("大きさ", "大きい"),
    "おおきい": ("大きさ", "大きい"), "重い":   ("大きさ", "大きい"),
    "巨大":     ("大きさ", "大きい"), "容量食": ("大きさ", "大きい"),
    "小さい":   ("大きさ", "小さい"), "ちいさい": ("大きさ", "小さい"),
    "軽い":     ("大きさ", "小さい"), "細かい": ("大きさ", "小さい"),
    # --- 動作(このファイルで増えたもの) ---
    "もぐ":     ("動作", "もぐる"),   "サブフォルダ": ("動作", "もぐる"),
    "奥まで":   ("動作", "もぐる"),   "中まで": ("動作", "もぐる"),
    "重複":     ("動作", "重複"),     "かぶ":   ("動作", "重複"),
    "だぶ":     ("動作", "重複"),     "同じファイル": ("動作", "重複"),
    "容量":     ("動作", "大きさ"),   "サイズ": ("動作", "大きさ"),
    "何メガ":   ("動作", "大きさ"),   "合計":   ("動作", "大きさ"),
    "名前変":   ("動作", "改名"),     "リネーム": ("動作", "改名"),
    "連番":     ("動作", "改名"),     "名前をそろ": ("動作", "改名"),
    "ゴミ箱":   ("動作", "ごみばこ"), "ごみ箱": ("動作", "ごみばこ"),
    "捨て":     ("動作", "ごみばこ"), "いらな": ("動作", "ごみばこ"),
    "削除":     ("動作", "ごみばこ"),
    # --- 並べ方 ---
    "古い順":   ("並べ方", "古い順"), "ふるい順": ("並べ方", "古い順"),
    "大きい順": ("並べ方", "大きい順"), "でかい順": ("並べ方", "大きい順"),
    "新しい順": ("並べ方", "新しい順"), "あたらしい順": ("並べ方", "新しい順"),
    "小さい順": ("並べ方", "小さい順"), "ちいさい順": ("並べ方", "小さい順"),
}


# ============================================================
# 追加(2026-08-24): つくる系
#   「デスクトップにファイルを作って」に答えられなかったので足す
# ============================================================
def p_touch(st, slots):
    """ファイルをつくる : テキストファイルを1つ作る"""
    import datetime as _dt
    import kernel as _k
    if slots.get("対象") == "フォルダ":
        raise Exception("フォルダを頼まれている")
    d = st.get("src") or _k.place_dir(slots["場所"])
    if not os.path.isdir(d):
        raise Exception(f"{d} が無い")
    # フォルダと同じ関所を通す。前は生のまま使っていたので、
    # 読み取りがくずれると「というファイル.txt」が出来ていた。
    name = _namae_wo_totonoeru(slots.get("名前"))
    if not name:
        name = "メモ_" + _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".txt"
    if not os.path.splitext(name)[1]:
        name += ".txt"
    p = os.path.join(d, name)
    n = 1
    while os.path.exists(p):                      # 上書きは絶対にしない
        base, ext = os.path.splitext(name)
        p = os.path.join(d, f"{base} {n}{ext}"); n += 1
    body = slots.get("中身", "")
    if not st.get("dry", True):
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
    return {**st, "src": d, "files": [p], "created": p,
            "answer": ("（下見）" if st.get("dry", True) else "")
                      + f"{os.path.basename(p)} を {os.path.basename(d)} に作りました"}


# 名前として受け取ってはいけない、読み取りのくずれ
_KUZURE_ATAMA = ("という", "といった", "と言う", "と言った", "いう", "言う")
# 名前ではなく「種別」そのもの。これだけ渡ってきたら 読み取りに失敗している
_SHUBETSU = {"フォルダ", "ファイル", "名前", "フオルダ", "ホルダ", "ディレクトリ"}


def _namae_wo_totonoeru(name):
    """フォルダ名として使ってよい形に整える。使えなければ None。

    ★ ここは **行動の直前** なので、上流の読み取りが何を渡してきても
      おかしな名前で本物のフォルダを作らせないための 最後の関所。

      実際に起きた（2026-09-06）:
        「デスクトップに 試験用 というフォルダをつくる」
        → 本物のデスクトップに **「というフォルダ」** という名前の
          フォルダが出来た。しかも一度できると、それが
          「実在するフォルダ名」として最優先で守られ、
          **間違いが正解として固定される**。
      上流（grammar.py の文節まとめ、kernel.py の名前取り）は直したが、
      名前が決まる経路は複数あるので、**ここでも必ず見る。**
    """
    n = (name or "").strip()
    for a, b in ("「」", "『』", '""', "''", "（）", "()"):
        while len(n) >= 3 and n[0] == a and n[-1] == b:
            n = n[1:-1].strip()
    # 片方だけ残ることがある（文節が括弧の中の空白で切れると
    # 『まとめ 2026』が「2026』」になる）。閉じ括弧だけ、開き括弧だけも落とす。
    n = n.strip("「」『』（）()\"'" + "　 ")
    for atama in _KUZURE_ATAMA:
        if n.startswith(atama):
            n = n[len(atama):].strip()
            break
    n = _re.sub(r'[/\\:*?"<>|\x00-\x1f]', "", n).strip(" .　")
    if not n or n in _SHUBETSU or len(n) > 80:
        return None
    return n


def p_mkfolder(st, slots):
    """フォルダをつくる : 名前つきのフォルダを1つ作る"""
    import datetime as _dt
    import kernel as _k
    if slots.get("対象") == "ファイル":
        raise Exception("ファイルを頼まれている")
    d = st.get("src") or _k.place_dir(slots["場所"])
    if not os.path.isdir(d):
        raise Exception(f"{d} が無い")
    name = _namae_wo_totonoeru(slots.get("名前")) or (
        "新しいフォルダ_" + _dt.datetime.now().strftime("%Y-%m-%d"))
    p = os.path.join(d, name)
    n = 1
    while os.path.exists(p):
        p = os.path.join(d, f"{name} {n}"); n += 1
    if not st.get("dry", True):
        os.makedirs(p)
    return {**st, "src": d, "files": [], "created": p,
            "answer": ("（下見）" if st.get("dry", True) else "")
                      + f"{os.path.basename(p)} というフォルダを作りました"}


PARTS_EXTRA["ファイルをつくる"] = dict(fn=p_touch,    needs=["場所"],
                                   uses_files=False, terminal=True)
PARTS_EXTRA["フォルダをつくる"] = dict(fn=p_mkfolder, needs=["場所"],
                                   uses_files=False, terminal=True)

SEED_EXTRA.update({
    "フォルダ":     ("対象", "フォルダ"), "ふぉるだ": ("対象", "フォルダ"),
    "ディレクトリ": ("対象", "フォルダ"),
    "ファイル":     ("対象", "ファイル"), "ふぁいる": ("対象", "ファイル"),
    "テキストファイル": ("対象", "ファイル"),
    "作って":   ("動作", "作成"), "つくって": ("動作", "作成"),
    "作成":     ("動作", "作成"), "つくる":   ("動作", "作成"),
    "生成":     ("動作", "作成"), "新規":     ("動作", "作成"),
    "作れる":   ("動作", "作成"), "用意":     ("動作", "作成"),
})
