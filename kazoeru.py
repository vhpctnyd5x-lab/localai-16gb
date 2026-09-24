"""閉じた電卓（2026-09-23）。ローカル LLM は式を書くだけ、数える・計算するのはこちら。
数え上げ（kazoeru）と ふつうの計算（keisan）の 2つ。Python だけで動く（Mac の機能もネットも使わない）。

ローカル LLM に渡すのはシェルではない。受け付けるのは次の形の文字だけ:
    変数: x 0 27        ← 名前・下限・上限（整数）
    条件: 3*x+5*y+8*z == 83
使える記号は 変数名・整数・+ - * // % ・比較（== != < <= > >=）・and or not・かっこ だけ。
関数呼び出し・属性・文字列・添字は ast の段階で断る。総当たりは 6千万通りまで。
"""
import ast, itertools, re

GENKAI = 60_000_000   # 条件は 1つの関数に組んでから回すので 6千万通りで 20秒ほど
_YOI = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
        ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod, ast.Compare, ast.Eq, ast.NotEq,
        ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Name, ast.Load, ast.Constant)

SYSTEM = ("あなたは数え上げの式を書く係です。問題を数えず、式だけを書きます。出力は次の形の行だけ（説明なし）:\n"
          "変数: <名前> <最小> <最大>   ← 数える物ごとに1行。最大は条件から分かる上限\n"
          "条件: <式>                  ← 満たすべき条件。1行に1つ。何行でもよい\n"
          "式に使えるのは 変数名・整数・+ - * // %・== != < <= > >=・and or not・かっこ だけ。\n"
          "問いに関係ない数（別の人・別件・別の用途の数）は式に入れないこと。上限は変数の行にだけ書き、条件に書き写さないこと。\n"
          "例: 2円と5円の硬貨で合計20円（どちらも0枚以上）。店の人は30円持っていた →\n"
          "変数: a 0 10\n変数: b 0 4\n条件: 2*a+5*b == 20\n（30円は別の人の数なので使わない）")


def _anzen(src):
    if re.search(r"[#\n\r;\\]", src):   # 組み立てるときに 後ろの条件を消せる字は断る
        raise ValueError("使えない字")
    t = ast.parse(src, mode="eval")
    for n in ast.walk(t):
        if not isinstance(n, _YOI):
            raise ValueError("使えない書き方: " + type(n).__name__)
        if isinstance(n, ast.Constant) and not isinstance(n.value, int):
            raise ValueError("整数だけ")
    return compile(t, "<条件>", "eval"), src


def yomu(text):
    """ローカル LLM の出力 → (変数 [(名,下,上)], 条件 [code])。読めなければ ValueError。"""
    hensu, jouken = [], []
    for ln in (text or "").splitlines():
        ln = ln.strip().strip("`").replace("＝", "=").replace("：", ":")
        m = re.match(r"変数\s*:\s*([A-Za-z_]\w*)\s+(-?\d+)\s+(-?\d+)\s*$", ln)
        if m:
            hensu.append((m.group(1), int(m.group(2)), int(m.group(3)))); continue
        m = re.match(r"条件\s*:\s*(.+)$", ln)
        if m:
            jouken.append(_anzen(m.group(1)))
    if not hensu or not jouken:
        raise ValueError("変数か条件が無い")
    names = [h[0] for h in hensu]
    if len(set(names)) != len(names):
        raise ValueError("変数名の重なり")
    for c, _ in jouken:
        for nm in c.co_names:
            if nm not in names and nm not in ("and", "or", "not"):
                raise ValueError("知らない名前: " + nm)
    n = 1
    for _, lo, hi in hensu:
        if hi < lo:
            raise ValueError("上限が下限より小さい")
        n *= hi - lo + 1
    if n > GENKAI:
        raise ValueError("総当たりが大きすぎる: %d" % n)
    return hensu, jouken


def kazoeru(text):
    hensu, jouken = yomu(text)
    names = [h[0] for h in hensu]
    # 検査を通った式（変数名・整数・演算子だけ）を 1つの関数に組む。1通りごとに式を読み直さない。
    f = eval("lambda %s: %s" % (",".join(names), " and ".join("(%s)" % src for _, src in jouken)),
             {"__builtins__": {}})
    return sum(1 for vals in itertools.product(*[range(lo, hi + 1) for _, lo, hi in hensu]) if f(*vals))


SYSTEM_KEISAN = ("あなたは文章題を式にする係です。計算はしません。出力は次の3行だけ（説明なし）:\n"
                 "使う: <計算に使う数と意味>\n使わない: <問いに関係ない数と理由。無ければ なし>\n"
                 "式: <答えを出す1本の式>\n"
                 "式に使えるのは 数・+ - * / // %・かっこ だけ（単位や文字は書かない）。\n"
                 "例: 箱に40個。12個入りを3袋足し、25個売れた。隣の店は60個持っている →\n"
                 "使う: 初め40個、12個×3袋を足す、25個売れた\n使わない: 60個（隣の店の数）\n式: 40 + 12*3 - 25")
_KEISAN_YOI = (ast.Expression, ast.UnaryOp, ast.USub, ast.UAdd, ast.BinOp, ast.Add, ast.Sub, ast.Mult,
               ast.Div, ast.FloorDiv, ast.Mod, ast.Constant, ast.Load)


def keisan(text):
    """ローカル LLM の出力の「式:」の行を 分数で正確に計算する。読めなければ ValueError。"""
    from fractions import Fraction
    m = re.findall(r"^\s*式\s*[:：]\s*(.+?)\s*$", text or "", re.M)
    if not m:
        raise ValueError("式が無い")
    src = m[-1].translate(str.maketrans("０１２３４５６７８９（）×÷－＋．，", "0123456789()*/-+.,")).replace(",", "").rstrip("。")
    src = re.sub(r"\s*[=＝].*$", "", src)                        # 「= 答え」まで書いたら式だけにする
    if re.search(r"[#\n\r;\\]", src) or len(src) > 300:
        raise ValueError("使えない字")
    t = ast.parse(src, mode="eval")
    for n in ast.walk(t):
        if not isinstance(n, _KEISAN_YOI) or (isinstance(n, ast.Constant) and not isinstance(n.value, (int, float))):
            raise ValueError("使えない書き方: " + type(n).__name__)

    def ev(n):
        if isinstance(n, ast.Expression): return ev(n.body)
        if isinstance(n, ast.Constant): return Fraction(str(n.value))
        if isinstance(n, ast.UnaryOp): return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        a, b = ev(n.left), ev(n.right)
        if isinstance(n.op, (ast.Mult,)) and (abs(a) > 10**12 or abs(b) > 10**12): raise ValueError("大きすぎる")
        return {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b, ast.Div: lambda: a / b,
                ast.FloorDiv: lambda: a // b, ast.Mod: lambda: a % b}[type(n.op)]()
    v = ev(t)
    return int(v) if v.denominator == 1 else float(round(v, 6))


SYSTEM_JIKAN = ("あなたは時刻の問題を書き出す係です。計算はしません。出力は次の行だけ（説明なし）:\n"
                "始め: <月>/<日> <時>:<分>\n終わり: <月>/<日> <時>:<分>\n"
                "引く: <分>  または  引く: <月>/<日> <時>:<分> - <月>/<日> <時>:<分>   ← 途中で止めた・休んだ分。1回ごとに1行。無ければ 0\n"
                "毎日引く: <時>:<分>-<時>:<分>   ← 毎日決まって止める時間帯（夜をまたいでよい）。無ければ書かない\n"
                "足す: <分>   ← 足す分。無ければ 0\n単位: 分 か 時間\n"
                "日付が無い問題は 始めと終わりを同じ日付 1/1 にし、終わりが翌日なら 1/2 にする。"
                "予定と実際の差（遅れ・早まり）は 始め=予定の時刻、終わり=実際の時刻。\n"
                "例: 9月8日21時35分に始め、9月10日0時20分に終えた。9月9日1時から1時15分まで止めた。何分か →\n"
                "始め: 9/8 21:35\n終わり: 9/10 0:20\n引く: 9/9 1:00 - 9/9 1:15\n足す: 0\n単位: 分\n"
                "例: 9月1日14時に点け、9月3日10時に消した。毎晩22時に消し翌朝6時に点ける。点いていたのは何分か →\n"
                "始め: 9/1 14:00\n終わり: 9/3 10:00\n毎日引く: 22:00-6:00\n足す: 0\n単位: 分")


def jikan(text, nen=2026):
    """時刻の書き出し → 分（または時間）。読めなければ ValueError。うるう年の 2/29 は扱わない。
    引く は 分の数か 時間帯（何行でも）。毎日引く は 毎日の時間帯（始め〜終わりと重なる分だけ引く）。"""
    import datetime as dt
    D = r"(\d{1,2})\s*/\s*(\d{1,2})\s+(\d{1,2})\s*[:：]\s*(\d{1,2})"
    def hi(mo, d, h, mi):
        return dt.datetime(nen, int(mo), int(d)) + dt.timedelta(hours=int(h), minutes=int(mi))   # 24:00 も通す
    def toru(k):
        m = re.search(r"^\s*%s\s*[:：]\s*%s" % (k, D), text or "", re.M)
        if not m:
            raise ValueError(k + "が無い")
        return hi(*m.groups())
    def kasanari(s, e):   # [s, e) と [a, b) の重なり（分）
        return max(0, int((min(e, b) - max(s, a)).total_seconds() // 60))
    a, b = toru("始め"), toru("終わり")
    if b < a:
        raise ValueError("終わりが始めより前")
    hiku = 0
    for g in re.findall(r"^\s*引く\s*[:：]\s*(.+)$", text or "", re.M):
        m = re.match(r"%s\s*[-－~〜から]+\s*%s" % (D, D), g.strip())
        if m:
            s, e = hi(*m.groups()[:4]), hi(*m.groups()[4:])
            if e <= s:
                raise ValueError("引くの時間帯が逆")
            hiku += kasanari(s, e)
        elif re.match(r"^\d+", g.strip()):   # 「50（点検）」のような添え書きは読み飛ばす
            hiku += int(re.match(r"\d+", g.strip()).group())
        else:
            raise ValueError("引くが読めない")
    for g in re.findall(r"^\s*毎日引く\s*[:：]\s*(\d{1,2})\s*[:：]\s*(\d{1,2})\s*[-－~〜から]+\s*(\d{1,2})\s*[:：]\s*(\d{1,2})", text or "", re.M):
        h1, m1, h2, m2 = map(int, g)
        nagasa = (h2 * 60 + m2 - h1 * 60 - m1) % 1440 or 1440
        hi0 = dt.datetime(a.year, a.month, a.day) - dt.timedelta(days=1)   # 前の晩から始まる分も数える
        while hi0 < b:
            s = hi0 + dt.timedelta(hours=h1, minutes=m1)
            hiku += kasanari(s, s + dt.timedelta(minutes=nagasa))
            hi0 += dt.timedelta(days=1)
    m = re.search(r"^\s*足す\s*[:：]\s*(\d+)", text or "", re.M)
    fun = int((b - a).total_seconds() // 60) - hiku + (int(m.group(1)) if m else 0)
    if re.search(r"^\s*単位\s*[:：]\s*時間", text or "", re.M):
        return fun // 60 if fun % 60 == 0 else round(fun / 60, 4)
    return fun


SYSTEM_NARABE = ("あなたは並べ方・順位の問題を書き出す係です。数えたり解いたりしません。出力は次の行だけ（説明なし）:\n"
                 "並べる: <並べる物の名前を空白区切り。問題文の呼び名をそのまま（さん・くん等は付けない）。名前の無い残りは まとめて 他<個数>。合計が並べる数になること>\n"
                 "条件: <式>   ← 1行に1つ。各名前は その物の位置（1番目=1）を表す整数\n"
                 "問う: 数   ← 並べ方の数を答えるとき\n問う: <名前>   ← その物の位置（何番目）を答えるとき\n"
                 "式に使えるのは 名前・整数・+ - * // %・== != < <= > >=・and or not・かっこ だけ。\n"
                 "隣り合う: (青木-井上)*(青木-井上) == 1 ／ 隣り合わない: (青木-井上)*(青木-井上) != 1 ／ 青木が井上より前: 青木 < 井上 ／ 両端: 青木 == 1 or 青木 == 5\n"
                 "同じ種類が何個もある（どれも区別する）ときは 並べる に <種類>×<個数> と書き、種類ごとの条件は次の行で書く:\n"
                 "離す: <種類か名前>   ← どの2つも隣り合わない ／ まとめる: <種類か名前>   ← 全部が続けて並ぶ\n"
                 "端に置かない: <種類か名前>   ← 左端にも右端にも置かない ／ 両端: <種類>   ← 左端と右端がその種類\n"
                 "例: 6人を1列に並べる。赤井さんと石田さんは隣り合わない。宇野さんは先頭ではない。並べ方は何通り →\n"
                 "並べる: 赤井 石田 宇野 他3\n条件: (赤井-石田)*(赤井-石田) != 1\n条件: 宇野 != 1\n問う: 数\n"
                 "例: 男子4人と女子3人を1列に並べる。女子どうしは隣り合わない。並べ方は何通り →\n"
                 "並べる: 男子×4 女子×3\n離す: 女子\n問う: 数")


def narabe(text):
    """並べる物の位置を全部の順列で試す。問う: 数 → 条件を満たす並べ方の数／問う: X → ただ1つの解での X の位置。
    種類×個数 は 区別する個数ぶんの物に広げ、離す・まとめる・端に置かない・両端 で種類ごとの条件を付ける。"""
    m = re.search(r"^\s*並べる\s*[:：]\s*(.+)$", text or "", re.M)
    if not m:
        raise ValueError("並べるが無い")
    names, shurui = [], {}
    for x in m.group(1).replace("、", " ").replace(",", " ").split():
        h = re.match(r"^(?:他|ほか|その他)(\d+)$", x)
        g = re.match(r"^([^\W\d]\w{0,9}?)\s*[×*＊]\s*(\d+)$", x)
        if h:
            names += ["_他%d_%d" % (len(names), i) for i in range(int(h.group(1)))]   # 名前の無い残り（条件には出ない）
        elif g:
            shurui[g.group(1)] = list(range(len(names), len(names) + int(g.group(2))))
            names += ["_%s_%d" % (g.group(1), i) for i in range(int(g.group(2)))]
        else:
            names.append(x)
    if not (2 <= len(names) <= 10) or len(set(names)) != len(names) or not all(re.match(r"^[^\W\d]\w{0,14}$", x) for x in names):
        raise ValueError("名前がおかしい")
    jouken = []
    for g in re.findall(r"^\s*条件\s*[:：]\s*(.+)$", text, re.M):
        c, src = _anzen(g.strip())
        for nm in c.co_names:
            if nm not in names:
                raise ValueError("知らない名前: " + nm)
        jouken.append(src)
    n = len(names)
    def mure(s):   # 「女子」「青木 井上」→ 位置の添字の並び
        idx = []
        for w in s.replace("、", " ").split():
            if w in shurui: idx += shurui[w]
            elif w in names: idx.append(names.index(w))
            else: raise ValueError("知らない名前: " + w)
        if not idx: raise ValueError("空の行")
        return idx
    SHU = {"離す": lambda p, ix: all(abs(u - v) != 1 for u, v in itertools.combinations([p[i] for i in ix], 2)),
           "まとめる": lambda p, ix: max(p[i] for i in ix) - min(p[i] for i in ix) == len(ix) - 1,
           "端に置かない": lambda p, ix: all(p[i] not in (1, n) for i in ix),
           "両端": lambda p, ix: {1, n} <= {p[i] for i in ix}}
    gyou = [(SHU[k], mure(v)) for k, v in re.findall(r"^\s*(離す|まとめる|端に置かない|両端)\s*[:：]\s*(.+)$", text, re.M)]
    q = re.search(r"^\s*問う\s*[:：]\s*(\S+)", text, re.M)
    tou = q.group(1) if q else "数"
    f = eval("lambda %s: %s" % (",".join(names), " and ".join("(%s)" % j for j in jouken) or "True"), {"__builtins__": {}})
    kai = [p for p in itertools.permutations(range(1, n + 1)) if f(*p) and all(h(p, ix) for h, ix in gyou)]
    if tou in ("数", "かず"):
        return len(kai)
    if tou not in names:
        raise ValueError("問うがおかしい")
    ichi = {p[names.index(tou)] for p in kai}
    if len(ichi) != 1:
        raise ValueError("答えが1つに決まらない: %d通り" % len(ichi))
    return ichi.pop()


SYSTEM_ERABI = ("あなたは選び方の問題を書き出す係です。数えません。出力は次の行だけ（説明なし）:\n"
                "候補: <名前が出てくる物を空白区切り。名前の無い残りは まとめて 他<個数>。同じ種類が何個もあれば <種類>×<個数>>\n"
                "選ぶ: <選ぶ個数>\n"
                "条件: <式>   ← 1行に1つ。各名前は 選べば 1・選ばなければ 0。種類の名前は その種類から選んだ個数\n"
                "式に使えるのは 名前・整数・+ - * // %・== != < <= > >=・and or not・かっこ だけ。\n"
                "必ず選ぶ: チーズ == 1 ／ 同時に選ばない: 健 + 美咲 <= 1 ／ 少なくとも1つ: ミント + バジル >= 1 ／ どちらか一方だけ: ミント + バジル == 1\n"
                "例: 8種類の具から3種類を選ぶ。チーズは必ず選び、ハムとサラミは同時に選ばない →\n"
                "候補: チーズ ハム サラミ 他5\n選ぶ: 3\n条件: チーズ == 1\n条件: ハム + サラミ <= 1\n"
                "例: 男子6人と女子4人から4人を選ぶ。女子を少なくとも1人入れる →\n"
                "候補: 男子×6 女子×4\n選ぶ: 4\n条件: 女子 >= 1")


def erabi(text):
    """候補から k 個を選ぶ組み合わせを全部試し、条件を満たす数を返す。種類×個数 の種類名は 選んだ個数。"""
    m = re.search(r"^\s*候補\s*[:：]\s*(.+)$", text or "", re.M)
    k = re.search(r"^\s*選ぶ\s*[:：]\s*(\d+)", text or "", re.M)
    if not m or not k:
        raise ValueError("候補か選ぶが無い")
    names, shurui, hoka = [], {}, 0
    for x in m.group(1).replace("、", " ").replace(",", " ").split():
        h = re.match(r"^(?:他|ほか|その他)(\d+)$", x)
        g = re.match(r"^([^\W\d]\w{0,9}?)\s*[×*＊]\s*(\d+)$", x)
        if h:
            hoka += int(h.group(1))
        elif g and g.group(1) not in names and g.group(1) not in shurui:
            shurui[g.group(1)] = int(g.group(2))
        elif re.match(r"^[^\W\d]\w{0,9}$", x) and x not in names and x not in shurui:
            names.append(x)
        else:
            raise ValueError("名前がおかしい: " + x)
    n, k = len(names) + sum(shurui.values()) + hoka, int(k.group(1))
    if not (1 <= k <= n <= 30):
        raise ValueError("数がおかしい")
    from math import comb
    if comb(n, k) > GENKAI:
        raise ValueError("大きすぎる")
    jouken = []
    for g in re.findall(r"^\s*条件\s*[:：]\s*(.+)$", text, re.M):
        c, src = _anzen(g.strip())
        for nm in c.co_names:
            if nm not in names and nm not in shurui:
                raise ValueError("知らない名前: " + nm)
        jouken.append(src)
    hen = names + list(shurui)
    f = eval("lambda %s: %s" % (",".join(hen) or "_", " and ".join("(%s)" % j for j in jouken) or "True"), {"__builtins__": {}})
    # 添字: 名前 0..len(names)-1、続けて種類ごとの区間、残りは 他
    kukan, i0 = [], len(names)
    for v in shurui.values():
        kukan.append(range(i0, i0 + v)); i0 += v
    kosu = 0
    for sel in itertools.combinations(range(n), k):
        s_ = set(sel)
        args = [1 if i in s_ else 0 for i in range(len(names))] + [len(s_.intersection(r)) for r in kukan]
        if f(*(args or [0])):
            kosu += 1
    return kosu


SYSTEM_HAYASA = ("あなたは速さの問題を書き出す係です。計算はしません。出力は次の行だけ（説明なし）:\n"
                 "間: <出発したときの二人の間の道のり>\n向き: 向かい合う か 追いかける\n"
                 "一: <分> <速さ>, <分> <速さ>, 以後 <速さ>   ← 一人目の速さを 始めから順に。途中で変わらなければ 以後 <速さ> だけ\n"
                 "二: 同じ書き方で二人目。追いかけるときは 一=追う方、二=前にいる方。遅れて出発するなら 最初に <分> 0\n"
                 "問う: 分 か 一の道のり か 二の道のり   ← 出会う（追いつく）までの時間か、それまでに進んだ道のり\n"
                 "道のりと速さの単位はそろえる（m と 毎分m など）。\n"
                 "例: 2000m 離れた二人が向かい合って出発。Aは最初の4分を毎分90m、その後は毎分130m。Bは毎分110m。何分後に出会うか →\n"
                 "間: 2000\n向き: 向かい合う\n一: 4 90, 以後 130\n二: 以後 110\n問う: 分")


def hayasa(text):
    """区切りごとの速さで二人を動かし、間が 0 になる時刻（分）か そこまでの道のりを分数で正確に出す。"""
    from fractions import Fraction as F
    def kazu(s):
        return F(s.replace(",", ""))
    m = re.search(r"^\s*間\s*[:：]\s*([\d.]+)", text or "", re.M)
    muki = re.search(r"^\s*向き\s*[:：]\s*(\S+)", text or "", re.M)
    if not m or not muki:
        raise ValueError("間か向きが無い")
    aida, oikake = kazu(m.group(1)), "追" in muki.group(1)
    def kukan(k):
        g = re.search(r"^\s*%s\s*[:：]\s*(.+)$" % k, text, re.M)
        if not g:
            raise ValueError(k + "が無い")
        out = []
        for p in re.split(r"[,、，]", g.group(1)):
            p = p.strip()
            a = re.match(r"^以後\s*([\d.]+)", p)
            b = re.match(r"^([\d.]+)\s*分?\s+(?:毎分)?([\d.]+)", p)
            if a: out.append((None, kazu(a.group(1)))); break
            elif b: out.append((kazu(b.group(1)), kazu(b.group(2))))
            elif p: raise ValueError("区切りが読めない: " + p[:20])
        if not out or out[-1][0] is not None:
            raise ValueError(k + "に 以後 が無い")
        return out
    ichi, ni = kukan("一"), kukan("二")
    def hayasa_at(ks, t):   # 時刻 t から次の区切りまでの速さと、その区切りの時刻
        s = F(0)
        for d, v in ks:
            if d is None or t < s + d:
                return v, (None if d is None else s + d)
            s += d
    t, michi1, michi2 = F(0), F(0), F(0)
    for _ in range(1000):
        v1, e1 = hayasa_at(ichi, t); v2, e2 = hayasa_at(ni, t)
        chijimu = v1 - v2 if oikake else v1 + v2
        tsugi = min([e for e in (e1, e2) if e is not None], default=None)
        if chijimu > 0 and (tsugi is None or aida / chijimu <= tsugi - t):
            dt = aida / chijimu
            t, michi1, michi2 = t + dt, michi1 + v1 * dt, michi2 + v2 * dt
            break
        if tsugi is None:
            raise ValueError("出会わない")
        dt = tsugi - t
        aida -= chijimu * dt; michi1 += v1 * dt; michi2 += v2 * dt; t = tsugi
    else:
        raise ValueError("区切りが多すぎる")
    q = re.search(r"^\s*問う\s*[:：]\s*(\S+)", text, re.M)
    v = {"一の道のり": michi1, "二の道のり": michi2}.get(q.group(1) if q else "分", t)
    return int(v) if v.denominator == 1 else float(round(v, 4))


# ── 道具えらび（物差し monosashi/hakaru.py と 本番 kernel/kikai.py が 同じこれを呼ぶ）──────────
# 型を見て 道具を 1つだけ選ぶ。合わない型に道具を使うと崩れる（9/23 自作テストB: 全部を式にすると 103→64）。
# 採用は 測って決める: 環境変数 KERNEL_KAZOERU / KERNEL_JIKAN / KERNEL_NARABE（本番の既定は kernel/kikai.py 側で決める）。
def erabu(toi, tsukau=("kazoeru", "jikan", "narabe", "erabi")):
    """問いに合う道具の名前を返す。合う物が無ければ None。"""
    # 「並び順は考えず」「組合せ」は 選び方（9/24 自作テストD: 並べ方に回って外した）
    if "erabi" in tsukau and re.search(r"選", toi) and re.search(r"何通り", toi) and (
            not re.search(r"並べ|並び|一列|順に並", toi) or re.search(r"組み?合わ?せ|(並び順|順序|順番)[はをも]?(考え|区別し|関係|決め)", toi)):
        return "erabi"          # 「n 個から k 個を選ぶ」（順番は関係ない）
    if "narabe" in tsukau and re.search(r"並|隣|列|席|順位|順番", toi) and re.search(r"何通り|何位|何番目", toi):
        return "narabe"
    # 時刻は「9時20分」。「2時間15分」（長さ）は時刻ではない（9/23 自作テストB の単位問題で取り違えた）
    if "jikan" in tsukau and len(re.findall(r"\d+時(?!間)(?:\d+分)?", toi)) >= 2 and re.search(r"何分|何時間", toi):
        return "jikan"
    # 速さ: 出会う・追いつく までの時間か道のり（9/24 自作テストE で 7/16。前半に相手も進むのを忘れる）。既定では使わない（測ってから）
    if "hayasa" in tsukau and re.search(r"出会|追いつ|追い付|すれ違", toi) and re.search(r"何分後|何秒後|何時間後|何m|何メートル|何km|何キロ", toi):
        return "hayasa"
    if "kazoeru" in tsukau and "何通り" in toi and not re.search(r"並べ|並び|隣|列に|一列|席|選", toi):
        return "kazoeru"
    return None


DOUGU = {"kazoeru": (lambda: SYSTEM, lambda t: kazoeru(t), 300),
         "jikan": (lambda: SYSTEM_JIKAN, lambda t: jikan(t), 200),
         "narabe": (lambda: SYSTEM_NARABE, lambda t: narabe(t), 300),
         "erabi": (lambda: SYSTEM_ERABI, lambda t: erabi(t), 300),
         "hayasa": (lambda: SYSTEM_HAYASA, lambda t: hayasa(t), 300)}


def toku(toi, kiku, tsukau=("kazoeru", "jikan", "narabe", "erabi")):
    """道具で解く。kiku(toi, system, kotae_cap) → ローカル LLM の出力文字列。
    戻りは (答え, 道具名, 書き出し) か、道具が合わない／読めないとき (None, 理由, 書き出し)。"""
    na = erabu(toi, tsukau)
    if not na:
        return None, None, ""
    sys_, f, cap = DOUGU[na]
    kaki = kiku(toi, sys_(), cap) or ""
    try:
        v = f(kaki)
        if na in ("kazoeru", "narabe", "erabi", "hayasa") and v == 0:
            raise ValueError("0通り")     # 「何通り」で 0 は まず書き違い
        return v, na, kaki
    except Exception as e:
        return None, "%s が読めず: %s" % (na, str(e)[:40]), kaki


if __name__ == "__main__":
    print(narabe("並べる: A B C D E\n条件: (A-B)*(A-B) != 1\n問う: 数"))   # 72
    print(narabe("並べる: A B C\n条件: A < B\n条件: C == 1\n問う: B"))     # 3
    print(jikan("始め: 9/8 21:35\n終わり: 9/10 0:20\n引く: 15\n足す: 0\n単位: 分"))   # 1590
    print(keisan("使う: …\n使わない: 23個\n式: 121 + 9*7 - 116"))            # 68
    print(keisan("式: (8700 - 8700*25/100) * 108/100 = 7047"))              # 7047
    for bad in ("式: __import__('os')", "式: 2**99999", "式: 1 # x"):
        try: keisan(bad); print("通ってしまった!", bad)
        except (ValueError, SyntaxError) as e: print("断った:", str(e)[:30])
    t = "変数: x 0 27\n変数: y 0 16\n変数: z 0 10\n条件: 3*x+5*y+8*z == 83"
    print(kazoeru(t))   # 35（7段 の 3円・5円・8円で 83円）
    for bad in ("変数: x 0 3\n条件: x==1 #", "変数: x 0 3\n条件: __import__('os')", "変数: x 0 3\n条件: x.real == 1", "変数: x 0 9999\n変数: y 0 9999\n条件: x==y"):
        try:
            kazoeru(bad); print("通ってしまった!", bad)
        except (ValueError, SyntaxError) as e:
            print("断った:", str(e)[:40])
