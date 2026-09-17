# -*- coding: utf-8 -*-
"""kikai ── machine.py の続き。「パソコンの機能を全部触れるように」（本人・2026-09-17）で足した用件。

  読（何も変えない）: 予定・リマインダー一覧・メモを探す・ファイルを探す・いまの曲・天気・未読メール・
                      大きいファイル・重いアプリ・バックアップ・選んでいるファイル・IPアドレス
  外（元に戻せる）  : 音楽・タイマー・画面ロック・明るさ・設定を開く・辞書・消音
  跡（戻せない）    : メモを書く・リマインダーに入れる・再起動・電源を切る（必ず承認を挟む）

決まりは machine.py と同じ: 頭脳にシェルを渡さない（ここの関数は決まった命令だけ動かす）。
用件の名前を KIKEN に書き忘れたものは machine.kiken が「跡」にする（いちばん重い側に倒れる）。
"""
from __future__ import annotations
import datetime as _dt
import json
import os
import re
import subprocess
import threading
import urllib.parse
import urllib.request

# machine の助っ人を借りる（循環 import を避けて 関数の中で）
def _M():
    import machine
    return machine


# ── 読 ─────────────────────────────────────────────────────────────
def m_yotei(slots):
    """予定 : カレンダーの今日（明日・今週）の予定を並べる"""
    t = slots.get("_文", "")
    kyou = _dt.date.today()
    if "明日" in t or "あした" in t:
        a, b, na = kyou + _dt.timedelta(1), kyou + _dt.timedelta(2), "明日"
    elif "今週" in t or "こんしゅう" in t:
        a, b, na = kyou, kyou + _dt.timedelta(7 - kyou.weekday()), "今週"
    elif "来週" in t:
        a = kyou + _dt.timedelta(7 - kyou.weekday()); b, na = a + _dt.timedelta(7), "来週"
    else:
        a, b, na = kyou, kyou + _dt.timedelta(1), "今日"
    scr = '''
set d0 to (current date)
set time of d0 to 0
set d0 to d0 + (%d * days)
set d1 to d0 + (%d * days)
set out to ""
tell application "Calendar"
  repeat with c in calendars
    set evs to (every event of c whose start date >= d0 and start date < d1)
    repeat with e in evs
      set out to out & (time string of (start date of e)) & "\t" & (summary of e) & linefeed
    end repeat
  end repeat
end tell
return out''' % ((a - kyou).days, (b - a).days)
    out = _M()._run(["osascript", "-e", scr], timeout=60)
    rows = sorted(l for l in out.splitlines() if l.strip())
    if not rows:
        return f"{na}の予定はありません（カレンダー.app の中）"
    return f"{na}の予定 {len(rows)} 件\n" + "\n".join("  " + r.replace("\t", "  ") for r in rows[:20])


def m_reminder_list(slots):
    """リマインダー一覧 : 未完了のリマインダーを並べる"""
    scr = '''
set out to ""
tell application "Reminders"
  repeat with r in (every reminder whose completed is false)
    set out to out & (name of r) & linefeed
  end repeat
end tell
return out'''
    rows = [l for l in _M()._run(["osascript", "-e", scr], timeout=60).splitlines() if l.strip()]
    if not rows:
        return "未完了のリマインダーはありません"
    return f"リマインダー {len(rows)} 件\n" + "\n".join("  - " + r for r in rows[:20])


def m_memo_search(slots):
    """メモを探す : メモ.app を文字で探す"""
    w = slots.get("語") or ""
    scr = '''
set out to ""
tell application "Notes"
  set ns to (every note whose name contains "%s" or plaintext contains "%s")
  repeat with n in ns
    set out to out & (name of n) & linefeed
  end repeat
end tell
return out''' % (w.replace('"', "'"), w.replace('"', "'"))
    rows = [l for l in _M()._run(["osascript", "-e", scr], timeout=60).splitlines() if l.strip()]
    if not rows:
        return f"「{w}」を含むメモはありません"
    return f"「{w}」を含むメモ {len(rows)} 件\n" + "\n".join("  - " + r for r in rows[:15])


def m_file_search(slots):
    """ファイルを探す : Spotlight（mdfind）で名前から探す。家の中だけ"""
    w = slots.get("語") or ""
    home = os.path.expanduser("~")
    out = _M()._run(["mdfind", "-onlyin", home, "-name", w], timeout=20)
    rows = [l for l in out.splitlines() if l.strip() and "/Library/" not in l]
    if not rows:
        return f"「{w}」という名前のファイルは見つかりません"
    rows.sort(key=lambda p: -os.path.getmtime(p) if os.path.exists(p) else 0)
    return f"「{w}」 {len(rows)} 件（新しい順）\n" + "\n".join("  " + p.replace(home, "~") for p in rows[:10])


def m_now_playing(slots):
    """いまの曲 : ミュージック.app で流れている曲"""
    scr = '''
tell application "Music"
  if player state is playing then
    return (name of current track) & " / " & (artist of current track)
  else
    return ""
  end if
end tell'''
    out = _M()._run(["osascript", "-e", scr], timeout=15)
    return ("いま流れているのは " + out) if out else "いまは何も流れていません"


_TENKI_JI = {"Sunny": "晴れ", "Clear": "快晴", "Partly cloudy": "晴れ時々くもり", "Cloudy": "くもり", "Overcast": "くもり",
             "Mist": "もや", "Patchy rain possible": "ところにより雨", "Patchy rain nearby": "近くで雨", "Light rain": "小雨",
             "Moderate rain": "雨", "Heavy rain": "大雨", "Light rain shower": "にわか雨", "Thundery outbreaks possible": "雷雨のおそれ",
             "Fog": "霧", "Light drizzle": "霧雨", "Moderate or heavy rain shower": "強いにわか雨"}


def m_tenki(slots):
    """天気 : wttr.in（鍵なし）で今日と明日"""
    t = slots.get("_文", "")
    m = re.search(r"([^\s、。の]{2,10})の(天気|気温)", t)
    basho = m.group(1) if m and m.group(1) not in ("今日", "明日", "きょう", "あした", "今", "外") else (os.environ.get("KERNEL_BASHO") or "Tokyo")
    url = "https://wttr.in/%s?format=j1" % urllib.parse.quote(basho)
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as f:
            d = json.loads(f.read().decode("utf-8", "replace"))
    except Exception as e:
        raise Exception("天気が取れませんでした（ネットか wttr.in の都合）: %s" % type(e).__name__)
    cur = (d.get("current_condition") or [{}])[0]
    desc = (cur.get("weatherDesc") or [{}])[0].get("value", "")
    lines = ["%s いま %s℃ %s（体感 %s℃・湿度 %s%%）" % (basho, cur.get("temp_C", "?"), _TENKI_JI.get(desc, desc), cur.get("FeelsLikeC", "?"), cur.get("humidity", "?"))]
    for i, na in enumerate(("今日", "明日")):
        w = (d.get("weather") or [])[i:i + 1]
        if not w:
            continue
        w = w[0]
        ame = max((int(h.get("chanceofrain", 0) or 0) for h in w.get("hourly", [])), default=0)
        lines.append("%s %s〜%s℃ 雨の確率 最大 %d%%" % (na, w.get("mintempC", "?"), w.get("maxtempC", "?"), ame))
    return "\n".join(lines)


def m_mail_unread(slots):
    """未読メール : メール.app の未読の数と新しい方から5件の件名"""
    scr = '''
set out to ""
tell application "Mail"
  set ms to (messages of inbox whose read status is false)
  set n to count of ms
  set k to 0
  repeat with m in ms
    set k to k + 1
    if k > 5 then exit repeat
    set out to out & (sender of m) & "\t" & (subject of m) & linefeed
  end repeat
  return (n as string) & linefeed & out
end tell'''
    out = _M()._run(["osascript", "-e", scr], timeout=60).splitlines()
    n = int(out[0]) if out and out[0].strip().isdigit() else 0
    if n == 0:
        return "未読メールはありません"
    return f"未読 {n} 件。新しい方から:\n" + "\n".join("  " + l.replace("\t", " — ") for l in out[1:6] if l.strip())


def m_big_files(slots):
    """大きいファイル : 家の中で 500MB を超えるファイル（Spotlight）"""
    home = os.path.expanduser("~")
    out = _M()._run(["mdfind", "-onlyin", home, "kMDItemFSSize > 500000000"], timeout=20)
    rows = []
    for p in out.splitlines():
        try:
            rows.append((os.path.getsize(p), p))
        except OSError:
            pass
    if not rows:
        return "500MB を超えるファイルはありません"
    rows.sort(reverse=True)
    return "大きいファイル（上位 %d）\n" % min(10, len(rows)) + "\n".join("  %6s  %s" % (_M()._human(s), p.replace(home, "~")) for s, p in rows[:10])


def m_heavy_apps(slots):
    """重いアプリ : CPU とメモリを食っている順"""
    out = _M()._run(["ps", "-Ao", "%cpu,%mem,comm", "-r"], timeout=10).splitlines()[1:8]
    rows = []
    for l in out:
        parts = l.split(None, 2)
        if len(parts) == 3:
            rows.append("  CPU %5s%%  メモリ %5s%%  %s" % (parts[0], parts[1], os.path.basename(parts[2])[:40]))
    return "いま重いもの（CPU 順）\n" + "\n".join(rows)


def m_backup(slots):
    """バックアップ : Time Machine の最後のバックアップ"""
    M = _M()
    try:
        last = M._run(["tmutil", "latestbackup"], timeout=15)
    except Exception:
        last = ""
    if not last:
        return "Time Machine のバックアップは見つかりません（ディスクがつながっていないか、未設定）"
    m = re.search(r"(\d{4}-\d{2}-\d{2})-(\d{2})(\d{2})", last)
    when = "%s %s:%s" % (m.group(1), m.group(2), m.group(3)) if m else last
    return f"最後のバックアップ: {when}"


def m_selection(slots):
    """選んでいるファイル : Finder で選択中のもの"""
    scr = '''
set out to ""
tell application "Finder"
  repeat with i in (get selection)
    set out to out & (POSIX path of (i as alias)) & linefeed
  end repeat
end tell
return out'''
    rows = [l for l in _M()._run(["osascript", "-e", scr], timeout=15).splitlines() if l.strip()]
    home = os.path.expanduser("~")
    if not rows:
        return "Finder で何も選ばれていません"
    return f"選んでいるもの {len(rows)} 件\n" + "\n".join("  " + p.replace(home, "~") for p in rows[:10])


def m_ip(slots):
    """IPアドレス : この機械の家の中のアドレス"""
    M = _M()
    for dev in ("en0", "en1", "en2"):
        try:
            ip = M._run(["ipconfig", "getifaddr", dev], timeout=5)
            if ip:
                return f"この機械のアドレス: {ip}（{dev}）"
        except Exception:
            continue
    return "ネットにつながっていないようです（アドレスなし）"


# ── 外 ─────────────────────────────────────────────────────────────
def m_music(slots):
    """音楽 : ミュージック.app を 再生・止める・次・前"""
    t = slots.get("_文", "")
    if re.search(r"(次|つぎ|スキップ|飛ばし|とばし)", t):
        cmd, na = "next track", "次の曲にしました"
    elif re.search(r"(前|まえ|戻し|もどし)", t):
        cmd, na = "previous track", "前の曲に戻しました"
    elif re.search(r"(止め|とめ|停止|ストップ|やめ)", t):
        cmd, na = "pause", "止めました"
    else:
        cmd, na = "play", "流しました"
    _M()._run(["osascript", "-e", 'tell application "Music" to %s' % cmd], timeout=15)
    return na


_TIMERS = []


def m_timer(slots):
    """タイマー : ○分後に知らせる（通知と声）"""
    t = slots.get("_文", "")
    m = re.search(r"(\d+)\s*(秒|分|時間)", t)
    if not m:
        raise Exception("何分後か分かりません（例: 5分後に知らせて）")
    n = int(m.group(1)); byou = n * {"秒": 1, "分": 60, "時間": 3600}[m.group(2)]
    if byou > 24 * 3600:
        raise Exception("1日より先は無理です")
    msg = (_M()._quoted(t) or "時間です").replace('"', "'")[:100]

    def naru():
        try:
            subprocess.run(["osascript", "-e", 'display notification "%s" with title "カーネルのタイマー" sound name "Glass"' % msg], timeout=10)
            subprocess.run(["say", "-v", "Kyoko", msg], timeout=30)
        except Exception:
            pass
    th = threading.Timer(byou, naru); th.daemon = True; th.start(); _TIMERS.append(th)
    return "%d%s後に「%s」と知らせます" % (n, m.group(2), msg)


def m_lock(slots):
    """画面ロック : ロック画面にする"""
    _M()._osa('tell application "System Events" to keystroke "q" using {control down, command down}')
    return "画面をロックしました"


def m_brightness(slots):
    """明るさ : 画面を明るく／暗く（キーを押すのと同じ）"""
    t = slots.get("_文", "")
    down = bool(re.search(r"(暗く|くらく|下げ|さげ|落と)", t))
    n = max(1, min(16, int(slots.get("数") or 4)))
    code = 145 if down else 144
    _M()._osa('tell application "System Events" to repeat %d times\nkey code %d\nend repeat' % (n, code))
    return "画面を%s%dだんしました" % ("暗く" if down else "明るく", n)


_SETTEI = [
    (r"画面収録|スクリーン", "com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture", "画面収録"),
    (r"マイク", "com.apple.settings.PrivacySecurity.extension?Privacy_Microphone", "マイク"),
    (r"カメラ", "com.apple.settings.PrivacySecurity.extension?Privacy_Camera", "カメラ"),
    (r"アクセシビリティ|補助", "com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility", "アクセシビリティ"),
    (r"オートメーション|自動化", "com.apple.settings.PrivacySecurity.extension?Privacy_Automation", "オートメーション"),
    (r"プライバシー|セキュリティ", "com.apple.settings.PrivacySecurity.extension", "プライバシーとセキュリティ"),
    (r"bluetooth|ブルートゥース", "com.apple.BluetoothSettings", "Bluetooth"),
    (r"wi-?fi|ワイファイ|ネットワーク", "com.apple.wifi-settings-extension", "Wi-Fi"),
    (r"ディスプレイ|画面", "com.apple.Displays-Settings.extension", "ディスプレイ"),
    (r"サウンド|音", "com.apple.Sound-Settings.extension", "サウンド"),
    (r"通知", "com.apple.Notifications-Settings.extension", "通知"),
    (r"バッテリ|電池", "com.apple.Battery-Settings.extension", "バッテリー"),
    (r"アップデート|更新", "com.apple.Software-Update-Settings.extension", "ソフトウェアアップデート"),
    (r"キーボード", "com.apple.Keyboard-Settings.extension", "キーボード"),
    (r"トラックパッド|マウス", "com.apple.Trackpad-Settings.extension", "トラックパッド"),
    (r"一般", "com.apple.settings.General", "一般"),
]


def m_settei(slots):
    """設定を開く : システム設定の その項目を開く"""
    t = slots.get("_文", "").lower()
    for rx, pane, na in _SETTEI:
        if re.search(rx, t):
            _M()._run(["open", "x-apple.systempreferences:" + pane])
            return f"システム設定の「{na}」を開きました"
    _M()._run(["open", "-a", "System Settings"])
    return "システム設定を開きました"


def m_dict(slots):
    """辞書 : 辞書.app で引く"""
    w = slots.get("語") or ""
    _M()._run(["open", "dict://" + urllib.parse.quote(w)])
    return f"辞書で「{w}」を引きました"


def m_mute(slots):
    """消音 : 音を消す／戻す"""
    t = slots.get("_文", "")
    if re.search(r"(戻|もど|解除|つけ|出し)", t):
        _M()._osa("set volume without output muted"); return "音を戻しました"
    _M()._osa("set volume with output muted"); return "音を消しました"


# ── 跡 ─────────────────────────────────────────────────────────────
def m_memo_write(slots):
    """メモを書く : メモ.app に新しいメモを作る"""
    body = (slots.get("文") or "").strip()
    if not body:
        raise Exception("何をメモするか分かりません（例: 「牛乳を買う」とメモして）")
    dai = body.splitlines()[0][:40]
    scr = 'tell application "Notes" to make new note with properties {name:"%s", body:"%s"}' % (dai.replace('"', "'"), body.replace('"', "'").replace("\n", "<br>"))
    _M()._run(["osascript", "-e", scr], timeout=30)
    return f"メモに書きました: {dai}"


def m_reminder_add(slots):
    """リマインダーに入れる : 新しいリマインダーを作る"""
    body = (slots.get("文") or "").strip()
    if not body:
        raise Exception("何をリマインドするか分かりません（例: 「薬を飲む」をリマインダーに入れて）")
    scr = 'tell application "Reminders" to make new reminder with properties {name:"%s"}' % body.replace('"', "'")[:200]
    _M()._run(["osascript", "-e", scr], timeout=30)
    return f"リマインダーに入れました: {body[:60]}"


def m_restart(slots):
    """再起動 : Mac を再起動する（保存していないものは消える）"""
    _M()._osa('tell application "System Events" to restart')
    return "再起動します"


def m_shutdown(slots):
    """電源を切る : Mac の電源を切る"""
    _M()._osa('tell application "System Events" to shut down')
    return "電源を切ります"


# ── 表 ─────────────────────────────────────────────────────────────
OPS = {
    "予定":               (m_yotei,          False),
    "リマインダー一覧":   (m_reminder_list,  False),
    "メモを探す":         (m_memo_search,    False),
    "ファイルを探す":     (m_file_search,    False),
    "いまの曲":           (m_now_playing,    False),
    "天気":               (m_tenki,          False),
    "未読メール":         (m_mail_unread,    False),
    "大きいファイル":     (m_big_files,      False),
    "重いアプリ":         (m_heavy_apps,     False),
    "バックアップ":       (m_backup,         False),
    "選んでいるファイル": (m_selection,      False),
    "IPアドレス":         (m_ip,             False),
    "音楽":               (m_music,          True),
    "タイマー":           (m_timer,          True),
    "画面ロック":         (m_lock,           True),
    "明るさ":             (m_brightness,     True),
    "設定を開く":         (m_settei,         True),
    "辞書":               (m_dict,           True),
    "消音":               (m_mute,           True),
    "メモを書く":         (m_memo_write,     True),
    "リマインダーに入れる": (m_reminder_add, True),
    "再起動":             (m_restart,        True),
    "電源を切る":         (m_shutdown,       True),
}
YOMU = {"予定", "リマインダー一覧", "メモを探す", "ファイルを探す", "いまの曲", "天気", "未読メール",
        "大きいファイル", "重いアプリ", "バックアップ", "選んでいるファイル", "IPアドレス"}
KIKEN = {
    "音楽": "外", "タイマー": "外", "画面ロック": "外", "明るさ": "外", "設定を開く": "外", "辞書": "外", "消音": "外",
    "メモを書く": "跡",            # メモが増える（消せるが、勝手に増やさない）
    "リマインダーに入れる": "跡",
    "再起動": "跡",                # 保存していないものは消える
    "電源を切る": "跡",
}

# machine.PATTERNS の **前** に置く（先に当たった方が勝つ）。語は絞って、既存の用件を奪わないように
PATTERNS_MAE = [
    (r"(今日|きょう|明日|あした|今週|来週|の)?\s*(予定|スケジュール|カレンダー).{0,6}(何|なに|ある|教え|おしえ|見せ|みせ|は[？?]?$|は$)", "予定"),
    (r"リマインダー.{0,8}(入れ|いれ|足し|たし|追加|作っ|つくっ|登録)|(を|と)リマインド(し|して)", "リマインダーに入れる"),
    (r"リマインダー.{0,8}(一覧|見せ|みせ|教え|おしえ|何|なに|ある|は[？?]?$)", "リマインダー一覧"),
    (r"(メモ|ノート).{0,6}(探し|さがし|検索|ある[？?]?$)", "メモを探す"),
    (r"(と|を)(メモ|ノート)(し|に(書い|かい|残し|のこし|入れ|いれ|足し|追加))", "メモを書く"),
    (r"(ファイル|書類|画像|写真|動画|pdf|フォルダ).{0,8}(探し|さがし|検索|どこ)|という(名前|ファイル).{0,6}(探|さが)|[「『][^」』]+[」』].{0,4}(探し|さがし)", "ファイルを探す"),
    (r"(いま|今).{0,4}(流れて|ながれて|かかって|の曲|なんの曲|何の曲)|(曲|音楽).{0,4}(何|なに)[？?]?$", "いまの曲"),
    (r"(音楽|曲|ミュージック|music).{0,8}(止め|とめ|停止|ストップ|再生|流し|ながし|かけ|次|つぎ|前|まえ|スキップ|飛ばし|とばし)|(次|つぎ|前|まえ)の曲", "音楽"),
    (r"\d+\s*(秒|分|時間)\s*(後|あと|たったら|経ったら|したら).{0,10}(知らせ|しらせ|教え|おしえ|起こし|おこし|鳴らし|ならし|アラーム|タイマー)|タイマー.{0,6}(かけ|セット|して)", "タイマー"),
    (r"(天気|気温|降る|ふる|降りそう|傘)", "天気"),
    (r"(未読|新しい|届い|とどい).{0,4}メール|メール.{0,6}(来て|きて|届い|とどい|未読|ある[？?]?$)", "未読メール"),
    (r"(大きい|おおきい|でかい|重い|おもい).{0,4}(ファイル|書類)|(容量|ディスク).{0,8}(食|くって|くう|使って|つかって|圧迫)", "大きいファイル"),
    (r"(重い|おもい).{0,6}(アプリ|プロセス|もの|やつ|の)|(cpu|メモリ).{0,6}(食|くって|くう|使って|つかって).{0,8}(アプリ|プロセス|何|なに|どれ|の|は)", "重いアプリ"),
    (r"(タイムマシン|time ?machine|バックアップ)", "バックアップ"),
    (r"(選んで|選択して|選択中|選んだ).{0,6}(ファイル|もの|やつ|の)", "選んでいるファイル"),
    (r"(ip|アイピー).{0,6}(アドレス|は)", "IPアドレス"),
    (r"(画面|パソコン|mac|マック).{0,4}(ロック|施錠)", "画面ロック"),
    (r"(画面|ディスプレイ).{0,6}(明るく|あかるく|明るさ|あかるさ)|明るさ.{0,4}(上げ|下げ|あげ|さげ)", "明るさ"),
    (r"(設定|環境設定).{0,12}(開い|ひらい|出し|だし|見せ|みせ)", "設定を開く"),
    (r"辞書.{0,4}(で|を).{0,12}(引い|ひい|調べ|しらべ|見|み)", "辞書"),
    (r"(ミュート|消音|音を消し|音をけし|音を戻し|音をもどし|ミュート解除)", "消音"),
    (r"再起動", "再起動"),
    (r"(電源を切|電源をき|シャットダウン)", "電源を切る"),
]


def slots_hook(name, text, slots) -> bool:
    """用件ごとの材料の取り出し。False を返すと その用件ではない（次を見る）"""
    M = _M()
    if name in ("メモを探す", "ファイルを探す", "辞書"):
        w = M._quoted(text) or M._word_for(text, name)
        if not w:
            m = re.search(r"([^\s「」、。]{1,30})(という|って|の)?(ファイル|書類|画像|写真|動画|メモ|ノート|名前)", text)
            w = m.group(1) if m and m.group(1) not in ("大きい", "重い", "選んで") else None
        if not w:
            return False
        # 「ポチというファイル」「請求書のPDF」→ 語だけに
        w = re.sub(r"(という|っていう|って|の)?(ファイル|書類|画像|写真|動画|pdf|フォルダ|メモ|ノート|名前)$", "", w, flags=re.I).strip("　 ")
        if not w:
            return False
        slots["語"] = w
    if name in ("メモを書く", "リマインダーに入れる"):
        w = M._quoted(text)
        if not w:
            m = re.search(r"^(.+?)(を|と)(メモ|ノート|リマインド|リマインダー)", text)
            w = m.group(1).strip("　 ") if m else None
        if not w:
            return False
        slots["文"] = w
    return True
