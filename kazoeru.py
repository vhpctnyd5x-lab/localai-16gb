"""閉じた数え上げ電卓（2026-09-23）。ローカル LLM は式を書くだけ、数えるのはこちら。

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


if __name__ == "__main__":
    t = "変数: x 0 27\n変数: y 0 16\n変数: z 0 10\n条件: 3*x+5*y+8*z == 83"
    print(kazoeru(t))   # 35（7段 の 3円・5円・8円で 83円）
    for bad in ("変数: x 0 3\n条件: x==1 #", "変数: x 0 3\n条件: __import__('os')", "変数: x 0 3\n条件: x.real == 1", "変数: x 0 9999\n変数: y 0 9999\n条件: x==y"):
        try:
            kazoeru(bad); print("通ってしまった!", bad)
        except (ValueError, SyntaxError) as e:
            print("断った:", str(e)[:40])
