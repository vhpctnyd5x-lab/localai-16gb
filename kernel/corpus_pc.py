#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corpus_pc.py -- 「パソコンの話」の文章を集める

  ────────────────────────────────────────────────
  なぜ作ったか
  ────────────────────────────────────────────────
  語の意味あてが、どうやっても当たらなかった。
  原因を辿ったら、表し方ではなく「材料」が悪かった。

      辞書の「画像」   → 人物 / 日本 / 洋風 / 弟子 / 先生   ← 絵画の意味
      辞書の「フォト」 → グラフ / 単位 / 平方 / センチ      ← 照度の単位
      Wikipediaの「壁紙」→ 建築物の内装仕上材              ← 建材の意味

  どれも「言葉の意味としては正しいが、パソコンの話ではない」。
  ここで欲しいのは、ファイルの話をしているときの意味だけ。

  ────────────────────────────────────────────────
  そこで、集め方をひっくり返した
  ────────────────────────────────────────────────
  ✗ 語を引いて、その説明を読む      … 別の意味が返ってくる
  ✓ パソコンの話の記事を丸ごと集めて、そこに出てくる語を見る

  「デジタル画像」「画像ファイルフォーマット」「スクリーンショット」…
  という記事に出てくる語は、ぜんぶ画像まわりの語だと言い切れる。
  意味を調べるのではなく、どの話に出てくるかで決める。

  掛け算は1回も使わない。数えるだけ。
"""
import os, re, sys, json, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wiki

OUT = os.path.join(HERE, "pc_web.json")

# 種類ごとの「話のもと」。この記事に出てくる語は、その種類の語とみなす
TOPICS = {
    "画像": ["デジタル画像", "画像ファイルフォーマット", "ラスターグラフィックス",
             "スクリーンショット", "写真", "JPEG", "Portable Network Graphics",
             "デジタルカメラ", "壁紙 (コンピュータ)", "サムネイル",
             "画像処理", "アイコン (コンピュータ)",
             "自分撮り", "スナップショット (写真)", "挿絵", "画像編集",
             "ペイントソフト", "GIF", "ビットマップ画像", "解像度",
             "Adobe Photoshop", "イラストレーション"],
    "動画": ["動画", "動画共有サービス", "MPEG-4", "映像", "ビデオ",
             "動画配信", "コーデック", "アニメーション", "映画",
             "ストリーミング", "YouTube", "ビデオカメラ", "フレームレート",
             "映像編集", "実写"],
    "音楽": ["音楽ファイル", "MP3", "デジタルオーディオ", "音楽配信",
             "音声ファイルフォーマット", "楽曲", "音響", "波形",
             "サンプリング周波数", "歌詞", "音源", "WAV", "着信メロディ",
             "オーディオプレーヤー"],
    "書類": ["Portable Document Format", "文書", "オフィススイート",
             "ワードプロセッサ", "表計算ソフト", "電子文書", "帳票",
             "契約書", "報告書", "請求書", "履歴書", "見積書",
             "プレゼンテーションソフト", "Microsoft Word"],
    "テキスト": ["テキストファイル", "プレーンテキスト", "文字コード",
                 "テキストエディタ", "Unicode", "改行コード", "原稿",
                 "草稿", "覚書", "メモ帳 (Windows)", "マークダウン",
                 "Comma-Separated Values", "ログファイル"],
    "圧縮": ["データ圧縮", "ZIP (ファイルフォーマット)", "アーカイブ",
             "可逆圧縮", "gzip", "非可逆圧縮", "7-Zip", "RAR",
             "tar (ファイルフォーマット)"],
}

# 語らしいかたまりの取り出し方。
#   ・カタカナの連なり            … スクリーンショット
#   ・漢字の連なり（2〜5文字）    … 圧縮率
#   ・英数字                      … JPEG, MP3
_TOKEN = re.compile(
    r"[ァ-ヴー]{2,12}|[一-龥]{2,5}|[A-Za-z][A-Za-z0-9]{1,11}")

# どの話にも出てくる語。手がかりにならないので捨てる
STOP = set("""
こと もの ため これ それ ある なる いる する できる ように 場合 とき 一般 使用
利用 必要 以下 以上 また および その他 なお ただし 参照 出典 脚注 関連 項目
日本 世界 現在 一部 多く 場合 方法 種類 意味 名称 上記 下記 存在 可能 不可
""".split())


def tokens(text):
    return [w for w in _TOKEN.findall(text) if w not in STOP]


def collect(chars=20000, verbose=True):
    """記事を集めて、語ごとに「どの話に、何回出たか」を数える

    記事ごとの語も残す。あとで
    「その語が出てくる記事はどんな記事か」を見るのに使う
    """
    per_topic = {}                       # 種類 → Counter(語 → 回数)
    per_doc = []                         # [(種類, 題, [語…])]
    for kind, titles in TOPICS.items():
        cnt = collections.Counter()
        for t in titles:
            try:
                a = wiki.article(t, chars)
            except Exception as e:
                if verbose:
                    print(f"    ✗ {t}: {e}")
                continue
            if not a:
                if verbose:
                    print(f"    － {t}: 記事なし")
                continue
            ws = tokens(a["本文"])
            cnt.update(ws)
            per_doc.append((kind, a["題"], ws))
            if verbose:
                print(f"    ✓ {kind:<5} {a['題']:<28} {len(ws):>5} 語")
        per_topic[kind] = cnt
    return per_topic, per_doc


def build(chars=20000, top=400, verbose=True):
    """集めた結果を、そのまま使える形にして保存する

    出すもの:
      "話ごとの語": 種類 → [(語, 回数), …]   ← 手本の材料
      "語の話ぶり": 語 → {種類: 回数, …}     ← その語がどの話に出るか
    """
    per_topic, per_doc = collect(chars, verbose)
    docs = len(per_doc)

    # どの話にも出る語は、手がかりにならない。話をまたぐ語ほど軽くする
    appears = collections.Counter()
    for cnt in per_topic.values():
        for w in cnt:
            appears[w] += 1
    nk = len(per_topic)

    out_topic = {}
    for kind, cnt in per_topic.items():
        # 「その話でよく出て、他の話ではあまり出ない」語を上から採る
        scored = [(c * (nk - appears[w] + 1), w, c) for w, c in cnt.items()
                  if c >= 2]
        scored.sort(reverse=True)
        out_topic[kind] = [[w, c] for _s, w, c in scored[:top]]

    profile = {}
    for kind, cnt in per_topic.items():
        for w, c in cnt.items():
            profile.setdefault(w, {})[kind] = c

    # 記事ごとの語（多い順に上位だけ）。これがあれば
    # 「その語が出る記事はどんな記事か」を、語そのものを使わずに言える
    out_doc = []
    for kind, title, ws in per_doc:
        c = collections.Counter(ws)
        out_doc.append({"種類": kind, "題": title,
                        "語": [[w, n] for w, n in c.most_common(300)]})

    data = {"話ごとの語": out_topic, "語の話ぶり": profile,
            "記事ごとの語": out_doc,
            "記事数": docs, "語数": len(profile)}
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    if verbose:
        print(f"\n  記事 {docs} 本 / 語 {len(profile):,} 個 → {OUT}")
        for k, v in out_topic.items():
            print(f"    {k:<5} {' / '.join(w for w, _c in v[:12])}")
    return data


def load():
    if not os.path.exists(OUT):
        return None
    return json.load(open(OUT, encoding="utf-8"))


if __name__ == "__main__":
    build(verbose=True)
