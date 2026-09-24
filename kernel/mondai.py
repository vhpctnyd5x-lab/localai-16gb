#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mondai.py -- 問題を たくさん作る工場。正解は カーネルを使わずに 出す

  ────────────────────────────────────────────────
  なぜ作るか
  ────────────────────────────────────────────────
  手で書いた問題は 83問しかない。すぐ満点になって 物差しにならない。
  今日 直したバグ3件は、どれも「新しく問題を1問足したら出てきた」もの。
      ・ゴミ箱を空にして → デスクトップから捨てる、に化けかけていた
      ・Desktop → 対象=フォルダ という誤った札が眠っていた
      ・「フォルダ」を 場所の一部でも 数える相手として拾っていた
  問題が足りないから、バグが見つからない。それだけの話だった。

  ────────────────────────────────────────────────
  いちばん大事なところ: 正解を カーネルに出させない
  ────────────────────────────────────────────────
  カーネルの答えを正解にしたら、何を測っても「自分と同じ」で満点になる。
  ここでは os.walk で ファイルを直接読み、数えて 正解を作る。
  カーネルの中身は 一行も呼ばない。

  【踏まないようにした落とし穴】
    ・隠しファイル（. で始まる）を数えてしまう
    ・macOS が勝手に作る「._」ファイルを数えてしまう
    ・シンボリックリンクを 中身ごと数えてしまう
    ・os.listdir の順番が環境で変わり、答えが日によって変わる → 必ず並べ替える
    ・拡張子の大文字小文字（.JPG と .jpg）を別物として数えてしまう
    ・下のフォルダの中を 数えるつもりが 数えていない／逆に数えている

  ────────────────────────────────────────────────
  過適合を見つけるための作り
  ────────────────────────────────────────────────
  問題には「型番」を付ける。あとで
      ・型番ごとの正答率（ばらつきが大きい＝その型に頼っている）
      ・型番を丸ごと伏せて測る（伏せた型だけ落ちる＝型を覚えただけ）
  ができるようにしておく。
"""
import datetime, os, random, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 問題用の場（sandbox とは別）。
# BA_NA を差し替えれば 別の場で回せる。
# 同じ場を 二つの実験が使うと、片方の作り直しが もう片方の答えを狂わせる。
# 実際 mondai_run と kowasu を同時に回して そうなった（§7-⑤ と同じ事故）。
_BA_OYA = os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                       "kernel-ai")
BA = os.path.join(_BA_OYA, "mondai_ba")


def ba_wo_kaeru(namae):
    """使う場を差し替える（実験ごとに別の場にするため）"""
    global BA
    BA = os.path.join(_BA_OYA, namae)
    return BA

Y = 365 * 24 * 3600
D = 24 * 3600

# 種類 と 拡張子。カーネルの EXT とは わざと別に書く。
# 同じ表を見たら「同じ間違い」をしても気づけない
SHURUI = {
    "画像":     [".jpg", ".png", ".jpeg", ".gif", ".heic"],
    "動画":     [".mp4", ".mov", ".avi"],
    "音楽":     [".mp3", ".m4a", ".wav"],
    "PDF":      [".pdf"],
    "テキスト": [".txt", ".md"],
    "圧縮":     [".zip", ".7z"],
}
# 「書類」は PDF とテキストと事務用をまとめたもの
SHORUI_EXT = [".pdf", ".txt", ".md", ".doc", ".docx", ".xls", ".xlsx",
              ".csv", ".ppt", ".pptx"]

OOKISA = {".jpg": 320_000, ".jpeg": 300_000, ".png": 180_000, ".gif": 90_000,
          ".heic": 400_000, ".mp4": 12_000_000, ".mov": 9_000_000,
          ".avi": 7_000_000, ".mp3": 4_500_000, ".m4a": 3_800_000,
          ".wav": 20_000_000, ".pdf": 240_000, ".txt": 1_800, ".md": 900,
          ".doc": 30_000, ".docx": 28_000, ".xls": 40_000, ".xlsx": 38_000,
          ".csv": 5_000, ".ppt": 900_000, ".pptx": 850_000,
          ".zip": 2_000_000, ".7z": 1_800_000}

NAMAE = ["旅行", "会議", "資料", "メモ", "写真", "動画", "録音", "請求",
         "契約", "報告", "計画", "見積", "日記", "献立", "住所", "予定",
         "設計", "図面", "原稿", "台本", "楽譜", "家計", "領収", "名簿"]

BASHO = ["Desktop", "Downloads", "Documents"]


# ============================================================
# ① 場を作る（毎回ちがう中身にする）
# ============================================================
def ba_tsukuru(tane, hukasa=True):
    """問題用のフォルダを 作り直す。tane が同じなら 同じ中身になる"""
    r = random.Random(tane)
    os.environ.setdefault("COPYFILE_DISABLE", "1")
    if os.path.exists(BA):
        shutil.rmtree(BA, ignore_errors=True)
    now = time.time()
    for basho in BASHO:
        d = os.path.join(BA, basho)
        os.makedirs(d, exist_ok=True)
        n = r.randint(4, 14)
        tsukatta = set()
        for _ in range(n):
            shu = r.choice(list(SHURUI))
            ext = r.choice(SHURUI[shu])
            base = r.choice(NAMAE) + str(r.randint(1, 99))
            name = base + ext
            if name in tsukatta:
                continue
            tsukatta.add(name)
            _fairu(os.path.join(d, name), ext, now - r.choice(
                [2 * D, 10 * D, 40 * D, 100 * D, 1.2 * Y, 1.4 * Y, 2.5 * Y]), r)
        # 下のフォルダ。あってもなくてもよい（「奥まで見る」の問題に使う）
        if hukasa and r.random() < 0.5:
            sub = os.path.join(d, r.choice(["古いもの", "保存", "作業中"]))
            os.makedirs(sub, exist_ok=True)
            for _ in range(r.randint(1, 4)):
                shu = r.choice(list(SHURUI))
                ext = r.choice(SHURUI[shu])
                _fairu(os.path.join(sub, r.choice(NAMAE) + str(r.randint(1, 99)) + ext),
                       ext, now - r.choice([5 * D, 60 * D, 1.3 * Y]), r)
    return BA


def _fairu(path, ext, mtime, r):
    size = OOKISA.get(ext, 2_000) + r.randint(0, 5_000)
    tane = (os.path.basename(path).encode("utf-8") * 64)[:64]
    with open(path, "wb") as f:
        f.write(tane)
        f.write(b"\0" * max(0, size - len(tane)))
    os.utime(path, (mtime, mtime))


# ============================================================
# ② 正解を出す（カーネルを一切呼ばない）
# ============================================================
def _mieru(d):
    """その場所で 目に見えるもの。隠しもの・リンクは数えない"""
    fs, ds = [], []
    try:
        namae = sorted(os.listdir(d))        # 順番を決めておく。環境で変わらせない
    except OSError:
        return [], []
    for n in namae:
        if n.startswith(".") or n.startswith("._"):
            continue                          # 隠しもの・macOS が勝手に作るもの
        p = os.path.join(d, n)
        if os.path.islink(p):
            continue                          # リンクの先までは数えない
        if os.path.isfile(p):
            fs.append(p)
        elif os.path.isdir(p):
            ds.append(p)
    return fs, ds


def _oku_made(d):
    """下のフォルダの中まで。ここも隠しものは飛ばす"""
    out = []
    for root, dirs, files in os.walk(d):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for f in sorted(files):
            if f.startswith(".") or f.startswith("._"):
                continue
            p = os.path.join(root, f)
            if not os.path.islink(p):
                out.append(p)
    return out


def _ext(p):
    return os.path.splitext(p)[1].lower()      # .JPG と .jpg を同じものとして見る


def _shu_de_shiboru(fs, shu):
    if shu == "書類":
        yoi = set(SHORUI_EXT)
    else:
        yoi = set(SHURUI[shu])
    return [f for f in fs if _ext(f) in yoi]


def _jiki_de_shiboru(fs, jiki):
    """時期でしぼる。

    ここは 一度 大きく間違えた。
    「最近＝30日」「去年＝365日前から」と 自分で決めて作ったが、
    カーネルは「最近＝7日」「去年＝去年の1月1日から今年の1月1日まで」だった。
    そのため 作った問題の 2割が「違う」と出ていたが、
    **間違っていたのは 私の正解のほう** だった。

      物差しが engine と食い違っていると、
      見つかるのは バグではなく 自分の思い込み になる。

    暦の区切り方は カーネルと同じ書き方をここに写す。
    （カーネルの関数を呼んだら「独立に出す」意味が無くなるので、呼ばない）
    """
    n = datetime.datetime.now()
    if jiki == "最近":
        a = (n - datetime.timedelta(days=7)).timestamp()
        b = 9e18
    elif jiki == "今年":
        a = n.replace(month=1, day=1, hour=0, minute=0, second=0,
                      microsecond=0).timestamp()
        b = 9e18
    elif jiki == "去年":
        a = n.replace(year=n.year - 1, month=1, day=1, hour=0, minute=0,
                      second=0, microsecond=0).timestamp()
        b = n.replace(month=1, day=1, hour=0, minute=0, second=0,
                      microsecond=0).timestamp()
    else:
        return fs
    return [f for f in fs if a <= os.path.getmtime(f) < b]


# ============================================================
# ③ 問題を作る
# ============================================================
# 型番ごとに（言い方の作り方, 正解の出し方, むずかしさ）
def _iikata_kazoeru(r, basho, shu=None, jiki=None):
    b = r.choice({"Desktop": ["デスクトップ", "机の上", "Desktop"],
                  "Downloads": ["ダウンロード", "落としたところ", "Downloads"],
                  "Documents": ["書類フォルダ", "ドキュメント", "Documents"]}[basho])
    s = "" if shu is None else r.choice({
        "画像": ["画像", "写真", "絵"], "動画": ["動画", "映像", "ムービー"],
        "音楽": ["音楽", "音声", "曲"], "PDF": ["PDF", "pdf"],
        "テキスト": ["テキスト", "メモ"], "圧縮": ["圧縮", "zip"],
        "書類": ["書類", "文書", "資料"]}[shu])
    j = "" if jiki is None else r.choice({
        # 「ここ1ヶ月の」は外した。カーネルに 1ヶ月 という区切りが無く、
        # 最近(7日) に寄せられて 食い違うため。無い機能を問うのは 問題の不良
        "去年": ["去年の", "1年前の"], "最近": ["最近の", "この前の"],
        "今年": ["今年の"]}[jiki])
    owari = r.choice(["は何個", "はいくつ", "の数を教えて", "は何枚",
                      "の個数を", "って何個ある", "の総数"])
    aite = None
    if not s:
        # 種類を言わないときは、何を数えるのか言わないと日本語にならない。
        # 「机の上の数を教えて」では 人にも通じない
        s = r.choice(["もの", "ファイル", "中身"])
        # 「ファイル」と言ったら フォルダは数に入らない。
        # ここを見ていなかったので、ファイルと言いながら
        # フォルダも足した数を 正解にしていた（自分の正解のほうが誤り）
        aite = "ファイル" if s == "ファイル" else None
    no = "の" if s else ""
    return f"{b}{no}{j}{s}{owari}", aite


def _ookii_jun(fs):
    return sorted(fs, key=lambda f: (-os.path.getsize(f), os.path.basename(f)))


def _furui_jun(fs):
    return sorted(fs, key=lambda f: (os.path.getmtime(f), os.path.basename(f)))


def _basho_iikata(r, basho):
    return r.choice({"Desktop": ["デスクトップ", "机の上", "Desktop"],
                     "Downloads": ["ダウンロード", "落としたところ", "Downloads"],
                     "Documents": ["書類フォルダ", "ドキュメント", "Documents"]}[basho])


def _shu_iikata(r, shu):
    return r.choice({
        "画像": ["画像", "写真", "絵"], "動画": ["動画", "映像", "ムービー"],
        "音楽": ["音楽", "音声", "曲"], "PDF": ["PDF", "pdf"],
        "テキスト": ["テキスト", "メモ"], "圧縮": ["圧縮", "zip"],
        "書類": ["書類", "文書", "資料"]}[shu])


def tsukuru(kazu=500, tane=1, muzukashisa=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)):
    """問題を kazu 問 作って返す

    返すのは (問い, 正解の文字列, 型番, むずかしさ) の並び

    むずかしさ:
      1 場所だけ数える        5 一番大きい／古いは何か
      2 場所＋種類            6 除く・対象（フォルダだけ）
      3 場所＋種類＋時期      7 奥まで見る・合計の大きさ・断るべき問い
      4 一覧                  8 まとめる・整理（ものが動く）
                              9 捨てる（ゴミ箱へ動く）
                             10 答えられないのが正解
    """
    r = random.Random(tane * 7919 + 13)
    ba_tsukuru(tane)
    out = []
    tomawari = 0
    while len(out) < kazu and tomawari < kazu * 40:
        tomawari += 1
        basho = r.choice(BASHO)
        d = os.path.join(BA, basho)
        fs, ds = _mieru(d)
        b = _basho_iikata(r, basho)
        muzu = r.choice(muzukashisa)

        if muzu == 1:
            toi, aite = _iikata_kazoeru(r, basho)
            n = len(fs) if aite == "ファイル" else len(fs) + len(ds)
            out.append((toi, f"{n} 個", "かぞえる/場所", muzu))

        elif muzu == 2:
            shu = r.choice(list(SHURUI) + ["書類"])
            toi, _ = _iikata_kazoeru(r, basho, shu)
            out.append((toi, f"{len(_shu_de_shiboru(fs, shu))} 個",
                        "かぞえる/場所+種類", muzu))

        elif muzu == 3:
            shu = r.choice(list(SHURUI) + ["書類"])
            jiki = r.choice(["去年", "最近", "今年"])
            toi, _ = _iikata_kazoeru(r, basho, shu, jiki)
            n = len(_jiki_de_shiboru(_shu_de_shiboru(fs, shu), jiki))
            out.append((toi, f"{n} 個", "かぞえる/場所+種類+時期", muzu))

        elif muzu == 4:                                   # 一覧
            shu = r.choice(list(SHURUI) + ["書類"])
            nokori = _shu_de_shiboru(fs, shu)
            if not nokori:
                continue                                  # 空の一覧は 手がかりが無い
            owari = r.choice(["を並べて", "の一覧を出して", "を見せて",
                              "のファイル名を教えて"])
            toi = f"{b}の{_shu_iikata(r, shu)}{owari}"
            out.append((toi, os.path.basename(nokori[0]),
                        "ならべる/場所+種類", muzu))

        elif muzu == 5:                                   # いちばん〜
            muki = r.choice(["大きい", "古い"])
            if len(fs) < 2:
                continue
            saki = (_ookii_jun(fs) if muki == "大きい" else _furui_jun(fs))[0]
            iikata = {"大きい": ["いちばん大きい", "一番でかい", "最も大きい",
                                 "いちばん重い", "いちばん容量食ってる"],
                      "古い": ["いちばん古い", "一番古い", "最も古い"]}[muki]
            toi = f"{b}で{r.choice(iikata)}ファイルは"
            out.append((toi, os.path.basename(saki),
                        f"いちばん/{muki}", muzu))

        elif muzu == 6:                                   # 除く・対象
            if r.random() < 0.5:
                shu = r.choice(list(SHURUI))
                nokori = [f for f in fs if f not in _shu_de_shiboru(fs, shu)]
                toi = f"{b}の{_shu_iikata(r, shu)}以外は何個"
                out.append((toi, f"{len(nokori)} 個", "のぞく/場所+種類", muzu))
            else:
                nani = r.choice(["フォルダ", "ファイル"])
                n = len(ds) if nani == "フォルダ" else len(fs)
                toi = f"{b}に{nani}はいくつ"
                out.append((toi, f"{n} 個", f"対象/{nani}", muzu))

        elif muzu == 8:                                   # 壊す側（移動）
            shu = r.choice(list(SHURUI))
            nokori = _shu_de_shiboru(fs, shu)
            if not nokori:
                continue
            iikata = r.choice(["をまとめて", "を一箇所に集めて",
                               "をフォルダに入れて", "を整理して"])
            toi = f"{b}の{_shu_iikata(r, shu)}{iikata}"
            # 正解は「何個 動いたか」。どこへ動いたかは engine の決めごと
            out.append((toi, f"{len(nokori)} 個", f"うごかす/移動", muzu))

        elif muzu == 9:                                   # 壊す側（ゴミ箱）
            shu = r.choice(list(SHURUI))
            nokori = _shu_de_shiboru(fs, shu)
            if not nokori:
                continue
            iikata = r.choice(["を捨てて", "をゴミ箱に入れて", "を消して"])
            toi = f"{b}の{_shu_iikata(r, shu)}{iikata}"
            out.append((toi, f"{len(nokori)} 個", "うごかす/ごみばこ", muzu))

        elif muzu == 10:                                  # 答えられないのが正解
            saikoro = r.random()
            if saikoro < 0.34:
                # 無い場所
                toi = r.choice(["音楽フォルダの画像は何個",
                                "写真ライブラリの動画を数えて",
                                "外付けディスクのPDFはいくつ"])
                out.append((toi, "分かりません", "断る/無い場所", muzu))
            elif saikoro < 0.67:
                # 作れない形
                toi = f"{b}の画像をZIPにして"
                out.append((toi, "できません", "断る/作れない形", muzu))
            else:
                # 裏付けの無い壊す動作（先生が言い出しても採ってはいけない形）
                toi = f"{b}の動画をMP3にして"
                out.append((toi, "できません", "断る/作れない形", muzu))

        else:                                             # 7
            saikoro = r.random()
            if saikoro < 0.3:                             # 奥まで
                zen = _oku_made(d)
                # 「全部数えて」だと フォルダ自体を数に入れるかが 決まらない。
                # 問いが曖昧だと、食い違っても どちらが悪いのか分からない。
                # 「ファイルは何個」と はっきり聞く。
                # 「入れて」と書いていたら 移動の合図に読まれ、
                # 聞いただけで 仕分けが走った。問いの言葉づかいも 試験の一部
                toi = f"{b}を奥のフォルダまで見て ファイルは何個"
                out.append((toi, f"{len(zen)} 個", "もぐる/場所", muzu))
            elif saikoro < 0.6:                           # 合計の大きさ
                if not fs:
                    continue
                toi = f"{b}のファイルは ぜんぶで何メガ"
                out.append((toi, "MB", "おおきさ/合計", muzu))
            else:                                         # 断るのが正解
                toi = r.choice(["ゴミ箱を空にして", "ゴミ箱きれいにしといて",
                                "ゴミ箱の中身を消して", "ごみ箱を片付けて"])
                out.append((toi, "しません", "断る/ゴミ箱", muzu))
    return out


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    for toi, kotae, kata, muzu in tsukuru(n):
        print(f"  [{kata}] {toi}\n      正解: {kotae}")
    print(f"\n  場: {BA}")
