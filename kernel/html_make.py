#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
html_make.py -- HTML ファイルを作る

  中身は、頼まれ方によって変える：
    ・何も言われない        → 白紙のひな形
    ・題を言われた          → その題の1ページ
    ・「〜の一覧」          → フォルダの中身を表にしたページ

  【決めごと】
   ・外から何も読み込まない（画像も文字も全部このファイルの中）
   ・上書きしない。同じ名前があれば連番を付ける
   ・入力された文字は必ずエスケープする（<script> をそのまま書かない）
"""
import os, html, datetime

# 見た目。1枚で完結させるので、全部この中に書く
STYLE = """
:root{--bg:#fbfaf7;--fg:#26241f;--dim:#6b675c;--line:#e0dcd2;--accent:#7a5c3e}
@media(prefers-color-scheme:dark){
  :root{--bg:#1a1917;--fg:#e8e4da;--dim:#9a958a;--line:#34322d;--accent:#c9a227}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font-family:"Hiragino Sans","Yu Gothic",system-ui,sans-serif;
  line-height:1.8;-webkit-font-smoothing:antialiased}
.wrap{max-width:44rem;margin:0 auto;padding:3rem 1.5rem 5rem}
h1{font-size:1.9rem;letter-spacing:.02em;margin:0 0 .3rem;font-weight:600}
.sub{color:var(--dim);font-size:.85rem;margin:0 0 2.5rem}
h2{font-size:1.15rem;margin:2.5rem 0 .8rem;padding-bottom:.4rem;
  border-bottom:1px solid var(--line)}
p{margin:0 0 1.1rem}
table{width:100%;border-collapse:collapse;font-size:.9rem;
  display:block;overflow-x:auto;white-space:nowrap}
th,td{text-align:left;padding:.55rem .8rem;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:600;font-size:.8rem;letter-spacing:.04em}
tr:hover td{background:color-mix(in srgb,var(--accent) 7%,transparent)}
.num{text-align:right;font-variant-numeric:tabular-nums}
footer{margin-top:4rem;padding-top:1.2rem;border-top:1px solid var(--line);
  color:var(--dim);font-size:.78rem}
code{background:color-mix(in srgb,var(--accent) 12%,transparent);
  padding:.1rem .35rem;border-radius:3px;font-size:.88em}
"""

SKEL = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{style}</style>
</head>
<body>
<div class="wrap">
<h1>{h1}</h1>
<p class="sub">{sub}</p>
{body}
<footer>{foot}</footer>
</div>
</body>
</html>
"""


def _esc(x):
    return html.escape(str(x), quote=True)


def _human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def _uniq(path):
    """上書きは絶対にしない。同じ名前があれば連番を足す"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{base} {i}{ext}"):
        i += 1
    return f"{base} {i}{ext}"


# ============================================================
# 中身の作り方
# ============================================================
def blank_body(title):
    return (
        "<h2>はじめに</h2>\n"
        "<p>ここに文章を書いてください。"
        "このファイルはブラウザでそのまま開けます。</p>\n"
        "<h2>つぎに</h2>\n"
        f"<p><code>{_esc(title)}.html</code> をテキストエディタで開けば、"
        "中身を書き換えられます。</p>")


def listing_body(files, where):
    """フォルダの中身を表にする"""
    rows = []
    for f in sorted(files, key=lambda x: os.path.basename(x).lower()):
        try:
            st = os.stat(f)
        except OSError:
            continue
        t = datetime.datetime.fromtimestamp(st.st_mtime)
        rows.append(
            "<tr><td>{}</td><td>{}</td><td class='num'>{}</td>"
            "<td class='num'>{}</td></tr>".format(
                _esc(os.path.basename(f)),
                _esc(os.path.splitext(f)[1].lstrip(".").upper() or "—"),
                _esc(_human(st.st_size)),
                t.strftime("%Y-%m-%d %H:%M")))
    if not rows:
        return "<p>ファイルがありませんでした。</p>"
    return (f"<h2>{_esc(where)} の中身（{len(rows)} 個）</h2>\n"
            "<table><thead><tr><th>名前</th><th>種類</th>"
            "<th class='num'>大きさ</th><th class='num'>更新</th></tr></thead>"
            "<tbody>" + "\n".join(rows) + "</tbody></table>")


def text_body(paragraphs):
    """ただの文章を並べる"""
    out = []
    for p in paragraphs:
        p = str(p).strip()
        if not p:
            continue
        if p.startswith("#"):
            out.append(f"<h2>{_esc(p.lstrip('# ').strip())}</h2>")
        else:
            out.append(f"<p>{_esc(p)}</p>")
    return "\n".join(out) or "<p>（中身は空です）</p>"


def build(title, body_html, sub=None):
    now = datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M")
    return SKEL.format(
        title=_esc(title), style=STYLE, h1=_esc(title),
        sub=_esc(sub or now), body=body_html,
        foot=f"カーネルが作りました ・ {now}")


def write(directory, name, title, body_html, sub=None):
    """本当に書き出す。作ったファイルの場所を返す"""
    if not name.lower().endswith((".html", ".htm")):
        name += ".html"
    path = _uniq(os.path.join(directory, name))
    with open(path, "w", encoding="utf-8") as f:
        f.write(build(title, body_html, sub))
    return path
