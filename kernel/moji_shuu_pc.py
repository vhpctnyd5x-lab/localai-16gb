#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
moji_shuu_pc.py -- 「パソコンと日常の話」の文章だけを集める

  【なぜ分けるか】実測して分かったこと:
    ・でたらめに集めた百科事典 334万字で、意味あては 15/18（83%）。
      83万字のときも 15/18。4倍に増やしても 上がらなかった。
      増やして効いたのは「知らない語が減る」ところまでで、
      すでに知っている語の精度は 増やしても上がらない。
    ・そのうえ、肝心の語を間違える:
          資料 → いちばん近いのは 音楽（書類は最下位）
      百科事典で「資料」は 出典・文献の話。私たちの言う「資料」ではない。
    ・命令の言葉も入っていない: 教えて19回 / 枚数12回。区別がつかない。

  つまり 足りないのは 量ではなく 種類。
  ファイルの話・道具の話・日常の物の話 だけを集める。

  【集め方】
  もとになる題を決めて、その記事と、そこから張られた先を辿る。
  でたらめには取らない。相手のサーバーには間を空ける。
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wiki

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "corpus_pc_raw.txt")

TANE = [
    # ファイルと道具
    "ファイル (コンピュータ)", "ディレクトリ", "デスクトップ環境", "ゴミ箱 (GUI)",
    "画像ファイルフォーマット", "デジタル画像", "スクリーンショット", "壁紙 (コンピュータ)",
    "動画", "映像", "音楽配信", "MP3", "Portable Document Format", "文書",
    "テキストファイル", "データ圧縮", "ZIP (ファイルフォーマット)", "バックアップ",
    "ファイルマネージャ", "オペレーティングシステム", "macOS", "Microsoft Windows",
    "ウェブブラウザ", "電子メール", "アプリケーションソフトウェア", "クラウドストレージ",
    "ファイル名", "拡張子", "フォルダ", "コピー・アンド・ペースト",
    "デジタルカメラ", "スマートフォン", "プリンター", "キーボード (コンピュータ)",
    "表計算ソフト", "ワードプロセッサ", "プレゼンテーションソフト", "テキストエディタ",
    # 日常の物と暮らし
    "家具", "机", "椅子", "台所", "料理", "食器", "衣服", "掃除",
    "整理整頓", "買い物", "家事", "рабочий",  # 効かない題は飛ばされる
    "書類", "手紙", "写真", "アルバム", "日記", "予定表", "住所",
    "学校", "会社", "仕事", "家族", "友人", "旅行", "食事", "睡眠",
    "天気", "季節", "時間", "曜日", "電車", "自動車", "自転車", "道路",
]


def _matomete(titles):
    """20題ぶんの前書きと、張られた先を いっぺんに取る

    1題ずつ丸ごと取るのは遅すぎた（実測 4本/90秒＝10時間かかる）。
    本文まるごとは1回に1題しか取れない決まりなので、
    前書きだけにして 20題まとめて取る。前書きは言葉が詰まっていて、
    まわりの語を数えるには かえって都合がよい。
    """
    d = wiki._get({"action": "query", "titles": "|".join(titles),
                   "prop": "extracts|links", "explaintext": 1,
                   "exintro": 1, "exlimit": 20,
                   "pllimit": 500, "plnamespace": 0, "redirects": 1})
    out = []
    for pg in d.get("query", {}).get("pages", {}).values():
        honbun = pg.get("extract", "").strip()
        saki = [l.get("title", "") for l in pg.get("links", [])]
        out.append((pg.get("title", ""), honbun, saki))
    return out


def atsumeru(hon=3000, verbose=True):
    mita = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding="utf-8"):
            if line.startswith("\x01"):
                mita.add(line[1:].strip())
    machi = [t for t in TANE if t not in mita]
    tsuika = set(machi)
    f = open(OUT, "a", encoding="utf-8")
    ji, kotowarare = 0, 0
    try:
        while machi and len(mita) < hon:
            kumi = [machi.pop(0) for _ in range(min(20, len(machi)))]
            kumi = [t for t in kumi if t not in mita]
            if not kumi:
                continue
            try:
                kekka = _matomete(kumi)
            except Exception as e:
                kotowarare += 1
                if kotowarare > 12:
                    if verbose:
                        print(f"\n  何度も断られたので止めます（{e}）")
                    break
                matsu = min(300.0, 10.0 * (2 ** (kotowarare - 1)))
                if verbose:
                    print(f"\n  断られました。{matsu:.0f}秒待ちます", flush=True)
                time.sleep(matsu)
                machi = kumi + machi
                continue
            kotowarare = 0
            for title, body, saki in kekka:
                if title and body and len(body) > 200 and title not in mita:
                    mita.add(title)
                    f.write("\x01" + title + "\n" + body + "\n")
                    ji += len(body)
                for t in saki:
                    if t and t not in mita and t not in tsuika and len(machi) < hon * 3:
                        tsuika.add(t)
                        machi.append(t)
            f.flush()
            if verbose:
                print(f"\r  {len(mita)} 本 / {ji:,} 字 / 待ち {len(machi)}",
                      end="", flush=True)
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()
    if verbose:
        print()
    return len(mita), ji


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    print(f"パソコンと日常の話を {n} 本 集めます")
    hon, ji = atsumeru(n)
    print(f"できあがり: {hon} 本 / {ji:,} 字")
