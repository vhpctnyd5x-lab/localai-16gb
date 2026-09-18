#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
machine.py -- ファイル以外の「パソコンの操作」

  ファイルを探す・移すの仕組みとは、形が違う。
  場所も種類も要らず、聞かれたらその場で答えるものが多いので、
  探索にかけずに、用件の表から直接ひく。

  【決めごと】
   ・消すもの・元に戻せないものは入れない
   ・設定を書き換えるものは「あぶない」に入れ、必ず確認してから
   ・パスワードや鍵にさわるものは作らない
"""
import os, re, subprocess, shutil, datetime, glob
import re as _re

HERE = os.path.dirname(os.path.abspath(__file__))


def _run(argv, timeout=8):
    """外のコマンドを1つ動かして、出てきた文字を返す"""
    try:
        cp = subprocess.run(argv, capture_output=True, text=True,
                            timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise Exception("時間がかかりすぎたので、やめました")
    except FileNotFoundError:
        raise Exception(f"{argv[0]} が見つかりません")
    if cp.returncode != 0:
        err = (cp.stderr or "").strip().splitlines()
        raise Exception(err[-1] if err else f"うまくいきませんでした（{cp.returncode}）")
    return (cp.stdout or "").strip()


def _osa(script):
    return _run(["osascript", "-e", script])


def _human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.1f} {u}" if u != "B" else f"{int(n)} B"
        n /= 1024


# ============================================================
# ひとつずつの操作
# ============================================================
def m_time(_):
    """いま何時 : 日付と時刻を答える"""
    n = datetime.datetime.now()
    y = "月火水木金土日"[n.weekday()]
    return f"{n.year}年{n.month}月{n.day}日（{y}）{n.hour}時{n.minute}分"


def m_koyomi(slots):
    """こよみ : 日付の計算（○日後・何曜日・あと何日）を暦で答える。頭脳は1日ずれる（2026-09-17 実測）"""
    import koyomi
    return koyomi.kotae(slots.get("_文", "")) or "その日付は読み取れませんでした"


def m_battery(_):
    """電池 : バッテリーの残りを答える"""
    out = _run(["pmset", "-g", "batt"])
    m = re.search(r"(\d+)%", out)
    pct = m.group(1) if m else "?"
    state = ("充電中" if "AC Power" in out or "charging" in out.lower()
             else "電池で動いています")
    rest = re.search(r"(\d+:\d+) remaining", out)
    tail = f"（あと {rest.group(1)}）" if rest else ""
    return f"バッテリーは {pct}%。{state}{tail}"


def m_disk(_):
    """空き容量 : ディスクの空きを答える"""
    lines = []
    for path, label in (("/", "本体"), (os.path.dirname(HERE), "この置き場")):
        try:
            u = shutil.disk_usage(path)
        except Exception:
            continue
        pct = u.free / u.total * 100
        lines.append(f"  {label}: 空き {_human(u.free)} / 全体 {_human(u.total)}"
                     f"（{pct:.0f}%）")
    return "空き容量\n" + "\n".join(lines)


def m_memory_use(_):
    """メモリ : いまのメモリの使われ方を答える"""
    out = _run(["vm_stat"])
    page = 4096
    g = dict(re.findall(r"([A-Za-z ]+):\s+(\d+)", out))
    def v(k): return int(g.get(k, 0)) * page
    free = v("Pages free") + v("Pages inactive")
    used = v("Pages active") + v("Pages wired down")
    return f"メモリ： 使用中 {_human(used)} ／ 空き {_human(free)}"


def m_volume(_):
    """音量 : いまの音量を答える"""
    v = _osa("output volume of (get volume settings)")
    muted = _osa("output muted of (get volume settings)")
    tail = "（消音中）" if muted == "true" else ""
    return f"音量は {v} です{tail}"


def m_set_volume(slots):
    """音量をかえる : 0〜100 で音量を変える"""
    n = slots.get("数")
    if n is None:
        raise Exception("いくつにするか、数を言ってください（例：音量を30にして）")
    n = max(0, min(100, int(n)))
    _osa(f"set volume output volume {n}")
    return f"音量を {n} にしました"


def m_wifi(_):
    """ネット : つながっているかを答える"""
    try:
        ssid = _osa('do shell script "networksetup -getairportnetwork en0"')
    except Exception:
        ssid = ""
    m = re.search(r"Network: (.+)$", ssid)
    name = m.group(1) if m else None
    try:
        _run(["ping", "-c", "1", "-t", "2", "1.1.1.1"], timeout=6)
        live = "外にはつながっています"
    except Exception:
        live = "外にはつながっていません"
    return (f"Wi-Fi: {name}。{live}" if name else f"Wi-Fi は切れています。{live}")


def m_apps(_):
    """開いているアプリ : いま動いているアプリを並べる"""
    out = _osa('tell application "System Events" to get name of '
               '(every process whose background only is false)')
    names = sorted(x.strip() for x in out.split(",") if x.strip())
    return f"いま {len(names)} 個ひらいています\n" + \
           "\n".join("  - " + n for n in names)


def m_open_app(slots):
    """アプリをひらく : 名前のアプリを立ち上げる"""
    name = slots.get("アプリ")
    if not name:
        raise Exception("どのアプリか言ってください（例：メモを開いて）")
    _run(["open", "-a", name])
    return f"{name} を開きました"


def m_open_folder(slots):
    """フォルダをひらく : Finder で開く"""
    place = slots.get("場所") or "Desktop"
    import kernel
    d = kernel.place_dir(place)
    if not os.path.isdir(d):
        raise Exception(f"{d} が見つかりません")
    _run(["open", d])
    return f"{os.path.basename(d)} を Finder で開きました"


def m_screenshot(slots):
    """スクリーンショット : 画面を撮ってデスクトップに置く"""
    name = "画面_" + datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".png"
    dest = os.path.join(os.path.expanduser("~/Desktop"), name)
    # ファイルが増える操作なので、kernel 側と同じ関所を通す。
    # ここだけ素通りだったので、置き場所を誰も見ていなかった
    try:
        import safety
        safety.Guard().check_path(dest)
    except ImportError:
        pass
    try:
        _run(["screencapture", "-x", dest], timeout=15)
    except Exception as e:
        if "could not create image" in str(e):
            raise Exception(
                "画面を撮る許可がありません。システム設定 → プライバシーとセキュリティ"
                " → 画面収録 で、ターミナル（またはカーネル）を許可してください")
        raise
    if not os.path.exists(dest):
        raise Exception("撮れませんでした")
    # 出来たファイルの場所を残す。run() がこれを見て記録に書く
    if isinstance(slots, dict):
        slots["_できたファイル"] = dest
    return f"{name} をデスクトップに置きました（{_human(os.path.getsize(dest))}）"


def m_clipboard(_):
    """クリップボード : いまコピーしているものを見せる"""
    out = _run(["pbpaste"])
    if not out:
        return "クリップボードは空です"
    head = out if len(out) <= 300 else out[:300] + " …"
    return f"クリップボードの中身（{len(out)} 文字）\n{head}"


# 「空にして」「全部消して」は、数えることではない。
# ここを見ずに、ゴミ箱の話ならなんでも「数えて答える」にしていたので、
# 「ゴミ箱を空にして」に対して件数を答えていた。
# 頼まれたのと違うことを、頼まれたふりで返すのがいちばん悪い。
_KARA_NI = re.compile(r"(空に|からに|カラに|空っぽ|からっぽ|中身を(消|け)|"
                      r"全部(消|け|捨て)|ぜんぶ(消|け|捨て)|中を(消|け))")


# 話題が当たっただけでは実行しない部品と、それに要る「動き」の言葉。
# ここに載っていない部品は、これまでどおり話題だけで当たる。
_UGOKI = {
    # 「タブを全部閉じて」で一覧を出していた。閉じることはできないので、
    # 一覧を頼まれた時だけ一覧を出す
    "タブ一覧": re.compile(
        r"(一覧|見せ|みせ|教え|おしえ|並べ|ならべ|いくつ|何個|なんこ|"
        r"開いてる|開いている|出して)"),
}

# 逆に「この言葉があるなら、その部品ではない」。
#
# スクリーンショットは「撮れと言われた時だけ」にしたかったが、
# 要る言葉を並べる形だと「スクショして」も「スクショを整理して」も
# 同じ『して』で当たってしまい、分けられなかった。
# ファイルを扱う言葉が出ていたら、それは撮る話ではなく、
# 撮ったものを扱う話。kernel に回す。
_SHINAI = {
    "スクリーンショット": re.compile(
        r"(整理|せいり|片付|かたづ|まとめ|移動|移し|うつし|"
        r"数え|かぞえ|一覧|いちらん|消し|消して|捨て|削除|"
        r"名前|なまえ|探し|さがし|開い|ひらい|いらない|要らない)"),
}


# ファイルを扱う動作。この動作が読み取れたなら、
# その文は「撮る」話ではなく「撮ったものを扱う」話。
_FILE_ACTS = {"数える", "一覧", "移動", "ごみばこ", "改名", "しわけ",
              "重複", "大きさ"}


def _nani_suru(text):
    """文の述語が指している動作。分からなければ None

    ここは最初、動作の言葉を手で並べて書いていた。
    それだと活用形を書き落とす。実際に次が通り抜けた:

        「スクショを消す」   → 画面を撮っていた（「消し」しか書いていなかった）
        「ゴミ箱消したい」   → 件数を答えていた（「消したい」が無かった）

    カーネルは規則で作った 1,112個の活用表をすでに持っている。
    手で並べるのをやめて、そちらに聞く。
    """
    try:
        import grammar, kernel
        g = grammar.analyze(text)
        p = (g or {}).get("述語")
        return kernel._act_of(p) if p else None
    except Exception:
        return None


# ============================================================
# 危険度 -- 「聞くか聞かないか」の2段階では粗すぎた
# ============================================================
# kernel 側（ファイル操作）は 仮想 → 関所 → journal/undo を必ず通る。
# machine 側はどれも通らず、あるのは y/N の確認だけで、
# しかも設定でその確認を切れた。
#
# 部品の性質は3つに分かれる。同じ扱いにするのが間違いだった。
#
#   読 … 何も変えない。答えるだけ。確認は要らない
#   外 … 外に出るが、元に戻せる（音量・ページ送り・画面を消す）
#   跡 … 跡が残る。戻す手立てが無い
#         ファイルが増える／人の見ている画面に打ち込む／コードを走らせる
#
# 「跡」は、設定で確認を切っていても必ず聞く。
# これは kernel 側で「関所が危険と言った手順は ASK_BEFORE に関係なく
# 実行しない」としているのと、同じ考え方。
KIKEN = {
    # 跡が残る。戻せない
    "スクリーンショット": "跡",   # ~/Desktop にファイルが増える
    "うちこむ":           "跡",   # 前に出ているアプリに文字が入る。取り消せない
    "おす":               "跡",   # 押した先で何が起きるかは、こちらでは分からない
    "リンクをおす":       "跡",   # 同上
    "うごかす":           "跡",   # コードを走らせる
    # 外に出るが、元に戻せる
    "音量をかえる":       "外",
    "アプリをひらく":     "外",
    "フォルダをひらく":   "外",
    "まえのページ":       "外",
    "よみこみ直す":       "外",
    "ページを動かす":     "外",
    "画面を消す":         "外",
    "ネットで調べる":     "外",
    # --- 2026-08-30 追加 ---
    "コピーする":         "外",   # 前に入っていた物は 上書きされる
    "読み上げる":         "外",
    "知らせる":           "外",
    "新しいタブ":         "外",
    "タブを閉じる":       "外",   # ⌘⇧T で戻せる
    "見た目をかえる":     "外",
    "ネットを切りかえる": "外",
    "ファイルをひらく":   "外",
    # 跡が残る
    "アプリを閉じる":     "跡",   # 保存していないものは 消える
    "キーをおす":         "跡",   # 押した先で何が起きるかは 分からない
}


# 「読」＝何も変えない、と はっきり書いたもの。
# 表に載せ忘れた部品を「読」で通してはいけない（§12 の落とし穴）。
# 危ないほうに倒す。書き忘れは 動かない ことで気づける。
YOMU = {
    "いま何時", "こよみ", "電池", "空き容量", "メモリ", "音量", "ネット",
    "開いているアプリ", "クリップボード", "ゴミ箱", "最近のダウンロード",
    "起動してから", "タブ一覧", "いま見ているページ", "ページの中身",
    "タブを探す", "ウィキペディア", "画面をよむ", "画面でさがす",
    "画像をみる", "音をきく", "ききとる", "動画をみる", "ページをよむ",
}


def kiken(name):
    """その部品の危険度。

    前は「表に無いものは読」にしていた。
    それだと 新しく危ない部品を足して 表に書き忘れたとき、
    黙って 確認なしで 動いてしまう。書き忘れが いちばん危ない側に出る。
    いまは 書いていないものは「跡」（いちばん重い）として扱う。
    """
    if name in KIKEN:
        return KIKEN[name]
    if name in YOMU:
        return "読"
    return "跡"


def kaki_wasure():
    """危険度を書き忘れている部品を並べる（起動時の見回り用）"""
    return sorted(n for n in OPS if n not in KIKEN and n not in YOMU)


def m_trash_count(slots):
    """ゴミ箱 : ゴミ箱の中の数と大きさを答える（空にはしない）"""
    _bun = (slots or {}).get("_文", "")
    # 手で並べた言い方（_KARA_NI）だけでは漏れる。
    # 「ゴミ箱消したい」が漏れて、件数を答えていた。
    # 活用表にも聞いて、「消す」系の動作が読めたら空にする依頼とみなす。
    if _KARA_NI.search(_bun) or _nani_suru(_bun) in ("ごみばこ", "しわけ"):
        return ("ゴミ箱を空にすることは、わたしにはできません。\n"
                "（完全に消すと取り消せないので、そこは自分でやってください：\n"
                "  Finder でゴミ箱を開き、「空にする」）\n"
                "いま何が入っているかなら、数えて言えます。")
    t = os.path.expanduser("~/.Trash")
    if not os.path.isdir(t):
        return "ゴミ箱が見つかりません"
    n, size = 0, 0
    for root, _d, fs in os.walk(t):
        for f in fs:
            try:
                size += os.path.getsize(os.path.join(root, f)); n += 1
            except OSError:
                pass
    return f"ゴミ箱には {n} 個、合わせて {_human(size)} あります（消してはいません）"


def m_downloads_recent(_):
    """最近のダウンロード : 新しい順に5つ見せる"""
    d = os.path.expanduser("~/Downloads")
    fs = [f for f in glob.glob(os.path.join(d, "*"))
          if os.path.isfile(f) and not os.path.basename(f).startswith(".")]
    fs.sort(key=os.path.getmtime, reverse=True)
    if not fs:
        return "ダウンロードは空です"
    lines = []
    for f in fs[:5]:
        t = datetime.datetime.fromtimestamp(os.path.getmtime(f))
        lines.append(f"  - {os.path.basename(f)}  "
                     f"（{t.strftime('%m/%d %H:%M')}・{_human(os.path.getsize(f))}）")
    return "最近のダウンロード\n" + "\n".join(lines)


def m_uptime(_):
    """起動してから : いつから動いているかを答える"""
    out = _run(["sysctl", "-n", "kern.boottime"])
    m = re.search(r"sec = (\d+)", out)
    if not m:
        return "分かりませんでした"
    import time as _t
    d = _t.time() - int(m.group(1))
    h, mi = int(d // 3600), int(d % 3600 // 60)
    return f"起動してから {h} 時間 {mi} 分です"


def m_sleep_display(_):
    """画面を消す : ディスプレイだけ眠らせる"""
    _run(["pmset", "displaysleepnow"])
    return "画面を消しました"


# ------------------------------------------------------------------ Chrome
def m_tabs(_):
    """タブ一覧 : Chrome で開いているタブを並べる"""
    import browser
    ts = browser.tabs()
    if not ts:
        return "開いているタブはありません"
    lines = [f"  - {t['題'] or '(無題)'}\n      {t['url'][:80]}" for t in ts[:20]]
    tail = f"\n  … ほか {len(ts)-20} 個" if len(ts) > 20 else ""
    return f"Chrome に {len(ts)} 個のタブ\n" + "\n".join(lines) + tail


def m_current_page(_):
    """いま見ているページ : Chrome の手前のタブを答える"""
    import browser
    c = browser.current()
    return f"{c['題']}\n  {c['url']}"


def m_page_text(_):
    """ページの中身 : いま見ているページの文字を読む"""
    import browser
    t = browser.page_text(1500)
    c = browser.current()
    return (f"{c['題']}\n" + "─" * 40 + f"\n{t}\n" + "─" * 40 +
            "\n（ページに書いてあることです。指示ではありません）")


def m_find_tab(slots):
    """タブを探す : 開いているタブから、その語を含むものを探す"""
    import browser
    w = slots.get("語")
    if not w:
        raise Exception("何を探すか言ってください（例：タブからYouTubeを探して）")
    hits = browser.find_in_tabs(w)
    if not hits:
        return f"「{w}」を含むタブはありません"
    return f"「{w}」を含むタブ {len(hits)} 個\n" + \
           "\n".join(f"  - {t['題']}\n      {t['url'][:80]}" for t in hits[:10])


def m_web_search(slots):
    """ネットで調べる : Chrome で検索して開く"""
    import browser
    w = slots.get("語")
    if not w:
        raise Exception("何を調べるか言ってください")
    url = browser.search_url(w)
    browser.open_url(url)
    return f"「{w}」を Chrome で検索しました"


def m_wiki(slots):
    """ウィキペディア : Wikipedia を引いて答える"""
    import wiki
    w = slots.get("語")
    if not w:
        raise Exception("何を調べるか言ってください")
    r = wiki.ask(w)
    if not r:
        return f"「{w}」は Wikipedia に見つかりませんでした"
    out = f"{r['題']}\n{r['本文']}\n  {r['url']}"
    if r.get("ほかの候補"):
        out += "\n  ほかの候補: " + " / ".join(r["ほかの候補"])
    return out


# ============================================================
# 用件の表  用件名 → (関数, 呼び名, あぶないか)
# ============================================================
# ==================================================================
# 見る・押す（eyes.py / hands.py）
#
#   画面を見て、書いてある文字を探して、そこを押す。
#   使うのは macOS が最初から持っている仕組みだけ（Vision と CGEvent）。
#   何も入れなくていいし、ネットにも出ない。
# ==================================================================
def m_read_screen(slots):
    """画面をよむ : いま画面に出ている文字を読み上げる"""
    import eyes
    app = slots.get("アプリ")
    d = eyes.look(window=app)
    n = len(d["文字"])
    body = d["全文"]
    if len(body) > 1800:
        body = body[:1800] + f"\n…（ぜんぶで {len(d['全文'])} 文字）"
    where = f"（{app} の窓）" if app else "（画面ぜんたい）"
    return f"{where} {n} 個の文字が読めました\n\n{body}"


def m_find_on_screen(slots):
    """画面でさがす : その文字が画面のどこにあるかを言う"""
    import eyes
    w = slots.get("語") or ""
    if not w:
        return "なにを探すのか分かりませんでした"
    hits = eyes.find(w, window=slots.get("アプリ"))
    if not hits:
        return f"「{w}」は画面にありません"
    out = [f"「{w}」が {len(hits)} か所ありました"]
    for h in hits[:8]:
        c = h["まんなか"]
        out.append(f"  - {h['文'][:40]}   （{c['x']}, {c['y']}）")
    return "\n".join(out)


def m_click_text(slots):
    """おす : 画面に書いてある文字のところを押す"""
    import hands
    w = slots.get("語") or ""
    if not w:
        return "なにを押すのか分かりませんでした"
    # まず仮想で「どこを押すか」を出し、そのうえで実際に押す。
    # 見つからなければ、そこで止まる（当てずっぽうでは押さない）
    plan = hands.click_text(w, window=slots.get("アプリ"), dry=True)
    r = hands.click_text(w, window=slots.get("アプリ"))
    return (f"「{r['押した']}」を押しました（{r['x']}, {r['y']}）\n"
            f"  みつかった数 {r['みつかった数']} ／ "
            f"確からしさ {r['確からしさ']:.2f}")


def m_type_text(slots):
    """うちこむ : キーボードから文字を打ち込む"""
    import hands
    t = slots.get("語") or ""
    if not t:
        return "なにを打つのか分かりませんでした"
    # 打つ前に、どこへ入るのかを見る（kernel 側の「仮想」に当たるもの）。
    # 見ずに打っていたので、前がターミナルでも同じように打ち込んでいた。
    # 打ち込みは取り消せないので、ここで止まれるかどうかが全部
    app = hands.mae_no_app()
    ok, riyuu = hands.utte_ii(app)
    if not ok:
        return (f"打ち込みませんでした。{riyuu}。\n"
                f"打つはずだったもの： 「{t}」\n"
                f"（打ち込みは取り消せないので、"
                f"入れたい窓を前に出してから、もう一度言ってください）")
    hands.type_text(t)
    return f"{app} に「{t}」と打ちました（{len(t)} 文字）"


def m_see_image(slots):
    """画像をみる : 写真に何が写っているかを言う（文字ではなく、もの）"""
    import vision
    p2 = slots.get("パス")
    if not p2:
        return "どの画像か分かりませんでした。ファイルの場所を書いてください"
    return vision.describe(p2)


def m_hear_sound(slots):
    """音をきく : どんな音か（強弱・高さ・音色・ざらつき）を言う"""
    import audio
    p2 = slots.get("パス")
    if not p2:
        return "どの音のファイルか分かりませんでした"
    return audio.describe(p2)


def m_transcribe(slots):
    """ききとる : 音のファイルの、しゃべった中身を文字にする"""
    import speech
    p2 = slots.get("パス")
    if not p2:
        return "どの音のファイルか分かりませんでした"
    return speech.describe(p2)


def m_see_video(slots):
    """動画をみる : コマを間引いて、何が写っているかを順に言う"""
    import video
    p2 = slots.get("パス")
    if not p2:
        return "どの動画か分かりませんでした"
    # 何秒に1コマ見るかは、言われていれば従う。
    # 全部のコマを見ると CPU が焼けるので、既定は2秒に1コマ・上限40コマ
    every = float(slots.get("数") or video.EVERY)
    return video.describe(p2, every=max(0.2, every))


def m_run_code(slots):
    """うごかす : 小さなプログラムをその場で動かす（使い捨ての部屋の中で）"""
    import coderun
    code = slots.get("コード") or ""
    if not code.strip():
        return ("動かす中身がありません。\n"
                "  例: 「python で print(1+1) を動かして」\n"
                "      画面からなら ``` で囲んで貼ってください")
    return coderun.report(
        coderun.run(code, slots.get("言語", "python")))


def m_page_back(_):
    """まえのページ : ブラウザで1つ前に戻る"""
    import browser
    c = browser.go_back()
    return f"戻りました： {(c or {}).get('題', '')[:60]}"


def m_page_reload(_):
    """よみこみ直す : いま見ているページを読み込み直す"""
    import browser
    c = browser.reload_page()
    return f"読み込み直しました： {(c or {}).get('題', '')[:60]}"


def m_page_scroll(slots):
    """ページを動かす : 見ているページを上下に動かす"""
    import browser
    d = "up" if slots.get("向き") == "上" else "down"
    browser.scroll_page(d, slots.get("数", 1))
    return f"ページを{'上' if d == 'up' else '下'}へ動かしました"


def m_click_link(slots):
    """リンクをおす : ページの中の、その文字のリンクを押す"""
    import browser
    w = slots.get("語") or ""
    if not w:
        return "どのリンクか分かりませんでした"
    r = browser.click_link(w)
    return f"「{r['押した']}」を押しました\n  → {r['先'][:90]}"


def m_page_read(_):
    """ページをよむ : いま見ているページの中身を読む"""
    import browser
    c = browser.current() or {}
    t = browser.page_text(2000)
    return f"{c.get('題', '')[:70]}\n{c.get('url', '')[:90]}\n\n{t}"


# ============================================================
# 2026-08-30 追加。どれも この機械で 実際に動くことを確かめたものだけ。
#
#   足す時の決めごと（4-② の再発を防ぐ）:
#     ・OPS の名前と KIKEN/YOMU の名前を **一字一句そろえる**
#     ・足したら 必ず kaki_wasure() を回す
#     ・表に書き忘れたものは「跡」（いちばん重い）に落ちる作りなので、
#       黙って素通りはしない。それでも 書く
# ============================================================

def m_copy(slots):
    """クリップボードに入れる（読むだけの『クリップボード』の相手）"""
    t = slots.get("文") or slots.get("なに") or ""
    if not t:
        raise Exception("何を入れるか 分かりません")
    import subprocess as _sp
    pr = _sp.run(["pbcopy"], input=t, text=True)
    if pr.returncode != 0:
        raise Exception("クリップボードに入れられませんでした")
    return "コピーしました: " + (t[:60] + ("…" if len(t) > 60 else ""))


def m_say(slots):
    """声に出して読む"""
    t = slots.get("文") or slots.get("なに") or ""
    if not t:
        raise Exception("何を読むか 分かりません")
    _run(["say", "-v", "Kyoko", t[:500]], timeout=30)
    return "読み上げました: " + t[:60]


def m_notify(slots):
    """画面の隅に知らせを出す"""
    t = (slots.get("文") or slots.get("なに") or "").replace('"', "'")
    if not t:
        raise Exception("何を知らせるか 分かりません")
    _osa('display notification "%s" with title "カーネル"' % t[:200])
    return "知らせました: " + t[:60]


def m_quit_app(slots):
    """アプリを終わらせる。

    **保存していないものは 消える。** だから「外」ではなく「跡」。
    """
    n = slots.get("名前") or slots.get("なに") or ""
    if not n:
        raise Exception("どのアプリか 分かりません")
    _osa('tell application "%s" to quit' % n.replace('"', ""))
    return n + " を終わらせました"


def m_open_file(slots):
    """そのファイルを、ふだんのアプリで開く"""
    import os as _os
    p = slots.get("道") or slots.get("名前") or ""
    p = _os.path.expanduser(p)
    if not p or not _os.path.exists(p):
        raise Exception("そのファイルが見つかりません: " + str(p))
    _run(["open", p])
    return _os.path.basename(p) + " を開きました"


def m_new_tab(slots):
    """Chrome で新しいタブを開く"""
    u = slots.get("道") or slots.get("なに") or ""
    if u and not u.startswith(("http://", "https://")):
        u = "https://" + u
    if u:
        _osa('tell application "Google Chrome" to tell front window to '
             'make new tab with properties {URL:"%s"}' % u.replace('"', ""))
        return "新しいタブで開きました: " + u
    _osa('tell application "Google Chrome" to tell front window to make new tab')
    return "新しいタブを開きました"


def m_close_tab(_):
    """いま見ているタブを閉じる（⌘⇧T で戻せるので「外」）"""
    t = _osa('tell application "Google Chrome" to get title of active tab '
             'of front window')
    _osa('tell application "Google Chrome" to close active tab of front window')
    return "閉じました: " + (t or "(名前なし)")


def m_dark_mode(slots):
    """見た目を 暗い／明るい に切り替える"""
    t = (slots.get("なに") or "") + (slots.get("文") or "")
    if any(x in t for x in ("明る", "あかる", "ライト", "白")):
        v = "false"
    elif any(x in t for x in ("暗", "くら", "ダーク", "黒")):
        v = "true"
    else:
        v = "not dark mode"      # 言われていなければ 入れ替える
    _osa('tell application "System Events" to tell appearance preferences '
         'to set dark mode to %s' % v)
    ima = _osa('tell application "System Events" to tell appearance '
               'preferences to get dark mode')
    return "見た目を " + ("暗く" if ima == "true" else "明るく") + " しました"


def m_wifi_switch(slots):
    """Wi-Fi を 入れる／切る"""
    t = (slots.get("なに") or "") + (slots.get("文") or "")
    if any(x in t for x in ("切", "きっ", "off", "オフ", "消")):
        v, kotoba = "off", "切りました"
    else:
        v, kotoba = "on", "入れました"
    dev = ""
    for line in _run(["networksetup", "-listallhardwareports"]).splitlines():
        if "Wi-Fi" in line or "AirPort" in line:
            dev = "next"
        elif dev == "next" and line.startswith("Device:"):
            dev = line.split(":", 1)[1].strip()
            break
    if not dev or dev == "next":
        raise Exception("Wi-Fi の口が見つかりません")
    _run(["networksetup", "-setairportpower", dev, v])
    return "Wi-Fi を " + kotoba


def m_press_key(slots):
    """キーの組み合わせを送る（⌘S など）。

    **押した先で何が起きるかは こちらでは分からない。** だから「跡」。
    """
    t = (slots.get("文") or slots.get("なに") or "").strip()
    if not t:
        raise Exception("どのキーか 分かりません")
    shuu = []
    for kana, eng in (("コマンド", "command"), ("⌘", "command"),
                      ("シフト", "shift"), ("⇧", "shift"),
                      ("オプション", "option"), ("⌥", "option"),
                      ("コントロール", "control"), ("⌃", "control")):
        if kana in t:
            shuu.append(eng)
            t = t.replace(kana, "")
    ji = t.strip(" +＋のと").strip()
    if len(ji) != 1:
        raise Exception("送れるのは 1文字と 修飾キーの組み合わせだけです: " + ji)
    tsuki = (" using {%s}" % ", ".join(x + " down" for x in shuu)) if shuu else ""
    _osa('tell application "System Events" to keystroke "%s"%s' % (ji, tsuki))
    return "送りました: " + "+".join(shuu + [ji])


OPS = {
    "いま何時":          (m_time,             False),
    "こよみ":            (m_koyomi,           False),
    "電池":              (m_battery,          False),
    "空き容量":          (m_disk,             False),
    "メモリ":            (m_memory_use,       False),
    "音量":              (m_volume,           False),
    "音量をかえる":      (m_set_volume,       True),
    "ネット":            (m_wifi,             False),
    "開いているアプリ":  (m_apps,             False),
    "アプリをひらく":    (m_open_app,         True),
    "フォルダをひらく":  (m_open_folder,      True),
    "スクリーンショット": (m_screenshot,      True),
    "クリップボード":    (m_clipboard,        False),
    "画面をよむ":        (m_read_screen,      False),
    "画像をみる":        (m_see_image,        False),
    "音をきく":          (m_hear_sound,       False),
    "ききとる":          (m_transcribe,       False),
    "動画をみる":        (m_see_video,        False),
    "うごかす":          (m_run_code,         True),
    "まえのページ":      (m_page_back,        True),
    "よみこみ直す":      (m_page_reload,      True),
    "ページを動かす":    (m_page_scroll,      True),
    "リンクをおす":      (m_click_link,       True),
    "ページをよむ":      (m_page_read,        False),
    "画面でさがす":      (m_find_on_screen,   False),
    "おす":              (m_click_text,       True),
    "うちこむ":          (m_type_text,        True),
    "ゴミ箱":            (m_trash_count,      False),
    "最近のダウンロード": (m_downloads_recent, False),
    "起動してから":      (m_uptime,           False),
    "画面を消す":        (m_sleep_display,    True),
    # --- Chrome と Wikipedia ---
    "タブ一覧":          (m_tabs,             False),
    "いま見ているページ": (m_current_page,    False),
    "ページの中身":      (m_page_text,        False),
    "タブを探す":        (m_find_tab,         False),
    "ネットで調べる":    (m_web_search,       True),
    "ウィキペディア":    (m_wiki,             False),
    # --- 2026-08-30 追加 ---
    "コピーする":        (m_copy,             True),
    "読み上げる":        (m_say,              True),
    "知らせる":          (m_notify,           True),
    "アプリを閉じる":    (m_quit_app,         True),
    "ファイルをひらく":  (m_open_file,        True),
    "新しいタブ":        (m_new_tab,          True),
    "タブを閉じる":      (m_close_tab,        True),
    "見た目をかえる":    (m_dark_mode,        True),
    "ネットを切りかえる": (m_wifi_switch,     True),
    "キーをおす":        (m_press_key,        True),
}

# ============================================================
# 言い方 → 用件。ここが「指示文の表」
# 上から順に見て、最初に当たったものを採る
# ============================================================
PATTERNS = [
    # 見る・押すは、他の用件より先に見る。
    # 「◯◯を押して」を「アプリをひらく」に取られないため
    # プログラムを動かす／画像を見る。いちばん先に見る
    (r"```|(python|パイソン|javascript|ジャバスクリプト|js|node|"
     r"シェル|shell|bash|applescript).{0,12}(で|を)?.{0,12}"
     r"(うごか|動か|実行|走らせ|試し)", "うごかす"),
    (r"\.(mp4|mov|m4v|avi|mkv|webm)\b", "動画をみる"),
    # 「なんて言ってる？」は文字にする。「どんな音？」は音のようす
    (r"\.(aiff?|wav|m4a|mp3|caf|aac|flac)\b.{0,20}"
     r"(なんて|何て|なんと|何と|しゃべ|喋|言って|いって|文字|書き起こ)",
     "ききとる"),
    (r"\.(aiff?|wav|m4a|mp3|caf|aac|flac)\b", "音をきく"),
    (r"\.(jpe?g|png|gif|heic|webp|bmp|tiff?)\b", "画像をみる"),
    # ブラウザまわり。画面まわりより先に見る
    (r"(ページ|ぺーじ|サイト|記事|ブラウザ).{0,6}(よん|読ん|読み|読め|よめ)", "ページをよむ"),
    (r"(まえ|前|戻|もど).{0,4}(ページ|ぺーじ|に戻|へ戻)", "まえのページ"),
    (r"(よみこみ直|読み込み直|リロード|更新して)", "よみこみ直す"),
    (r"(ページ|ぺーじ|画面).{0,4}(を)?\s*(下|した|上|うえ)(へ|に)?\s*"
     r"(スクロール|うごか|動か|送っ)", "ページを動かす"),
    (r"(リンク|link).{0,10}(を)?\s*(押し|おし|クリック|ひらい|開い)", "リンクをおす"),
    (r"(画面|がめん|いま見えて|表示されて).{0,8}(よん|読ん|読み|読め|よめ|"
     r"なんて書|何て書|なんと書|何と書)", "画面をよむ"),
    (r"(画面|がめん).{0,6}(の)?どこ", "画面でさがす"),
    (r"(を|と書いてある|というボタン|のボタン|というところ)"
     r"\s*(ところ)?\s*(を)?\s*(押し|おし|クリック|タップ|ぽち)", "おす"),
    (r"(押し|おし|クリック|タップ)て?ください?$", "おす"),
    (r"(と|を)\s*(打ち|うち|入力し|タイプし)(こんで|込んで|て|ます)?", "うちこむ"),
    # 日付・時刻の計算は暦（koyomi.py）。「いま何時」より前に置く（「3時間後は何時」を今の時刻で答えないため）。
    # 形が読めなければ match() が飛ばして次へ（いま何時 か 頭脳）
    (r"(日後|日前|週間後|週間前|か月後|ヶ月後|カ月後|ヵ月後|年後|年前|時間後|時間前|分後|分前|何曜日|なんようび|"
     r"何月何日|何日|日付|あと何日)", "こよみ"),
    (r"(いま|今)?.*(何時(?!間)|なんじ|時刻|日付|きょうは何日|今日は何日)", "いま何時"),
    (r"(電池|バッテリ|充電)", "電池"),
    (r"(空き容量|ディスク|容量|ストレージ|空きは)", "空き容量"),
    (r"(メモリ|RAM|めもり)", "メモリ"),
    (r"音量.*(に(して|変え)|にし|下げ|上げ|\d)", "音量をかえる"),
    (r"(音量|ボリューム|音は)", "音量"),
    # 「ネットで◯◯を調べて」が先。「ネットつながってる？」より前に置く
    (r"(ネット|web|ウェブ|google|グーグル|chrome|クローム)\s*(で|を)?\s*"
     r"[^\s]{0,40}?(調べ|検索|ぐぐ)", "ネットで調べる"),
    # 入切が先。後ろだと「つながってる？」の側に取られる
    (r"(wi-?fi|ワイファイ|無線|ネット).{0,6}(を)?\s*"
     r"(切っ|きっ|切る|オフ|off|入れて|いれて|オン|on|つけて)",
     "ネットを切りかえる"),
    (r"(wi-?fi|ワイファイ|ネット|通信|つながって|接続)", "ネット"),
    (r"(開いてる|開いている|起動してる|動いてる).*(アプリ|ソフト)", "開いているアプリ"),
    # 細かいほうを先に。「タブを閉じて」が「アプリを閉じる」に取られる
    (r"(タブ|たぶ).{0,6}(を)?\s*(閉じ|とじ|消し)", "タブを閉じる"),
    (r"(アプリ|ソフト)?.{0,20}(を)?\s*(終了|終わらせ|閉じて|とじて|やめさせ|落とし)",
     "アプリを閉じる"),
    (r"(新しい|あたらしい).{0,4}(タブ|たぶ)|タブ.{0,4}(を)?(開い|ひらい|増や)", "新しいタブ"),
    (r"(読み上げ|よみあげ|声に出|しゃべって|喋って|音声で)", "読み上げる"),
    (r"(知らせ|しらせ|通知|お知らせ|リマインド)", "知らせる"),
    (r"(ダークモード|見た目|外観|テーマ).{0,8}(に|を)?\s*"
     r"(し|変え|かえ|切り替え|きりかえ)", "見た目をかえる"),
    (r"(暗く|くらく|明るく|あかるく).{0,4}(し|して)", "見た目をかえる"),
    (r"(⌘|コマンド|シフト|オプション|コントロール).{0,6}(を)?\s*"
     r"(押し|おし|送っ|打っ)", "キーをおす"),
    # ★ 2026-09-18: 「ダウンロードのフォルダを開いて」（erabu の例文）が アプリをひらく に横取りされて None だった → 場所つきは先に
    (r"(デスクトップ|ダウンロード|書類|ドキュメント)\s*(の)?\s*フォルダ.*(開|ひら)", "フォルダをひらく"),
    (r"(ファイル|書類).{0,10}(を)?\s*(ふだんの|いつもの|既定の)?"
     r"\s*(アプリで)?\s*(開い|ひらい)", "ファイルをひらく"),
    (r"(アプリ|ソフト)?.*(を)?(ひらい|開い|起動|立ち上げ)", "アプリをひらく"),
    (r"(finder|ファインダ).*(開|ひら)|(フォルダ|場所).*(finder|ファインダ)", "フォルダをひらく"),
    (r"(スクショ|スクリーンショット|画面を撮|画面撮|キャプチャ)", "スクリーンショット"),
    # 書くほうを 読むほうより先に。後ろだと「クリップボード」に取られる
    (r"(をコピー|コピーして(?!る|た|ます|い)|クリップボードに(入れ|コピー))",
     "コピーする"),
    (r"(クリップボード|コピーしてる|コピーした)", "クリップボード"),
    (r"ゴミ箱|ごみばこ|ごみ箱", "ゴミ箱"),
    (r"(最近|さっき).*(ダウンロード|落とし)", "最近のダウンロード"),
    (r"(起動して|立ち上げて|つけて)から.*(どれくらい|どのくらい|何時間)", "起動してから"),
    (r"(画面を消|画面消|ディスプレイ.*消|スリープ)", "画面を消す"),
    # --- Chrome と Wikipedia。語を取るものは、あとで材料を詰める ---
    (r"(タブ).*(一覧|全部|いくつ|見せ|教え|開いてる|開いている)|"
     r"(chrome|クローム).*(タブ|開いてる|開いている)", "タブ一覧"),
    (r"(いま|今|現在).*(見てる|見ている|開いてる|開いている).*(ページ|サイト|タブ)|"
     r"(このページ|今のページ).*(何|なに|url)", "いま見ているページ"),
    (r"(ページ|サイト|画面).*(中身|文字|本文|読ん|読んで|内容)", "ページの中身"),
    (r"タブ.*(から|の中).*(探|さが|見つけ)", "タブを探す"),

    (r"(wikipedia|ウィキペディア|ウィキ|百科事典)", "ウィキペディア"),
]
# ★ 2026-09-17: 続きの用件（kikai.py）。表はここで合流させ、言い方は先に見る
import kikai as _kikai
OPS.update(_kikai.OPS); KIKEN.update(_kikai.KIKEN); YOMU.update(_kikai.YOMU)
PATTERNS = _kikai.PATTERNS_MAE + PATTERNS
_COMPILED = [(re.compile(p, re.IGNORECASE), name) for p, name in PATTERNS]

# アプリの呼び名 → 本当の名前
APPS = {
    "メモ": "Notes", "notes": "Notes", "メモ帳": "Notes",
    "サファリ": "Safari", "safari": "Safari", "ブラウザ": "Safari",
    "クローム": "Google Chrome", "chrome": "Google Chrome",
    "ファインダ": "Finder", "finder": "Finder",
    "ターミナル": "Terminal", "terminal": "Terminal",
    "カレンダー": "Calendar", "メール": "Mail",
    "設定": "System Settings", "システム設定": "System Settings",
    "音楽": "Music", "写真": "Photos", "プレビュー": "Preview",
    "計算機": "Calculator", "電卓": "Calculator",
    "テキストエディット": "TextEdit", "マップ": "Maps", "地図": "Maps",
}

_NUM = re.compile(r"(\d+)")

# 「〜について」「〜を調べて」「〜って」から、調べたい語を取り出す
_WORD_PATS = [
    re.compile(r"[「『]([^」』]{1,40})[」』]"),
    re.compile(r"([^\s　、。]{1,40}?)\s*(?:について|に関して)"),
    # 「タブから」「ネットで」などをまたがないよう、助詞で区切る
    re.compile(r"([^\s　、。をはがのにへ]{1,40}?)\s*を\s*(?:調べ|検索|ぐぐ|探)"),
    # 「猫をネットで調べて」「富士山を Wikipedia で調べて」— 語 → を → 場所 → 調べ
    re.compile(r"^([^\s　、。をはがのにへ]{1,40}?)\s*を\s*(?:ネット|web|ウェブ|google|グーグル|ウィキペディア|wikipedia|ウィキ|百科事典|タブ)"),
    re.compile(r"([^\s　、。]{1,40}?)\s*(?:って|とは)\s*(?:何|なに|誰|どこ|いつ)"),
]
# 用件そのものを指す語は、調べたい語ではない
_NOT_WORD = {"ネット", "web", "ウェブ", "google", "グーグル", "chrome",
             "クローム", "wikipedia", "ウィキペディア", "ウィキ", "百科事典",
             "タブ", "ページ", "サイト", "これ", "それ", "あれ"}


def _word_for(text, name):
    """調べたい語を取り出す。取れなければ None"""
    for rx in _WORD_PATS:
        m = rx.search(text)
        if not m:
            continue
        w = m.group(1).strip("　 のでを")
        # 「タブから」「この中から」のような前置きは、調べたい語ではない
        for pre in ("タブから", "タブの中から", "この中から", "ここから",
                    "ネットで", "ウェブで", "webで", "グーグルで", "google で",
                    "ウィキペディアで", "ウィキで", "百科事典で", "wikipediaで",
                    "chromeで", "クロームで", "ブラウザで"):
            if w.lower().startswith(pre.lower()):
                w = w[len(pre):]
        w = w.strip("　 のでを")
        # 2文字以上、としていたので **一文字の語が 全部 捨てられていた**:
        #   「ネットで猫を調べて」→「猫」を取り出す →1文字→捨てる
        #   → 次の用件『ネット』に落ちて「つながっています」と答えていた
        # これは machine.py 自身が §7-② として戒めている
        # 「できないことを、堂々と 別のことをしてやる」そのもの。
        # 日本語は 一文字の語（猫・犬・雨・金）が ふつうにある。
        # 英数字だけは 2文字以上のまま（1文字だと 拾い過ぎる）
        naga = len(w) >= 2 or bool(_re.match(r"[぀-ヿ㐀-䶵一-鿿]", w))
        if w and w.lower() not in _NOT_WORD and naga:
            return w
    return None


def _path_of(text, kinds):
    """文の中から、ファイルのパスを取り出す。

    macOS のパスには空白が入る。
      /Users/…/Application Support/kernel-ai/はりつけ/cat_s 2.jpg
    空白で切る書き方をしていたので「2.jpg」だけを拾って落ちていた。

    そこで「拡張子の場所」を先に見つけ、そこから左へ伸ばしながら、
    実際にあるパスになったところで止める。
    実在するものが無ければ、空白で切った短い形を返す（相対パス用）。
    """
    hits = list(_re.finditer(r"\.(?:" + kinds + r")\b", text, _re.I))
    for m in reversed(hits):
        end = m.end()
        # 左へ1文字ずつ伸ばして、実在するいちばん長いものを採る
        best = None
        for start in range(0, m.start()):
            cand = text[start:end].strip()
            if not cand:
                continue
            full = os.path.expanduser(cand)
            if os.path.exists(full):
                best = full
                break          # いちばん左＝いちばん長いもの
        if best:
            return best
        # 実在しない（これから作る／相対で言われた）なら、空白で切る
        left = text.rfind(" ", 0, m.start()) + 1
        cand = text[left:end].strip("「」『』\"'、。 ")
        if cand:
            return os.path.expanduser(cand)
    return None


_QUOTE = _re.compile(r"[「『\"'“]([^」』\"'”]{1,60})[」』\"'”]")


def _quoted(text):
    """かぎかっこの中身。「保存」を押して → 保存

    かっこで囲ってあれば、そこが押したい文字だと迷わず決められる
    """
    m = _QUOTE.search(text)
    return m.group(1).strip() if m else None


def match(text):
    """言い方から用件を決める。当たらなければ None

    戻り値: (用件名, 材料の辞書) または None
    """
    low = text.lower()
    for rx, name in _COMPILED:
        if not rx.search(low):
            continue
        # 話題が当たっただけで、頼まれたことまで当たったとは限らない。
        #
        # 実測した誤動作（どれも「話題」だけを見ていたせい）:
        #   「スクリーンショットを整理して」 → 画面を撮っていた
        #   「タブを全部閉じて」           → タブの一覧を出していた
        #   「ゴミ箱を空にして」           → 件数を数えていた
        #
        # これは §7-② の「できないことを、堂々と別のことをしてやる」と同じ形。
        # 話題の語だけでなく、頼まれた「動き」も見る。
        if name in _UGOKI and not _UGOKI[name].search(text):
            continue
        if name in _SHINAI and _SHINAI[name].search(text):
            continue
        # 手で並べた言葉から漏れたものを、活用表で拾う
        if name == "スクリーンショット" and _nani_suru(text) in _FILE_ACTS:
            continue

        # 元の文をそのまま持たせる。
        # 部品側でも「何を頼まれたか」を見られるようにするため
        slots = _zairyou(name, text, low)
        if slots is None:
            continue
        return name, slots
    return None


def _zairyou(name, text, low):
    """用件が決まっているとき、その用件の材料を文から取る。取れない（この用件ではない）なら None。
    ★ 2026-09-18: match() の中にあった取り出しを外に出した。頭脳が 1トークンで用件を選ぶ（kimeru）とき、
      言い方が決まった形でなくても 同じ取り出しを通せるように。"""
    slots = {"_文": text}
    m = _NUM.search(text)
    if m:
        slots["数"] = int(m.group(1))
    if name == "こよみ":
        import koyomi
        if koyomi.kotae(text) is None:
            return None          # 暦の形で読めないなら、この用件ではない（頭脳に回す）
    if name in _kikai.OPS and not _kikai.slots_hook(name, text, slots):
        return None
    if name in ("読み上げる", "知らせる"):
        # 「「休憩」と知らせて」「おはようと読み上げて」の中身。無いと部品が「何を読むか分かりません」と言う
        w = _quoted(text)
        if not w:
            m4 = _re.search(r"^(.+?)(と|って)\s*(読み上げ|よみあげ|読んで|よんで|しゃべ|喋|知らせ|しらせ|通知)", text)
            w = m4.group(1).strip("　 ") if m4 else None
        if w:
            slots["文"] = w
    if name == "アプリをひらく":
        for k, v in APPS.items():
            if k in low:
                slots["アプリ"] = v
                break
        else:
            return None          # どのアプリか分からないなら、この用件ではない
    if name in ("画像をみる", "音をきく", "動画をみる", "ききとる"):
        kinds = {
            "ききとる":   r"aiff?|wav|m4a|mp3|caf|aac|flac",
            "画像をみる": r"jpe?g|png|gif|heic|webp|bmp|tiff?",
            "音をきく":   r"aiff?|wav|m4a|mp3|caf|aac|flac",
            "動画をみる": r"mp4|mov|m4v|avi|mkv|webm",
        }[name]
        got = _path_of(text, kinds)
        if not got:
            return None
        slots["パス"] = got
    if name == "うごかす":
        # ``` で囲まれていれば、その中身が動かす対象
        m2 = _re.search(r"```(\w+)?\s*\n?(.*?)```", text, _re.S)
        if m2:
            slots["コード"] = m2.group(2).strip()
            if m2.group(1):
                slots["言語"] = m2.group(1)
        else:
            # 「python で ◯◯ を動かして」の ◯◯
            m3 = _re.search(
                r"(?:python|パイソン|javascript|ジャバスクリプト|js|node|"
                r"シェル|shell|bash|applescript)\s*(?:で|を)?\s*(.+?)"
                r"\s*(?:を)?\s*(?:うごか|動か|実行|走らせ|試し)", text, _re.I)
            if not m3:
                return None
            slots["コード"] = m3.group(1).strip()
        low2 = text.lower()
        for k, v in (("javascript", "javascript"), ("ジャバスクリプト", "javascript"),
                     ("node", "javascript"), ("js", "javascript"),
                     ("シェル", "shell"), ("bash", "shell"), ("shell", "shell"),
                     ("applescript", "applescript"),
                     ("パイソン", "python"), ("python", "python")):
            if k in low2:
                slots.setdefault("言語", v)
                break
        slots.setdefault("言語", "python")
    if name == "ページを動かす":
        slots["向き"] = "上" if _re.search(r"(上|うえ)", text) else "下"
    if name == "リンクをおす":
        w = _quoted(text)
        if not w:
            return None          # どのリンクか分からないなら、この用件ではない
        slots["語"] = w
    if name in ("おす", "うちこむ", "画面でさがす"):
        w = _quoted(text) or _word_for(text, name)
        if not w:
            return None          # なにを押すのか分からないなら、この用件ではない
        slots["語"] = w
    if name in ("タブを探す", "ネットで調べる", "ウィキペディア"):
        w = _word_for(text, name)
        if not w:
            return None          # 何を調べるか分からないなら、この用件ではない
        slots["語"] = w
    if name == "フォルダをひらく":
        for k, v in (("デスクトップ", "Desktop"), ("ダウンロード", "Downloads"),
                     ("書類", "Documents"), ("ドキュメント", "Documents")):
            if k in text:
                slots["場所"] = v
                break
    return slots


def zairyou(name, text):
    """用件名 → 材料（外向き）。取れなければ None"""
    return _zairyou(name, text, text.lower())


def run(name, slots, confirm=None):
    """用件をひとつ実行する。

    confirm は「あぶないもの」の前に呼ばれる関数（True で実行）。

    「跡」の部品は、confirm が渡されていなければ実行しない。
    以前は confirm が None なら黙って実行していたので、
    設定で確認を切ると、画面への打ち込みもコード実行も素通りしていた。
    """
    fn, risky = OPS[name]
    k = kiken(name)
    # 1つの辞書を最後まで使い回す。
    # `fn(slots or {})` と書いていたため、slots が空のときだけ
    # 別の辞書が渡り、部品が書き込んだ「_できたファイル」が
    # 記録側に届いていなかった（記録の items がいつも 0 だった）
    slots = slots if isinstance(slots, dict) else {}
    if k != "読":
        if confirm is None:
            if k == "跡":
                # 跡が残るものは、聞けないなら やらない。
                # kernel 側で「関所が危険と言った手順は
                # ASK_BEFORE に関係なく実行しない」としているのと同じ考え
                return (f"「{name}」は、跡が残って戻せない操作です。\n"
                        f"確認を切った状態では実行しません。")
        elif not confirm(slots.get("_札") or name):     # 部品が「誰に何を」まで札に書けるように（メールを送る）
            return "やめました"

    ans = fn(slots)

    # 何をしたかを残す。
    # machine の部品は journal を通っていなかったので、
    # 「さっき何をされたのか」を後から確かめる手立てが無かった。
    # 戻せないものでも、残っていれば気づける
    if k != "読":
        _kiroku(name, k, slots, ans)
    return ans


def _kiroku(name, k, slots, ans):
    """machine の操作を journal に残す。

    ファイルが増えるものは、戻せる形（from/to）で残す。
    それ以外は履歴としてだけ残す（items が無いので /undo の対象にならない）。
    """
    try:
        import safety
        g = safety.Guard()
        items = []
        # スクリーンショットのように、出来たファイルの場所が分かるものは
        # ゴミ箱へ戻せる形にしておく
        deki = (slots or {}).get("_できたファイル")
        if deki and os.path.isfile(deki):
            items = [{"from": deki, "to": deki}]
        g.journal("machine", {
            "plan": [name], "slots": {x: y for x, y in (slots or {}).items()
                                      if x != "_文"},
            "items": items,
            "note": f"パソコン操作／{k}",
        })
    except Exception:
        pass          # 記録に失敗しても、本業は止めない


def describe():
    """できることのいちらん（/machine で見せる）"""
    out = []
    for name, (fn, risky) in OPS.items():
        doc = (fn.__doc__ or "").strip().split("\n")[0]
        out.append((name, doc.split(" : ")[-1], risky))
    return out
