#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vision.py -- 画像に何が写っているかを言う（日本語で）

  eyes.py（文字を読む）とは別の仕組み。
      eyes.py   … VNRecognizeTextRequest      … 書いてある文字を読む
      vision.py … VNClassifyImageRequest 他   … 写っているものを言う

  どちらも macOS が最初から持っている Vision。
  何も入れなくていいし、ネットにも出ない。

  【実測】
      猫の写真   → Cat 0.749 ／ cat・feline・adult_cat 0.913
      ピザの写真 → pizza 0.877 ／ tableware 0.477
      車の写真   → machine 0.957 ／ automobile・vehicle 0.793
      既定の壁紙 → outdoor 0.926 ／ sky・blue_sky 0.918 ／ rocks 0.823

  返ってくる名前は英語なので、よく出るものだけ日本語に直す。
  表に無いものは英語のまま出す（勝手な訳をでっち上げない）。
"""
import json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
LOOK = os.path.join(HERE, "tools", "look")

# 英語の呼び名 → 日本語。よく出るものだけ。
# 無いものは英語のまま返す。当てずっぽうの訳をしない
JP = {
    # いきもの
    "animal": "動物", "cat": "猫", "Cat": "猫", "adult_cat": "猫（おとな）",
    "kitten": "子猫", "feline": "ネコ科", "dog": "犬", "Dog": "犬",
    "puppy": "子犬", "canine": "イヌ科", "mammal": "ほ乳類", "bird": "鳥",
    "fish": "魚", "insect": "虫", "horse": "馬", "cow": "牛", "sheep": "羊",
    "pig": "豚", "rabbit": "うさぎ", "reptile": "は虫類", "snake": "へび",
    "turtle": "かめ", "butterfly": "ちょう", "flower": "花", "plant": "植物",
    "tree": "木", "grass": "草", "leaf": "葉",
    # ひと
    "people": "人", "person": "人", "face": "顔", "man": "男性",
    "woman": "女性", "child": "子ども", "baby": "赤ちゃん", "crowd": "人ごみ",
    "hand": "手", "hair": "髪",
    # たべもの
    "food": "食べ物", "pizza": "ピザ", "bread": "パン", "cake": "ケーキ",
    "fruit": "くだもの", "vegetable": "野菜", "meat": "肉", "rice": "ごはん",
    "noodle": "めん", "soup": "スープ", "drink": "飲み物", "coffee": "コーヒー",
    "tea": "お茶", "beer": "ビール", "wine": "ワイン", "dessert": "デザート",
    "tableware": "食器", "plate": "皿", "cup": "コップ", "utensil": "道具",
    # のりもの・もの
    "machine": "機械", "vehicle": "乗り物", "automobile": "自動車",
    "car": "車", "truck": "トラック", "bus": "バス", "train": "電車",
    "bicycle": "自転車", "motorcycle": "バイク", "airplane": "飛行機",
    "boat": "船", "wheel": "車輪", "tire": "タイヤ", "rim": "ホイール",
    "furniture": "家具", "chair": "いす", "table": "テーブル", "bed": "ベッド",
    "book": "本", "clothing": "服", "shoe": "くつ", "bag": "かばん",
    "toy": "おもちゃ", "tool": "道具", "electronics": "電気製品",
    "computer": "パソコン", "phone": "電話", "camera": "カメラ",
    "screen": "画面", "keyboard": "キーボード", "clock": "時計",
    "money": "お金", "musical_instrument": "楽器",
    # ばしょ・けしき
    "outdoor": "屋外", "indoor": "屋内", "sky": "空", "blue_sky": "青空",
    "cloud": "雲", "sunset": "夕焼け", "night": "夜", "sun": "太陽",
    "moon": "月", "star": "星", "mountain": "山", "hill": "丘",
    "rocks": "岩", "rock": "岩", "beach": "浜辺", "sea": "海",
    "ocean": "海", "lake": "湖", "river": "川", "water": "水",
    "liquid": "水面", "snow": "雪", "rain": "雨", "forest": "森",
    "field": "野原", "garden": "庭", "park": "公園", "city": "街",
    "street": "通り", "road": "道", "building": "建物", "house": "家",
    "structure": "建てもの", "bridge": "橋", "window": "窓", "door": "とびら",
    "room": "部屋", "kitchen": "台所", "office": "事務所",
    # かたち・そのほか
    "art": "絵・作品", "illustrations": "イラスト", "painting": "絵画",
    "drawing": "線画", "photo": "写真", "document": "書類",
    "handwriting": "手書き", "text": "文字", "sign": "看板",
    "logo": "ロゴ", "pattern": "模様", "abstract": "抽象",
    "black_and_white": "白黒", "close_up": "接写", "landscape": "風景",
    "portrait": "人物写真", "silhouette": "影絵", "reflection": "うつりこみ",
    "fire": "火", "smoke": "けむり", "light": "光", "shadow": "かげ",
}


def ready():
    return os.path.exists(LOOK)


def jp(name):
    """英語の呼び名を日本語に。無ければ英語のまま"""
    return JP.get(name, JP.get(name.lower(), name))


def look(path, top=8, minimum=0.10, timeout=90):
    """画像1枚を見る。

    戻り値:
      {"まとめ", "写っているもの": [{"名","日本語","確からしさ"}…],
       "どうぶつ": [...], "顔": [...], "大きさ"}
    """
    if not ready():
        raise Exception("見る道具がありません（tools/look）")
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise Exception(f"その画像がありません: {path}")
    r = subprocess.run([LOOK, path, "--top", str(top), "--min", str(minimum)],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise Exception((r.stderr or "見られませんでした").strip()[:200])
    d = json.loads(r.stdout)
    for k in ("写っているもの", "どうぶつ"):
        for it in d.get(k, []):
            it["日本語"] = jp(it["名"])
    d["まとめ"] = " / ".join(
        dict.fromkeys(                        # 重複を消しつつ順番は保つ
            [jp(a["名"]) for a in d.get("どうぶつ", [])]
            + ([f"人の顔 {len(d['顔'])} つ"] if d.get("顔") else [])
            + [jp(l["名"]) for l in d.get("写っているもの", [])[:3]]))
    return d


def describe(path, top=8):
    """人に読ませる文にする"""
    d = look(path, top=top)
    name = os.path.basename(path)
    out = [f"{name}（{d['大きさ']['幅']}×{d['大きさ']['高さ']}）",
           f"  ひとことで言うと： {d['まとめ'] or '（分かりませんでした）'}"]
    if d.get("どうぶつ"):
        for a in d["どうぶつ"]:
            b = a["箱"]
            out.append(f"  どうぶつ： {a['日本語']}"
                       f"（{a['確からしさ']:.0%}）  そこ:({b['x']},{b['y']})")
    if d.get("顔"):
        out.append(f"  人の顔： {len(d['顔'])} つ")
    if d.get("写っているもの"):
        out.append("  写っていそうなもの：")
        for l in d["写っているもの"]:
            e = "" if l["日本語"] == l["名"] else f"  （{l['名']}）"
            out.append(f"    {l['確からしさ']:.0%}  {l['日本語']}{e}")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    if not sys.argv[1:]:
        print("  使い方: python3 vision.py <画像のパス>")
    for p in sys.argv[1:]:
        print(describe(p))
        print()
