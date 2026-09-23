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
                "引く: <分>   ← 途中で止めた・休んだ分。無ければ 0。何回かあれば足した数\n"
                "足す: <分>   ← 足す分。無ければ 0\n単位: 分 か 時間\n"
                "日付が無い問題は 始めと終わりを同じ日付 1/1 にし、終わりが翌日なら 1/2 にする。\n"
                "例: 9月8日21時35分に始め、9月10日0時20分に終えた。途中15分止めた。何分か →\n"
                "始め: 9/8 21:35\n終わり: 9/10 0:20\n引く: 15\n足す: 0\n単位: 分")


def jikan(text, nen=2026):
    """時刻の書き出し → 分（または時間）。読めなければ ValueError。うるう年の 2/29 は扱わない。"""
    import datetime as dt
    def toru(k):
        m = re.search(r"^\s*%s\s*[:：]\s*(\d{1,2})\s*/\s*(\d{1,2})\s+(\d{1,2})\s*[:：]\s*(\d{1,2})" % k, text or "", re.M)
        if not m:
            raise ValueError(k + "が無い")
        mo, d, h, mi = map(int, m.groups())
        return dt.datetime(nen, mo, d) + dt.timedelta(hours=h, minutes=mi)   # 24:00 も通す
    def kazu(k):
        m = re.search(r"^\s*%s\s*[:：]\s*(\d+)" % k, text or "", re.M)
        return int(m.group(1)) if m else 0
    a, b = toru("始め"), toru("終わり")
    if b < a:
        raise ValueError("終わりが始めより前")
    fun = int((b - a).total_seconds() // 60) - kazu("引く") + kazu("足す")
    if re.search(r"^\s*単位\s*[:：]\s*時間", text or "", re.M):
        return fun // 60 if fun % 60 == 0 else round(fun / 60, 4)
    return fun


SYSTEM_NARABE = ("あなたは並べ方・順位の問題を書き出す係です。数えたり解いたりしません。出力は次の行だけ（説明なし）:\n"
                 "並べる: <並べる物の名前を空白区切り。問題文の呼び名をそのまま（さん・くん等は付けない）。全員書く>\n"
                 "条件: <式>   ← 1行に1つ。各名前は その物の位置（1番目=1）を表す整数\n"
                 "問う: 数   ← 並べ方の数を答えるとき\n問う: <名前>   ← その物の位置（何番目）を答えるとき\n"
                 "式に使えるのは 名前・整数・+ - * // %・== != < <= > >=・and or not・かっこ だけ。\n"
                 "隣り合う: (青木-井上)*(青木-井上) == 1 ／ 隣り合わない: (青木-井上)*(青木-井上) != 1 ／ 青木が井上より前: 青木 < 井上 ／ 両端: 青木 == 1 or 青木 == 5\n"
                 "例: 赤井・石田・宇野・遠藤の4人を1列に並べる。赤井さんと石田さんは隣り合わない。宇野さんは先頭ではない。並べ方は何通り →\n"
                 "並べる: 赤井 石田 宇野 遠藤\n条件: (赤井-石田)*(赤井-石田) != 1\n条件: 宇野 != 1\n問う: 数")


def narabe(text):
    """並べる物の位置を全部の順列で試す。問う: 数 → 条件を満たす並べ方の数／問う: X → ただ1つの解での X の位置。"""
    m = re.search(r"^\s*並べる\s*[:：]\s*(.+)$", text or "", re.M)
    if not m:
        raise ValueError("並べるが無い")
    names = m.group(1).replace("、", " ").replace(",", " ").split()
    if not (2 <= len(names) <= 9) or len(set(names)) != len(names) or not all(re.match(r"^[^\W\d]\w{0,7}$", x) for x in names):
        raise ValueError("名前がおかしい")
    jouken = []
    for g in re.findall(r"^\s*条件\s*[:：]\s*(.+)$", text, re.M):
        c, src = _anzen(g.strip())
        for nm in c.co_names:
            if nm not in names:
                raise ValueError("知らない名前: " + nm)
        jouken.append(src)
    q = re.search(r"^\s*問う\s*[:：]\s*(\S+)", text, re.M)
    tou = q.group(1) if q else "数"
    f = eval("lambda %s: %s" % (",".join(names), " and ".join("(%s)" % j for j in jouken) or "True"), {"__builtins__": {}})
    kai = [p for p in itertools.permutations(range(1, len(names) + 1)) if f(*p)]
    if tou in ("数", "かず"):
        return len(kai)
    if tou not in names:
        raise ValueError("問うがおかしい")
    ichi = {p[names.index(tou)] for p in kai}
    if len(ichi) != 1:
        raise ValueError("答えが1つに決まらない: %d通り" % len(ichi))
    return ichi.pop()


# ── 道具えらび（物差し monosashi/hakaru.py と 本番 kernel/kikai.py が 同じこれを呼ぶ）──────────
# 型を見て 道具を 1つだけ選ぶ。合わない型に道具を使うと崩れる（9/23 自作テストB: 全部を式にすると 103→64）。
# 採用は 測って決める: 環境変数 KERNEL_KAZOERU / KERNEL_JIKAN / KERNEL_NARABE（本番の既定は kernel/kikai.py 側で決める）。
def erabu(toi, tsukau=("kazoeru", "jikan", "narabe")):
    """問いに合う道具の名前を返す。合う物が無ければ None。"""
    if "narabe" in tsukau and re.search(r"並|隣|列|席|順位|順番", toi) and re.search(r"何通り|何位|何番目", toi):
        return "narabe"
    if "jikan" in tsukau and len(re.findall(r"\d+時(?:\d+分)?", toi)) >= 2 and re.search(r"何分|何時間", toi):
        return "jikan"
    if "kazoeru" in tsukau and "何通り" in toi and not re.search(r"並べ|並び|隣|列に|一列|席", toi):
        return "kazoeru"
    return None


DOUGU = {"kazoeru": (lambda: SYSTEM, lambda t: kazoeru(t), 300),
         "jikan": (lambda: SYSTEM_JIKAN, lambda t: jikan(t), 200),
         "narabe": (lambda: SYSTEM_NARABE, lambda t: narabe(t), 300)}


def toku(toi, kiku, tsukau=("kazoeru", "jikan", "narabe")):
    """道具で解く。kiku(toi, system, kotae_cap) → ローカル LLM の出力文字列。
    戻りは (答え, 道具名, 書き出し) か、道具が合わない／読めないとき (None, 理由, 書き出し)。"""
    na = erabu(toi, tsukau)
    if not na:
        return None, None, ""
    sys_, f, cap = DOUGU[na]
    kaki = kiku(toi, sys_(), cap) or ""
    try:
        v = f(kaki)
        if na in ("kazoeru", "narabe") and v == 0:
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
