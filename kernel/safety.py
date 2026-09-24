#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
safety.py -- kernel.py のエンジンを「本物のホームフォルダ」で動かすための安全層

このファイルは kernel.py / parts_more.py を一切書き換えない。
読むだけで、外側から包む「関所」として働く。

守りは4枚重ね:
  (1) resolve     : 概念スロットの場所名 → 実パス（許可リスト外なら通さない）
  (2) check_path  : 1本のパスを触ってよいか（realpath で symlink を必ず解決）
  (3) check_plan  : 実行直前の最終検査（件数・容量・範囲外・危険な対象）
  (4) confirm     : 人間に日本語で見せて y/n。非対話なら必ず拒否
  (5) journal     : 実行した変更を記録し、undo_last で手で戻せるようにする

【絶対条件】
  このファイルには「ファイルを完全に消すコード」を1行も書かない。
  os.remove / os.unlink / shutil.rmtree は使わない。捨てるのは常に ~/.Trash への移動。
"""

import os
import sys
import json
import shutil
import datetime

HERE    = os.path.dirname(os.path.abspath(__file__))
HOME    = os.path.realpath(os.path.expanduser("~"))
TRASH   = os.path.join(HOME, ".Trash")

# 練習用フォルダの場所。kernel.py と同じ計算をする。
#
# ここは長いあいだ HERE/"sandbox"（外付けSSDの中）を指したままだった。
# kernel.py はとっくに本体ディスクへ引っ越していた（exFAT でフォルダが
# 壊れたため。その残骸が sandbox_壊れている）。
# 食い違っていたので、関所の許可範囲に「実際に使っている練習用フォルダ」が
# 入っておらず、本番モードで練習用のパスを通すと
# 「システム/設定の領域です: ~/Library」で止まる状態だった。
SANDBOX = os.path.join(HOME, "Library", "Application Support",
                       "kernel-ai", "sandbox")
_SANDBOX_OLD = os.path.join(HERE, "sandbox")   # 昔の場所。まだ在れば許す

# 変更を伴う部品の名前（kernel.py / parts_more.py の PARTS と対応）
CHANGING_PARTS = {"うつす", "なまえかえ", "ごみばこ", "つくる"}
# そのうち「本当に中身が動く」もの（つくる はフォルダ作成だけなので別枠）
MOVING_PARTS   = {"うつす", "なまえかえ", "ごみばこ"}

# 概念スロットの場所名 → ホーム配下の実フォルダ名
PLACE_MAP = {
    "Desktop":   "Desktop",
    "デスクトップ": "Desktop",
    "Downloads": "Downloads",
    "ダウンロード": "Downloads",
    "Documents": "Documents",
    "書類":       "Documents",
    "ドキュメント": "Documents",
}

# 何があっても触らせない場所（許可リストより強い）
FORBIDDEN = [
    "/System", "/Library", "/Applications", "/usr", "/bin", "/sbin",
    "/etc", "/private/etc", "/var", "/private/var", "/opt", "/cores",
    "/Network", "/dev", "/Volumes/Macintosh HD/System",
    os.path.join(HOME, "Library"),
    os.path.join(HOME, ".ssh"),
    os.path.join(HOME, ".config"),
    os.path.join(HOME, ".Trash"),   # ゴミ箱は undo 専用。通常の操作対象にはしない
]

# 既定のしきい値
DEFAULT_LIMITS = {
    "最大件数":   50,
    "最大バイト": 1024 * 1024 * 1024,   # 1GB
}


class SafetyError(Exception):
    """関所で止めたときに投げる例外"""
    pass


# ------------------------------------------------------------
# 小道具
# ------------------------------------------------------------
def _real(p):
    """symlink を辿った先の、本当の絶対パス"""
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(p))))


def _under(child, parent):
    """child が parent と同じか、その配下か（文字列の前方一致だけに頼らない）"""
    child, parent = _real(child), _real(parent)
    if child == parent:
        return True
    return child.startswith(parent.rstrip(os.sep) + os.sep)


def _human(n):
    """バイト数を人間が読める形に"""
    x = float(n)
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if x < 1024 or u == "TB":
            return f"{int(x)} B" if u == "B" else f"{x:.1f} {u}"
        x /= 1024


def _size_of(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def _uniq_dest(dirpath, name):
    """同名がすでにあるときに、連番を足した空きパスを返す（上書きを絶対にしない）"""
    base, ext = os.path.splitext(name)
    cand = os.path.join(dirpath, name)
    i = 1
    while os.path.exists(cand):
        cand = os.path.join(dirpath, f"{base} {i}{ext}")
        i += 1
    return cand


# ============================================================
# 関所ほんたい
# ============================================================
class Guard:
    def __init__(self, allow_roots=None, config="safety.json"):
        # 既定の許可範囲: 本物の Desktop / Downloads / Documents と、エンジン自身の sandbox
        # allow_roots を呼び出し側が明示したかを覚えておく。
        # 明示された根だけが、下の FORBIDDEN 判定を上書きできる（テスト用の一時フォルダなど）。
        self.explicit_roots = allow_roots is not None
        if allow_roots is None:
            allow_roots = [
                os.path.join(HOME, "Desktop"),
                os.path.join(HOME, "Downloads"),
                os.path.join(HOME, "Documents"),
                SANDBOX,
            ]
        # 実体のあるものだけを許可根として持つ（無い場所は最初から通さない）
        self.allow_roots = []
        for r in allow_roots:
            rr = _real(r)
            if rr not in self.allow_roots:
                self.allow_roots.append(rr)

        # しきい値の設定を読む（無ければ既定）
        self.limits = dict(DEFAULT_LIMITS)
        self.config_path = config if os.path.isabs(str(config)) else os.path.join(HERE, str(config))
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    for k, v in (json.load(f) or {}).items():
                        if k in self.limits and isinstance(v, int):
                            self.limits[k] = v
            except Exception:
                pass   # 設定が壊れていたら既定のまま（安全側）

        self.journal_path = os.path.join(HERE, "journal.jsonl")

    # --------------------------------------------------------
    # (1) 場所名 → 実パス
    # --------------------------------------------------------
    def resolve(self, place):
        """概念スロットの場所名を実パスに変える。許可リスト外なら例外"""
        place = str(place)

        cands = []
        if place in PLACE_MAP:
            cands.append(os.path.join(HOME, PLACE_MAP[place]))
        # sandbox 配下の同名フォルダ（テスト・従来動作のため）
        cands.append(os.path.join(SANDBOX, PLACE_MAP.get(place, place)))
        # 絶対パスを直接渡された場合も、検査を通れば認める
        if os.path.isabs(place):
            cands.insert(0, place)

        first_err = None
        for c in cands:
            try:
                self.check_path(c)
            except SafetyError as e:
                first_err = first_err or e
                continue
            if os.path.isdir(_real(c)):
                return _real(c)
        if first_err:
            raise SafetyError(f"場所「{place}」は許可された範囲にありません: {first_err}")
        raise SafetyError(f"場所「{place}」に当たるフォルダが見つかりません")

    # --------------------------------------------------------
    # (2) 1本のパスの検査
    # --------------------------------------------------------
    def check_path(self, p):
        """このパスを触ってよいか。ダメなら理由つきで SafetyError"""
        if p is None or str(p).strip() == "":
            raise SafetyError("パスが空です")

        raw  = str(p)
        real = _real(raw)   # ★ symlink はここで必ず解決する

        # / 直下そのもの
        if real == os.sep:
            raise SafetyError("ルート「/」そのものは触れません")

        # ホームディレクトリそのもの
        if real == HOME:
            raise SafetyError("ホームフォルダそのものは触れません")

        # 触ってはいけない場所。
        # 例外は1つだけ: 呼び出し側が allow_roots を明示していて、その根が
        # 禁止領域そのものではなく、より深いところにある場合（テスト用の一時フォルダなど）。
        # 既定の許可根では、この例外は決して発動しない。
        # 練習用フォルダだけは、禁止領域(~/Library)の中にあっても通す。
        # そこはカーネル自身が作って、カーネル自身が作り直す場所で、
        # 「システムの設定」ではない。
        if _under(real, SANDBOX) or _under(real, _SANDBOX_OLD):
            return real

        for bad in FORBIDDEN:
            if not _under(real, bad):
                continue
            allowed_by_explicit = False
            if self.explicit_roots:
                for root in self.allow_roots:
                    if _under(root, bad) and root != _real(bad) and _under(real, root):
                        allowed_by_explicit = True
                        break
            if not allowed_by_explicit:
                raise SafetyError(f"システム/設定の領域です: {bad}")

        # / 直下のもの（/Volumes 配下の sandbox は下の許可判定で救われる）
        if os.path.dirname(real) == os.sep:
            raise SafetyError("ルート直下の項目は触れません")

        # 許可された根の、どれかの中に入っているか
        inside = None
        for root in self.allow_roots:
            if _under(real, root):
                inside = root
                break
        if inside is None:
            # 「../」で外へ抜けた場合も、symlink で外を指した場合も、必ずここで落ちる
            hint = ""
            if real != _real(os.path.abspath(os.path.expanduser(raw))) or os.path.islink(os.path.abspath(os.path.expanduser(raw))):
                hint = "（シンボリックリンクの飛び先が範囲外）"
            raise SafetyError(f"許可された範囲の外です{hint}: {real}")

        # ホーム直下の項目のうち、許可根そのもの以外は拒否
        if os.path.dirname(real) == HOME and real not in self.allow_roots:
            raise SafetyError("ホームフォルダ直下の項目は触れません")

        return None

    def is_ok_path(self, p):
        """例外を投げずに真偽で返す版"""
        try:
            self.check_path(p)
            return True
        except SafetyError:
            return False

    # --------------------------------------------------------
    # (3) 実行直前の最終検査
    # --------------------------------------------------------
    def check_plan(self, plan, slots, preview):
        """
        plan    : 部品名のリスト
        slots   : 概念スロット
        preview : 下見(dry)モードで実行した結果の状態 dict
        戻り値  : {"ok":bool, "level":"安全"|"要確認"|"危険", "reasons":[...], "summary":str}
        """
        plan    = list(plan or [])
        slots   = dict(slots or {})
        preview = dict(preview or {})

        reasons = []
        level   = "安全"

        def bump(lv):
            nonlocal level
            order = {"安全": 0, "要確認": 1, "危険": 2}
            if order[lv] > order[level]:
                level = lv

        changing = [n for n in plan if n in CHANGING_PARTS]
        moving   = [n for n in plan if n in MOVING_PARTS]

        # --- 対象ファイルの一覧を作る -------------------------
        targets = []
        for f in (preview.get("files") or []):
            f = str(f)
            if os.path.exists(f):
                targets.append(f)
            else:
                # 下見の「うつす」は行き先(まだ無い)を返すので、元の場所に読み替える
                src = preview.get("src")
                alt = os.path.join(src, os.path.basename(f)) if src else None
                targets.append(alt if (alt and os.path.exists(alt)) else f)

        # --- 触るパスを全部検査 ------------------------------
        checked = list(targets)
        for key in ("src", "dest"):
            if preview.get(key):
                checked.append(str(preview[key]))

        outside = []
        for p in checked:
            try:
                self.check_path(p)
            except SafetyError as e:
                outside.append((p, str(e)))
        if outside:
            bump("危険")
            for p, why in outside[:5]:
                reasons.append(f"許可範囲外のパスが混ざっています: {p} … {why}")
            if len(outside) > 5:
                reasons.append(f"（ほか {len(outside)-5} 件も範囲外）")

        # 読むだけの手順なら、範囲さえ問題なければ通す
        if not changing:
            if outside:
                return {"ok": False, "level": "危険", "reasons": reasons,
                        "summary": "読むだけの手順ですが、許可範囲外のパスが含まれています。"}
            return {"ok": True, "level": "安全", "reasons": ["変更をともなう操作はありません"],
                    "summary": "読むだけの手順です。ファイルは1つも動きません。"}

        n     = len(targets)
        total = sum(_size_of(p) for p in targets)

        # --- 件数 --------------------------------------------
        if n > self.limits["最大件数"]:
            bump("危険" if n > self.limits["最大件数"] * 2 else "要確認")
            reasons.append(f"変更対象が {n} 件あります（しきい値 {self.limits['最大件数']} 件）")

        # --- 合計サイズ --------------------------------------
        if total > self.limits["最大バイト"]:
            bump("危険" if total > self.limits["最大バイト"] * 2 else "要確認")
            reasons.append(f"合計 {_human(total)} を動かします（しきい値 {_human(self.limits['最大バイト'])}）")

        # --- 隠しファイル / 拡張子なし ------------------------
        hidden = [p for p in targets if os.path.basename(p).startswith(".")]
        noext  = [p for p in targets
                  if not os.path.splitext(os.path.basename(p))[1]
                  and not os.path.basename(p).startswith(".")]
        if hidden:
            bump("危険")
            reasons.append(f"隠しファイルが {len(hidden)} 件含まれます"
                           f"（例: {os.path.basename(hidden[0])}）")
        if noext:
            bump("要確認")
            reasons.append(f"拡張子のないファイルが {len(noext)} 件含まれます"
                           f"（例: {os.path.basename(noext[0])}）")

        # --- ゴミ箱送りは常に一段重く ------------------------
        if "ごみばこ" in plan:
            bump("要確認")
            reasons.append("ゴミ箱へ移す操作です（完全削除はしませんが、元の場所からは消えます）")

        # --- 本物のホームを触るなら一段重く ------------------
        if any(_under(p, HOME) and not _under(p, SANDBOX) for p in targets):
            bump("要確認")
            reasons.append("本物のホームフォルダの中身が対象です")

        if not reasons:
            reasons.append("しきい値内で、対象もすべて許可範囲内です")

        ok = (level != "危険")
        what = "・".join(moving) if moving else "・".join(changing)
        summary = (f"【{level}】{what} を {n} 件（合計 {_human(total)}）に対して実行します。\n"
                   f"  元: {preview.get('src', '(不明)')}\n"
                   f"  先: {preview.get('dest') or ('~/.Trash' if 'ごみばこ' in plan else '(同じ場所)')}")
        return {"ok": ok, "level": level, "reasons": reasons, "summary": summary}

    # --------------------------------------------------------
    # (4) 人間に見せて y/n
    # --------------------------------------------------------
    def confirm(self, verdict):
        """人間の確認。非対話環境では必ず False（安全側に倒す）"""
        verdict = dict(verdict or {})
        print()
        print("=" * 58)
        print("  これから本物のファイルを変更します。よく読んでください。")
        print("=" * 58)
        print(verdict.get("summary", "（内容不明）"))
        print("-" * 58)
        for r in verdict.get("reasons", []):
            print(f"  ・{r}")
        print("-" * 58)

        if verdict.get("level") == "危険":
            print("  判定：危険。この手順は自動では実行しません。")
            return False

        if not sys.stdin.isatty():
            print("  ここは対話できない環境です → 安全のため実行しません。")
            return False

        try:
            ans = input("  実行してよいですか？ [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  入力が取れませんでした → 実行しません。")
            return False
        ok = ans in ("y", "yes")
        print("  → 実行します。" if ok else "  → やめておきます。")
        return ok

    # --------------------------------------------------------
    # (5) 記録
    # --------------------------------------------------------
    def journal(self, action, detail):
        """
        実行した変更を journal.jsonl に1行ずつ足す。
        「何を・どこから・どこへ」を残し、あとから手で戻せるようにする。
        """
        detail = dict(detail or {})
        items = []
        for it in (detail.get("items") or []):
            if isinstance(it, dict):
                items.append({"名前": it.get("名前") or os.path.basename(str(it.get("to") or it.get("from") or "")),
                              "from": str(it.get("from") or ""),
                              "to":   str(it.get("to") or "")})
            elif isinstance(it, (list, tuple)) and len(it) == 2:
                items.append({"名前": os.path.basename(str(it[1])),
                              "from": str(it[0]), "to": str(it[1])})

        rec = {
            "id":     datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"),
            "時刻":   datetime.datetime.now().isoformat(timespec="seconds"),
            "action": str(action),
            "plan":   list(detail.get("plan") or []),
            "slots":  dict(detail.get("slots") or {}),
            "src":    str(detail.get("src") or ""),
            "dest":   str(detail.get("dest") or ""),
            "件数":   len(items),
            "items":  items,
            "undone": False,
            "note":   str(detail.get("note") or ""),
        }
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _rotate_journal(self.journal_path)
        return None

    # --------------------------------------------------------
    # 便利: 下見結果から journal 用の items を作る
    # --------------------------------------------------------
    @staticmethod
    def items_from(before, after):
        """元パスの並び before と、変更後パスの並び after を突き合わせて items にする"""
        return [{"from": str(a), "to": str(b)} for a, b in zip(before, after)]


# ============================================================
# 取り消し
# ============================================================
def _read_journal(path):
    recs = []
    if not os.path.exists(path):
        return recs
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
    return recs


# 記録に残す行数の上限。
# 追記しっぱなしだったので、787行(1MB)まで伸びていた。
# 取り消しのたびに全行を読んで書き直すので、伸びるほど遅くなる。
# 古いものは別ファイルへ逃がす（消しはしない）。
JOURNAL_MAX = 3000
JOURNAL_KEEP = 1500


def _rotate_journal(path):
    """行数が上限を超えたら、古い分を .old へ移す。消しはしない"""
    try:
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= JOURNAL_MAX:
            return
        old, keep = lines[:-JOURNAL_KEEP], lines[-JOURNAL_KEEP:]
        with open(path + ".old", "a", encoding="utf-8") as f:
            f.writelines(old)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(keep)
        os.replace(tmp, path)
    except OSError:
        pass          # 片付けに失敗しても、本業(記録)は止めない


def _mark_undone(path, rec_id):
    """該当行に undone フラグを立てる（行の削除はしない、書き直すだけ）"""
    recs = _read_journal(path)
    for r in recs:
        if r.get("id") == rec_id:
            r["undone"] = True
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)   # 置き換え。消しているわけではない


def undo_last(journal_path="journal.jsonl", note=None):
    """
    直近の変更操作を打ち消す。
    移動・改名なら元の場所へ戻し、ゴミ箱送りなら ~/.Trash から元の場所へ戻す。
    完全削除は一切しない（戻すのも「移動」だけ）。

    note に "本物" / "練習用" を渡すと、その種類だけを対象にする。
    ここを分けていなかったせいで、次の事故が起きうる状態だった。

      本物のフォルダで移動する
        → bench.py を1回流す（練習用の記録が数十行積まれる）
        → /undo が練習用のほうを戻し、本物の取り消しに永久に届かない

    notebook_real.json / simnote_real.json はわざわざ分けてあるのに、
    この記録だけ本物と練習用が同じ列に並んでいた。
    """
    path = journal_path if os.path.isabs(str(journal_path)) \
        else os.path.join(HERE, str(journal_path))

    recs = _read_journal(path)
    target = None
    for r in reversed(recs):
        if r.get("undone"):
            continue
        if not r.get("items"):
            continue
        if note is not None and r.get("note") != note:
            continue
        target = r
        break
    if target is None:
        return "取り消せる操作は記録にありません。"

    back, fail, skip = [], [], []
    keshita = []                          # 作ったフォルダを消したもの
    nokoshita = []                        # 中身があったので残したフォルダ
    for it in reversed(target["items"]):
        src_now  = it.get("to") or ""     # いま在る場所
        src_back = it.get("from") or ""   # 戻したい場所

        # 「作った」記録（from が空）は、戻すのではなく **消す**。
        #   前は フォルダを作っても記録に残らず、/undo が
        #   「取り消せる操作は記録にありません」と言うだけだった。
        #   本物のデスクトップに作ったものを 手で消すしかなかった。
        # ★ 消すのは **空のフォルダだけ**。
        #   os.rmdir は空でないと失敗するので、中身を巻き込む心配は無い。
        #   中身があれば、そのまま残して「残した」と言う。
        if src_now and not src_back:
            if not os.path.isdir(src_now):
                skip.append(os.path.basename(src_now) or "?")
                continue
            try:
                os.rmdir(src_now)
                keshita.append(src_now)
            except OSError:
                # 中に何か入っている＝消してはいけない
                nokoshita.append(src_now)
            continue

        if not src_now or not src_back:
            skip.append(it.get("名前", "?"))
            continue
        if not os.path.exists(src_now):
            skip.append(os.path.basename(src_now))
            continue
        if os.path.abspath(src_now) == os.path.abspath(src_back):
            skip.append(os.path.basename(src_now))
            continue
        try:
            d = os.path.dirname(src_back)
            if not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            dest = src_back if not os.path.exists(src_back) \
                else _uniq_dest(d, os.path.basename(src_back))
            shutil.move(src_now, dest)     # 戻すのも「移動」だけ
            back.append((src_now, dest))
        except Exception as e:
            fail.append(f"{os.path.basename(src_now)}（{e}）")

    if back or keshita:
        _mark_undone(path, target.get("id"))

    # 空になった行き先フォルダは片付ける。os.rmdir は空の時しか成功しないので、
    # 中身が残っていれば何も起きない（消してしまう心配は無い）
    emptied = []
    for a, _b in back:
        d = os.path.dirname(a)
        try:
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                emptied.append(os.path.basename(d))
        except OSError:
            pass

    nanika = bool(back or keshita)
    lines = [(f"取り消しました: {target.get('action')}  （{target.get('時刻')}）")
             if nanika else
             (f"取り消せませんでした: {target.get('action')}  （{target.get('時刻')}）")]
    for a, b in back:
        lines.append(f"  戻した: {a}\n      → {b}")
    if keshita:
        lines.append("  作ったフォルダを消しました: "
                     + ", ".join(os.path.basename(x) for x in keshita))
    if nokoshita:
        lines.append("  中身が入っていたので、そのまま残しました: "
                     + ", ".join(os.path.basename(x) for x in nokoshita))
        lines.append("    （空にしてからもう一度 /undo すると消せます。"
                     "中身ごと消すことは しません）")
    if emptied:
        lines.append(f"  空になったフォルダも片付けました: {', '.join(sorted(set(emptied)))}")
    if skip:
        lines.append(f"  そのまま（見つからない/すでに元の場所）: {len(skip)} 件")
    if fail:
        lines.append("  戻せなかったもの:")
        for x in fail:
            lines.append(f"    - {x}")
    if not back and not fail and not keshita and not nokoshita:
        lines.append("  戻す対象がありませんでした。")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--undo":
        print(undo_last())
    else:
        g = Guard()
        print("許可された範囲:")
        for r in g.allow_roots:
            print("  -", r)
        print("しきい値:", g.limits)
