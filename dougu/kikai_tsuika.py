# -*- coding: utf-8 -*-
"""kikai.py に足す macOS の用件（2026-09-24 Codex/Luna の案を Claude が確かめて入れた。クリップボードは秘密が映るので外した）。"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import time as _time


def _M():
    import machine
    return machine


def _run(argv, timeout=8):
    return _M()._run(argv, timeout=timeout)


def m_battery_status(slots):
    out = _run(["pmset", "-g", "batt"], timeout=8)
    pct = re.search(r"(\d+)%", out)
    if not pct:
        return "このMacではバッテリー残量を取得できません"
    low = out.lower()
    if "not charging" in low:
        state = "充電していません"
    elif "charging" in low:
        state = "充電中です"
    elif "charged" in low:
        state = "充電完了です"
    elif "discharging" in low:
        state = "バッテリー駆動中です"
    else:
        state = "電源に接続中です"
    return "バッテリー残量は %s%%、%s" % (pct.group(1), state)


def m_free_storage(slots):
    out = _run(["df", "-k", "/"], timeout=8)
    rows = [line.split() for line in out.splitlines() if line.strip()]
    if len(rows) < 2 or len(rows[-1]) < 4:
        return "起動ディスクの空き容量を取得できませんでした"
    gib = int(rows[-1][3]) / (1024 * 1024)
    return "起動ディスクの空き容量は %.1f GBです" % gib


def m_memory_pressure(slots):
    out = _run(["memory_pressure", "-Q"], timeout=15)
    pct = re.search(r"System-wide memory free percentage:\s*(\d+)%", out, re.I)
    if pct:
        free = int(pct.group(1))
        if free < 15:
            state = "メモリに余裕が少ない状態です"
        elif free < 30:
            state = "メモリ使用が多めです"
        else:
            state = "メモリに余裕があります"
        return "メモリの空き目安は %d%%。%s" % (free, state)
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if lines:
        return "メモリ圧迫の状況: " + lines[0][:180]
    return "メモリ圧迫の状況を取得できませんでした"


def m_wifi_name(slots):
    ports = _run(["networksetup", "-listallhardwareports"], timeout=8)
    device = None
    for block in ports.split("Hardware Port:")[1:]:
        label = block.splitlines()[0].strip() if block.splitlines() else ""
        if re.fullmatch(r"(Wi-Fi|AirPort)", label, re.I):
            found = re.search(r"Device:\s*(\S+)", block)
            if found:
                device = found.group(1)
                break
    if not device:
        return "Wi-Fiの接続名を取得できませんでした"
    out = _run(["networksetup", "-getairportnetwork", device], timeout=8)
    if "not associated" in out.lower():
        return "Wi-Fiには接続していません"
    found = re.search(r"Current Wi-Fi Network:\s*(.+)", out)
    if found:
        return "Wi-Fiの接続先は「%s」です" % found.group(1).strip()
    return "Wi-Fiの接続名を取得できませんでした"


def _walk_bluetooth(node, found):
    if isinstance(node, dict):
        name = node.get("device_name") or node.get("_name")
        status = node.get("device_isconnected", node.get("device_connected"))
        if name and status is not None:
            connected = str(status).strip().lower() in {
                "yes", "true", "1", "attrib_yes", "connected"
            }
            if connected:
                found.append(str(name))
        for value in node.values():
            _walk_bluetooth(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk_bluetooth(value, found)


def m_bluetooth_devices(slots):
    raw = _run(["system_profiler", "-json", "SPBluetoothDataType"], timeout=25)
    data = json.loads(raw)
    found = []
    _walk_bluetooth(data, found)
    names = list(dict.fromkeys(found))
    if not names:
        return "接続中のBluetooth機器はありません"
    return "接続中のBluetooth機器: " + "、".join(names[:12])


def m_uptime(slots):
    out = _run(["sysctl", "-n", "kern.boottime"], timeout=8)
    boot = re.search(r"sec\s*=\s*(\d+)", out)
    if not boot:
        return "起動してからの時間を取得できませんでした"
    elapsed = max(0, int(_time.time()) - int(boot.group(1)))
    days, rem = divmod(elapsed, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append("%d日" % days)
    if hours:
        parts.append("%d時間" % hours)
    parts.append("%d分" % minutes)
    return "起動してから " + " ".join(parts) + "です"


def m_macos_version(slots):
    version = _run(["sw_vers", "-productVersion"], timeout=8)
    build = _run(["sw_vers", "-buildVersion"], timeout=8)
    return "macOS %s（ビルド %s）です" % (version, build)


def _walk_displays(node, found):
    if isinstance(node, dict):
        name = node.get("_name")
        resolution = node.get("spdisplays_resolution") or node.get("_spdisplays_resolution")   # この Mac（macOS 26）は頭に _ が付く
        if name and resolution:
            found.append((str(name), str(resolution)))
        for value in node.values():
            _walk_displays(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk_displays(value, found)


def m_display_info(slots):
    raw = _run(["system_profiler", "-json", "SPDisplaysDataType"], timeout=25)
    data = json.loads(raw)
    displays = []
    _walk_displays(data, displays)
    if not displays:
        return "画面の数と解像度を取得できませんでした"
    rows = ["%s %s" % item for item in displays[:8]]
    return "画面は%d台です: %s" % (len(displays), "、".join(rows))


def m_running_apps(slots):
    script = '''tell application "System Events"
set appNames to name of every application process whose background only is false
set AppleScript's text item delimiters to linefeed
return appNames as text
end tell'''
    out = _run(["osascript", "-e", script], timeout=12)
    names = [name.strip() for name in out.splitlines() if name.strip()]
    if not names:
        return "動いているアプリは見つかりませんでした"
    return "動いているアプリ: " + "、".join(names[:20])


def m_front_app(slots):
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    out = _run(["osascript", "-e", script], timeout=8)
    return "いちばん前のアプリは「%s」です" % out


def m_volume_status(slots):
    out = _run(["osascript", "-e", "get output volume"], timeout=8)
    return "現在の音量は %s%%です" % out


def _dark_mode_is_on():
    script = '''tell application "System Events"
tell appearance preferences to get dark mode
end tell'''
    out = _run(["osascript", "-e", script], timeout=8).strip().lower()
    return out in ("true", "yes", "1")


def m_dark_mode_status(slots):
    state = "オン" if _dark_mode_is_on() else "オフ"
    return "ダークモードは%sです" % state


def m_system_load(slots):
    out = _run(["sysctl", "-n", "vm.loadavg"], timeout=8)
    numbers = re.findall(r"\d+(?:\.\d+)?", out)
    if len(numbers) < 3:
        return "システム負荷を取得できませんでした"
    return "システム負荷平均（1・5・15分）は %s / %s / %sです" % tuple(numbers[:3])


def m_battery_health(slots):
    out = _run(["system_profiler", "SPPowerDataType"], timeout=25)
    details = []
    for line in out.splitlines():
        line = line.strip()
        found = re.match(r"(Cycle Count|Condition|Maximum Capacity):\s*(.+)", line, re.I)
        if not found:
            continue
        label, value = found.group(1).lower(), found.group(2).strip()
        if label == "cycle count":
            details.append("充放電回数 %s回" % value)
        elif label == "condition":
            details.append("状態 %s" % value)
        else:
            details.append("最大容量 %s" % value)
    if not details:
        return "バッテリーの健康情報は見つかりませんでした"
    return "バッテリーの健康状態: " + "、".join(details)


def m_set_volume(slots):
    text = str(slots.get("_文", ""))
    found = re.search(r"(?:出力)?音量\s*(?:を|は)?\s*(\d{1,3})(?!\d)", text)
    if not found:
        raise Exception("音量を0から100の数字で指定してください")
    value = int(found.group(1))
    if not 0 <= value <= 100:
        raise Exception("音量は0から100で指定してください")
    _run(["osascript", "-e", "set volume output volume %d" % value], timeout=8)
    return "音量を%d%%にしました" % value


def m_toggle_dark_mode(slots):
    new_state = not _dark_mode_is_on()
    value = "true" if new_state else "false"
    script = '''tell application "System Events"
tell appearance preferences to set dark mode to %s
end tell''' % value
    _run(["osascript", "-e", script], timeout=8)
    return "ダークモードを%sにしました" % ("オン" if new_state else "オフ")


def _app_name(slots):
    candidate = slots.get("app") or slots.get("アプリ")
    text = str(slots.get("_文", ""))
    if not candidate:
        quoted = re.search(r'[「『"]([A-Za-z0-9][A-Za-z0-9 ._-]{0,39})[」』"]', text)
        plain = re.search(
            r"(?<![A-Za-z0-9._-])([A-Za-z][A-Za-z0-9._-]{0,31})"
            r"(?:アプリ)?を(?:開|起動|立ち上げ|閉じ|閉め|終了)",
            text,
        )
        candidate = quoted.group(1) if quoted else (plain.group(1) if plain else "")
    candidate = str(candidate).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}", candidate):
        raise Exception("アプリ名は英数字と空白、._-で指定してください")
    return candidate


def m_open_app(slots):
    app = _app_name(slots)
    _run(["open", "-a", app], timeout=15)
    return "アプリ「%s」を開きました" % app


def m_close_app(slots):
    app = _app_name(slots)
    script = 'tell application "%s" to quit' % app
    _run(["osascript", "-e", script], timeout=15)
    return "アプリ「%s」を終了しました" % app


def m_save_screenshot(slots):
    desktop = os.path.expanduser("~/Desktop")
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = os.path.join(desktop, "画面-%s.png" % stamp)
    _run(["screencapture", "-x", path], timeout=20)
    return "画面の写真をデスクトップに保存しました"


TSUIKA_OPS = {
    "バッテリー残量": (m_battery_status, False),
    "空き容量": (m_free_storage, False),
    "メモリ圧迫": (m_memory_pressure, False),
    "Wi-Fi名": (m_wifi_name, False),
    "Bluetooth機器": (m_bluetooth_devices, False),
    "起動時間": (m_uptime, False),
    "macOS版": (m_macos_version, False),
    "画面構成": (m_display_info, False),
    "起動中アプリ一覧": (m_running_apps, False),
    "最前面アプリ": (m_front_app, False),
    "現在の音量": (m_volume_status, False),
    "ダークモード状態": (m_dark_mode_status, False),
    "システム負荷": (m_system_load, False),
    "バッテリー健康状態": (m_battery_health, False),
    "音量設定": (m_set_volume, True),
    "ダークモード切替": (m_toggle_dark_mode, True),
    "アプリを開く": (m_open_app, True),
    "アプリを閉じる": (m_close_app, True),
    "画面写真を保存": (m_save_screenshot, True),
}

TSUIKA_PATTERNS = [
    (r"(?:バッテリー|電池).{0,8}(?:残量|残り|充電中|充電状態|充電状況|残り何(?:％|パーセント))", "バッテリー残量"),
    (r"(?:起動ディスク|ディスク|ストレージ|Mac|マック).{0,6}空き容量|空き容量.{0,6}(?:教|確認|どれ|何|は[？?]?$)", "空き容量"),
    (r"(?:メモリ|memory).{0,6}(?:圧迫|プレッシャー|不足|余裕).{0,8}(?:状態|状況|具合|教|確認|は[？?]?$)", "メモリ圧迫"),
    (r"(?:Wi-?Fi|無線LAN).{0,8}(?:名前|SSID|接続先|つながっている先|どこにつなが)|(?:Wi-Fi名|SSID.{0,6}(?:教|確認|何|は))", "Wi-Fi名"),
    (r"(?:Bluetooth|ブルートゥース).{0,8}(?:機器|デバイス|接続中|つながっているもの|何がつなが|一覧)", "Bluetooth機器"),
    (r"(?:起動してから|電源を入れてから|稼働時間|起動時間).{0,8}(?:どれくらい|何時間|何日|どのくらい|教|確認|経った|は[？?]?$)|(?:Mac|マック|パソコン).{0,6}(?:起動時間|稼働時間)", "起動時間"),
    (r"(?:macOS|Mac OS|OS X).{0,8}(?:バージョン|版|version)|(?:macOS|OS).{0,4}の(?:バージョン|版)", "macOS版"),
    (r"(?:画面|ディスプレイ|モニター).{0,8}(?:何台|台数|何枚|解像度|いくつ接続)|(?:ディスプレイ|モニター)の数", "画面構成"),
    (r"(?:動いている|起動中の|実行中の|開いている).{0,4}アプリ.{0,4}(?:一覧|リスト|何|教|見せ|表示|全部|は[？?]?$)|(?:起動中|実行中)アプリ(?:一覧|の一覧|リスト)", "起動中アプリ一覧"),
    (r"(?:いちばん前|一番前|最前面|前面).{0,4}(?:アプリ|ウィンドウ).{0,4}(?:何|どれ|名前|教|表示|は[？?]?$)|前面のアプリ名", "最前面アプリ"),
    (r"(?:出力)?音量.{0,8}(?:今|現在|何％|何パーセント|数値|値|レベル|どれくらい|教|確認|は[？?]?$)", "現在の音量"),
    (r"(?:ダークモード|ダークテーマ|外観モード).{0,6}(?:オン|オフ|状態|かどうか|有効|無効|設定|教|確認|は[？?]?$)", "ダークモード状態"),
    (r"(?:システム|Mac|マック|パソコン|CPU全体).{0,6}(?:負荷|ロードアベレージ|平均負荷).{0,6}(?:状態|値|今|確認|教|見|何|どれ|は[？?]?$)", "システム負荷"),
    (r"(?:バッテリー|電池).{0,8}(?:劣化|健康状態|最大容量|サイクル数|充放電回数|コンディション|寿命)", "バッテリー健康状態"),
    (r"(?:出力)?音量\s*(?:を|は)?\s*\d{1,3}\s*(?:[%％]\s*)?(?:に|へ)?\s*(?:して|設定して|合わせて|変えて)", "音量設定"),
    (r"(?:ダークモード|ダークテーマ).{0,8}(?:切り替|切替|反転|トグル)|(?:切り替|切替).{0,6}(?:ダークモード|ダークテーマ)", "ダークモード切替"),
    (r"(?:[「『\"]([A-Za-z][A-Za-z0-9 ._-]{0,39})[」』\"]|(?:^|[\s　])([A-Za-z][A-Za-z0-9._-]{0,31}))(?:アプリ)?を(?:開|起動|立ち上げ)", "アプリを開く"),
    (r"(?:[「『\"]([A-Za-z][A-Za-z0-9 ._-]{0,39})[」』\"]|(?:^|[\s　])([A-Za-z][A-Za-z0-9._-]{0,31}))(?:アプリ)?を(?:終了|閉じ|閉め)", "アプリを閉じる"),
    (r"(?:画面の写真|画面キャプチャ|スクリーンショット).{0,12}(?:デスクトップに)?保存|(?:画面|スクリーンショット).{0,6}撮って.{0,8}デスクトップに保存", "画面写真を保存"),
]

TSUIKA_KIKEN = {
    "音量設定": "外",
    "ダークモード切替": "外",
    "アプリを開く": "外",
    "アプリを閉じる": "外",
    "画面写真を保存": "外",
}

TSUIKA_TEST = [
    ("バッテリー残量は？", "バッテリー残量"),
    ("電池の残りを教えて", "バッテリー残量"),
    ("いまバッテリーは充電中？", "バッテリー残量"),
    ("電池の充電状態を確認して", "バッテリー残量"),

    ("起動ディスクの空き容量を教えて", "空き容量"),
    ("Macの空き容量はどれくらい？", "空き容量"),
    ("ストレージの空き容量を確認して", "空き容量"),
    ("ディスクの空き容量は？", "空き容量"),

    ("メモリの圧迫状態を教えて", "メモリ圧迫"),
    ("メモリプレッシャーの状況を確認して", "メモリ圧迫"),
    ("メモリ不足の状態を見て", "メモリ圧迫"),
    ("メモリに余裕があるか教えて", "メモリ圧迫"),

    ("Wi-Fiの名前を教えて", "Wi-Fi名"),
    ("WiFi SSIDを見せて", "Wi-Fi名"),
    ("無線LANの接続先は？", "Wi-Fi名"),
    ("Wi-Fiはどこにつながってる？", "Wi-Fi名"),

    ("Bluetooth機器を一覧で教えて", "Bluetooth機器"),
    ("ブルートゥースのデバイスを見せて", "Bluetooth機器"),
    ("Bluetoothで接続中の機器は？", "Bluetooth機器"),
    ("Bluetooth機器一覧を出して", "Bluetooth機器"),

    ("このMacの起動時間を教えて", "起動時間"),
    ("パソコンが起動してから何時間？", "起動時間"),
    ("電源を入れてからどれくらい？", "起動時間"),
    ("Macの稼働時間は？", "起動時間"),

    ("macOSのバージョンを教えて", "macOS版"),
    ("このMac OSの版を確認して", "macOS版"),
    ("OSのバージョンは何？", "macOS版"),
    ("今のmacOS版は？", "macOS版"),

    ("ディスプレイは何台つながってる？", "画面構成"),
    ("画面の解像度を教えて", "画面構成"),
    ("モニターの台数を確認して", "画面構成"),
    ("ディスプレイの解像度一覧を見せて", "画面構成"),

    ("いま起動中のアプリ一覧を見せて", "起動中アプリ一覧"),
    ("動いているアプリを全部表示して", "起動中アプリ一覧"),
    ("開いているアプリのリストを教えて", "起動中アプリ一覧"),
    ("実行中アプリの一覧は？", "起動中アプリ一覧"),

    ("最前面のアプリは何？", "最前面アプリ"),
    ("いちばん前のアプリ名を教えて", "最前面アプリ"),
    ("一番前にあるウィンドウ名は？", "最前面アプリ"),
    ("前面のアプリを教えて", "最前面アプリ"),


    ("音量の現在値を教えて", "現在の音量"),
    ("今の出力音量は何％？", "現在の音量"),
    ("音量レベルを確認して", "現在の音量"),
    ("音量を今いくつに設定している？", "現在の音量"),

    ("ダークモードがオンか確認して", "ダークモード状態"),
    ("ダークテーマの状態は？", "ダークモード状態"),
    ("今ダークモードが有効か教えて", "ダークモード状態"),
    ("外観モードがオフか見て", "ダークモード状態"),

    ("システム全体の負荷を教えて", "システム負荷"),
    ("Macの平均負荷を確認して", "システム負荷"),
    ("CPU全体のロードアベレージは？", "システム負荷"),
    ("パソコンのシステム負荷はどれくらい？", "システム負荷"),

    ("バッテリーの最大容量を教えて", "バッテリー健康状態"),
    ("電池のサイクル数を確認して", "バッテリー健康状態"),
    ("バッテリーの劣化具合は？", "バッテリー健康状態"),
    ("電池の健康状態を見たい", "バッテリー健康状態"),

    ("音量を50にして", "音量設定"),
    ("出力音量を25％に設定して", "音量設定"),
    ("音量 80% に合わせて", "音量設定"),
    ("音量を0にして", "音量設定"),

    ("ダークモードを切り替えて", "ダークモード切替"),
    ("ダークテーマを切替", "ダークモード切替"),
    ("ダークモードを反転して", "ダークモード切替"),
    ("切り替えてダークモード", "ダークモード切替"),

    ("Safariを開いて", "アプリを開く"),
    ("Notesアプリを起動して", "アプリを開く"),
    ("Finderを立ち上げて", "アプリを開く"),
    ("「Google Chrome」を開いて", "アプリを開く"),

    ("Safariを終了して", "アプリを閉じる"),
    ("Notesアプリを閉じて", "アプリを閉じる"),
    ("「Google Chrome」を閉じて", "アプリを閉じる"),
    ("Finderを終了", "アプリを閉じる"),

    ("画面の写真をデスクトップに保存して", "画面写真を保存"),
    ("スクリーンショットをデスクトップに保存", "画面写真を保存"),
    ("画面を撮ってデスクトップに保存して", "画面写真を保存"),
    ("画面キャプチャを保存して", "画面写真を保存"),

    ("今日の予定を見せて", None),
    ("タイマーを5分でかけて", None),
    ("未読メールを見せて", None),
    ("明日の天気を教えて", None),
    ("請求書のPDFを探して", None),
    ("音楽を止めて", None),
    ("画面の明るさを上げて", None),
    ("パソコンをロックして", None),
    ("Wi-Fiの速度を測って", None),
    ("Bluetoothをオンにして", None),
    ("Safariで新しいページを開いて", None),
    ("アプリが重いのはなぜ？", None),
    ("音を消して", None),
    ("メモを検索して", None),
    ("パスワードを確認して", None),
    ("バッテリーを節約したい", None),
    ("メモリを使うアプリを調べて", None),
    ("画面ロックを解除して", None),
    ("スクリーンショットを撮る方法を教えて", None),
    ("アプリを閉じる方法を教えて", None),
]

# 本当に新しいものだけ残す（Codex は kikai.py だけを見て、machine.py に前からある 電池・音量・空き容量・アプリを開く/閉じる・
# スクリーンショット・メモリ・起動してから・開いているアプリ と 同じものを 10個作っていた。名前が同じものは上書きになる）
NOKOSU = {"Bluetooth機器", "Wi-Fi名", "macOS版", "システム負荷", "ダークモード切替", "ダークモード状態",
          "バッテリー健康状態", "最前面アプリ", "画面構成"}
TSUIKA_OPS = {k: v for k, v in TSUIKA_OPS.items() if k in NOKOSU}
TSUIKA_KIKEN = {k: v for k, v in TSUIKA_KIKEN.items() if k in NOKOSU}
TSUIKA_PATTERNS = [(p, k) for p, k in TSUIKA_PATTERNS if k in NOKOSU]
TSUIKA_TEST = [(q, k) for q, k in TSUIKA_TEST if k is None or k in NOKOSU]
