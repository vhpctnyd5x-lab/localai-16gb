#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gameparts.py -- ゲームを、部品を組み合わせて作る

  ────────────────────────────────────────────────
  なぜこれを作ったか
  ────────────────────────────────────────────────
  「テトリスを作って」で出てきた物は、先生が書いたものだった。
  カーネルは「テトリス」という語も知らないし、
  ゲームを作る部品を1つも持っていなかった。

  では、先生に頼らずに作る方法はあるか。ある。
  カーネルがファイル操作でやっているのと、まったく同じやり方でよい。

      デスクトップの画像を数えて
        → さがす → しぼる(種類) → かぞえる

      落ちてくるブロックを、そろったら消すゲーム
        → ばんめん → おちもの → よこうごき → まわす → そろい消し → てんすう

  ────────────────────────────────────────────────
  「これは、ただのひな形ではないのか」
  ────────────────────────────────────────────────
  違う。ひな形は「1つの決まったゲーム」を丸ごと持っておくこと。
  ここでは、部品どうしを組み替えられる。
  だから、こちらが思いつかなかった組み合わせも作れる。
  （たとえば「落ちてくるブロックを、跳ね返る玉で消す」）

  部品そのものは人（私）が手で書いた。
  それは「さがす」「かぞえる」を手で書いたのと同じ立場。
  カーネルがやるのは、どれを どの順で 使うかを決めて、組み立てること。

  ────────────────────────────────────────────────
  残る問題（正直に）
  ────────────────────────────────────────────────
  「テトリス」という名前から「落ちもの＋そろい消し」を思いつくには、
  名前と中身をつなぐ知識が要る。それはカードで教えるしかない。
  言い方で「落ちてきて、そろったら消える」と言われれば、名前を知らなくても作れる。
"""
import os, re

# ==================================================================
# ゲームの土台（ここは1回だけ手で書く。部品はこの上に乗る）
# ==================================================================
RUNTIME_HEAD = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{--bg:#15151a;--fg:#e8e6e1;--line:#2e2e36;--accent:#d4744a}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--fg);min-height:100vh;
       font:14px/1.7 "Hiragino Sans","Yu Gothic",system-ui,sans-serif;
       display:flex;flex-direction:column;align-items:center;
       justify-content:center;gap:14px;padding:20px}
  h1{font-size:15px;font-weight:600;letter-spacing:.04em;color:#b9b5ad}
  #wrap{position:relative}
  canvas{background:#0f0f13;border:1px solid var(--line);border-radius:8px;
         display:block;image-rendering:pixelated}
  #hud{display:flex;gap:18px;font-size:13px;color:#b9b5ad}
  #hud b{color:var(--accent);font-weight:600}
  #msg{position:absolute;inset:0;display:none;align-items:center;
       justify-content:center;flex-direction:column;gap:10px;
       background:rgba(15,15,19,.86);border-radius:8px;font-size:16px}
  #msg.on{display:flex}
  #msg small{font-size:12px;color:#9c9890}
  #help{font-size:11.5px;color:#77736c;text-align:center;max-width:420px}
</style></head><body>
<h1>__TITLE__</h1>
<div id="wrap">
  <canvas id="cv"></canvas>
  <div id="msg"><span id="msgt"></span><small>R キーでもう一度</small></div>
</div>
<div id="hud">__HUD__</div>
<div id="help">__HELP__</div>
<script>
"use strict";
// ── 土台 ──────────────────────────────────────────────
// 盤面はマス目で持つ。0 は空。1 以上は色の番号
const CELL = 24, COLS = __COLS__, ROWS = __ROWS__;
const COLORS = ["", "#4a90d9", "#d4744a", "#7fb08a", "#d9a441",
                "#a97fd9", "#d96a7f", "#57c3c8"];
const cv = document.getElementById("cv");
cv.width = COLS * CELL; cv.height = ROWS * CELL;
const cx = cv.getContext("2d");

const G = {
  cols: COLS, rows: ROWS, cell: CELL,
  grid: [], score: 0, over: false, won: false, t: 0, keys: {},
  msg: (s) => { document.getElementById("msgt").textContent = s;
                document.getElementById("msg").classList.add("on"); },
};
G.clear = () => { G.grid = Array.from({length: ROWS},
                    () => new Array(COLS).fill(0)); };
G.at  = (x, y) => (x < 0 || x >= COLS || y < 0 || y >= ROWS) ? -1 : G.grid[y][x];
G.set = (x, y, v) => { if (x >= 0 && x < COLS && y >= 0 && y < ROWS) G.grid[y][x] = v; };
G.box = (x, y, c) => {
  cx.fillStyle = COLORS[c] || "#888";
  cx.fillRect(x * CELL + 1, y * CELL + 1, CELL - 2, CELL - 2);
};
G.grid_draw = () => {
  for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++)
    if (G.grid[y][x]) G.box(x, y, G.grid[y][x]);
};
G.hud = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };

addEventListener("keydown", e => {
  G.keys[e.key] = true;
  if (["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"," "].includes(e.key))
    e.preventDefault();
  if (e.key === "r" || e.key === "R") location.reload();
  PARTS.forEach(p => p.key && p.key(e.key, true));
});
addEventListener("keyup", e => { G.keys[e.key] = false;
  PARTS.forEach(p => p.key && p.key(e.key, false)); });
cv.addEventListener("click", e => {
  const r = cv.getBoundingClientRect();
  const x = Math.floor((e.clientX - r.left) / CELL);
  const y = Math.floor((e.clientY - r.top) / CELL);
  PARTS.forEach(p => p.click && p.click(x, y));
});

const PARTS = [];
"""

RUNTIME_TAIL = """
// ── 動かす ────────────────────────────────────────────
G.clear();
PARTS.forEach(p => p.init && p.init());
let last = performance.now();
function loop(now){
  const dt = Math.min(50, now - last); last = now; G.t += dt;
  if (!G.over) PARTS.forEach(p => p.step && p.step(dt));
  cx.clearRect(0, 0, cv.width, cv.height);
  G.grid_draw();
  PARTS.forEach(p => p.draw && p.draw(cx));
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
</script></body></html>
"""


# ==================================================================
# 部品
#   要る … この部品より先に置かないといけないもの
#   出す … この部品が用意するもの（他の部品が「要る」で指す）
# ==================================================================
PARTS = {}


def part(name, setsumei, iru=(), dasu=(), hud="", help="", js=""):
    PARTS[name] = {"説明": setsumei, "要る": list(iru), "出す": list(dasu),
                   "hud": hud, "help": help, "js": js}


part("ばんめん", "マス目の盤面を用意する（土台。いつも要る）",
     dasu=["盤面"], js="")

part("おちもの", "ブロックが上から落ちてきて、下に着いたら固まる",
     iru=["盤面"], dasu=["こま", "落ちる"],
     hud='落ちた数 <b id="h-drop">0</b>',
     help="↓ で速く落とす",
     js="""
// 落ちもの : 4マスのかたまりが上から降ってくる
const SHAPES = [
  [[1,1],[1,1]],                    // ■■
  [[1,1,1,1]],                      // ────
  [[1,1,0],[0,1,1]],
  [[0,1,1],[1,1,0]],
  [[1,0,0],[1,1,1]],
  [[0,0,1],[1,1,1]],
  [[0,1,0],[1,1,1]],
];
const P = { cells: null, x: 0, y: 0, color: 1, fall: 0, speed: 520, drops: 0 };
function newPiece(){
  const s = SHAPES[(Math.random() * SHAPES.length) | 0];
  P.cells = s.map(r => r.slice());
  P.color = 1 + ((Math.random() * 6) | 0);
  P.x = ((G.cols - P.cells[0].length) / 2) | 0;
  P.y = 0;
  if (hits(P.x, P.y, P.cells)) { G.over = true; G.msg("おしまい"); }
}
function hits(px, py, cells){
  for (let y = 0; y < cells.length; y++)
    for (let x = 0; x < cells[y].length; x++){
      if (!cells[y][x]) continue;
      const gx = px + x, gy = py + y;
      if (gx < 0 || gx >= G.cols || gy >= G.rows) return true;
      if (gy >= 0 && G.grid[gy][gx]) return true;
    }
  return false;
}
function fix(){
  P.cells.forEach((row, y) => row.forEach((v, x) => {
    if (v) G.set(P.x + x, P.y + y, P.color);
  }));
  P.drops++; G.hud("h-drop", P.drops);
  if (typeof onFixed === "function") onFixed();
  newPiece();
}
PARTS.push({
  init(){ newPiece(); },
  step(dt){
    P.fall += dt * (G.keys["ArrowDown"] ? 8 : 1);
    if (P.fall < P.speed) return;
    P.fall = 0;
    if (hits(P.x, P.y + 1, P.cells)) fix(); else P.y++;
  },
  draw(){
    if (!P.cells) return;
    P.cells.forEach((row, y) => row.forEach((v, x) => {
      if (v) G.box(P.x + x, P.y + y, P.color);
    }));
  },
});
""")

part("よこうごき", "← → でブロックを左右に動かす",
     iru=["こま"], help="← → で動かす",
     js="""
PARTS.push({ key(k, down){
  if (!down || G.over || !P.cells) return;
  if (k === "ArrowLeft"  && !hits(P.x - 1, P.y, P.cells)) P.x--;
  if (k === "ArrowRight" && !hits(P.x + 1, P.y, P.cells)) P.x++;
}});
""")

part("まわす", "↑ でブロックを回す",
     iru=["こま"], help="↑ で回す",
     js="""
PARTS.push({ key(k, down){
  if (!down || G.over || !P.cells || k !== "ArrowUp") return;
  const w = P.cells[0].length, h = P.cells.length;
  const r = Array.from({length: w}, (_, y) =>
    Array.from({length: h}, (_, x) => P.cells[h - 1 - x][y]));
  // 端で回すとはみ出すので、少しずらして入るか試す
  for (const dx of [0, -1, 1, -2, 2]) {
    if (!hits(P.x + dx, P.y, r)) { P.cells = r; P.x += dx; return; }
  }
}});
""")

part("そろい消し", "横1列がそろったら消えて、上が落ちてくる",
     iru=["盤面"], dasu=["消える"],
     hud='消した列 <b id="h-line">0</b>',
     js="""
let lines = 0;
function clearFull(){
  let got = 0;
  for (let y = G.rows - 1; y >= 0; y--){
    if (G.grid[y].every(v => v)){
      G.grid.splice(y, 1);
      G.grid.unshift(new Array(G.cols).fill(0));
      got++; y++;
    }
  }
  if (got){
    lines += got; G.hud("h-line", lines);
    G.score += [0, 100, 300, 600, 1000][got] || 1000;
    G.hud("h-score", G.score);
  }
}
function onFixed(){ clearFull(); }
PARTS.push({ step(){ } });
""")

part("たま", "玉がとんで、かべではね返る",
     iru=["盤面"], dasu=["玉"],
     help="玉は勝手に動きます",
     js="""
const B = { x: G.cols / 2, y: G.rows - 4, vx: 0.006, vy: -0.008, r: 0.38 };
PARTS.push({
  step(dt){
    if (G.over) return;          // 終わったら、もう動かさない
    B.x += B.vx * dt; B.y += B.vy * dt;
    if (B.x < B.r){ B.x = B.r; B.vx *= -1; }
    if (B.x > G.cols - B.r){ B.x = G.cols - B.r; B.vx *= -1; }
    if (B.y < B.r){ B.y = B.r; B.vy *= -1; }
    // マスに当たったら、そのマスを消して跳ね返る
    const gx = Math.floor(B.x), gy = Math.floor(B.y);
    if (G.at(gx, gy) > 0){
      G.set(gx, gy, 0); B.vy *= -1;
      G.score += 10; G.hud("h-score", G.score);
    }
    if (B.y > G.rows + 1){
      if (typeof onMiss === "function") onMiss();
      else { G.over = true; G.msg("おしまい"); }
    }
    // 盤の上のものを全部消したら勝ち
    if (typeof BRICKS !== "undefined" && BRICKS
        && !G.grid.flat().some(v => v)){
      G.over = true; G.won = true; G.msg("ぜんぶ消した　てん " + G.score);
    }
  },
  draw(cx){
    cx.fillStyle = "#e8e6e1";
    cx.beginPath();
    cx.arc(B.x * G.cell, B.y * G.cell, B.r * G.cell, 0, 7);
    cx.fill();
  },
});
""")

part("ラケット", "← → で動かす板。玉を打ち返す",
     iru=["玉"], help="← → でラケットを動かす",
     js="""
const PAD = { x: G.cols / 2 - 1.5, w: 3, y: G.rows - 1.2, sp: 0.014, miss: 0 };
PARTS.push({
  step(dt){
    if (G.over) return;
    if (G.keys["ArrowLeft"])  PAD.x -= PAD.sp * dt;
    if (G.keys["ArrowRight"]) PAD.x += PAD.sp * dt;
    PAD.x = Math.max(0, Math.min(G.cols - PAD.w, PAD.x));
    if (B.vy > 0 && B.y + B.r >= PAD.y && B.y < PAD.y + 1
        && B.x >= PAD.x && B.x <= PAD.x + PAD.w){
      B.y = PAD.y - B.r;
      B.vy *= -1;
      // 当たった場所で跳ね返る向きが変わる。まん中なら真上
      B.vx += ((B.x - (PAD.x + PAD.w / 2)) / PAD.w) * 0.008;
      B.vx = Math.max(-0.014, Math.min(0.014, B.vx));
    }
  },
  draw(cx){
    cx.fillStyle = "#d4744a";
    cx.fillRect(PAD.x * G.cell, PAD.y * G.cell,
                PAD.w * G.cell, 0.7 * G.cell);
  },
});
function onMiss(){
  if (G.over) return;
  PAD.miss++;
  // 位置は必ず戻す。戻していなかったので、終わったあとも玉が落ち続け、
  // 打ちそこねが 527 回まで数えられていた
  B.x = G.cols / 2; B.y = G.rows - 4; B.vx = 0.006; B.vy = -0.008;
  if (PAD.miss >= 3){ G.over = true; G.msg("おしまい　てん " + G.score); }
}
""")

part("ブロックならべ", "上のほうにブロックを並べておく",
     iru=["盤面"],
     js="""
const BRICKS = true;
PARTS.push({ init(){
  for (let y = 2; y < 6; y++)
    for (let x = 1; x < G.cols - 1; x++)
      G.set(x, y, 1 + ((y - 2) % 6));
}});
""")

part("こうごおき", "押したところに、交互にしるしを置く",
     iru=["盤面"], dasu=["交互"],
     hud='いま <b id="h-turn">1人目</b>',
     help="マスを押して置きます",
     js="""
let turn = 1;
PARTS.push({
  click(x, y){
    if (G.over || G.at(x, y) !== 0) return;
    G.set(x, y, turn === 1 ? 2 : 4);
    if (typeof onPlaced === "function") onPlaced(x, y, turn);
    if (!G.over){ turn = turn === 1 ? 2 : 1;
                  G.hud("h-turn", turn + "人目"); }
  },
});
""")

part("そろえたら勝ち", "たて・よこ・ななめに 3つ そろえたら勝ち",
     iru=["交互"],
     js="""
const NEED = 3;
function onPlaced(x, y, who){
  const c = G.at(x, y);
  const dirs = [[1,0],[0,1],[1,1],[1,-1]];
  for (const [dx, dy] of dirs){
    let n = 1;
    for (const s of [1, -1])
      for (let k = 1; k < NEED; k++){
        if (G.at(x + dx*k*s, y + dy*k*s) !== c) break;
        n++;
      }
    if (n >= NEED){ G.over = true; G.won = true;
                    G.msg(who + "人目の勝ち"); return; }
  }
}
""")

part("てんすう", "点を数えて出す",
     hud='てん <b id="h-score">0</b>',
     js="""
PARTS.push({ init(){ G.hud("h-score", G.score); } });
""")

part("じかん", "のこり時間を数える。0 になったらおしまい",
     hud='のこり <b id="h-time">60</b> 秒',
     js="""
let left = 60000;
PARTS.push({ step(dt){
  left -= dt;
  G.hud("h-time", Math.max(0, Math.ceil(left / 1000)));
  if (left <= 0){ G.over = true; G.msg("時間切れ　てん " + G.score); }
}});
""")


# ==================================================================
# 言い方 → 部品
#   「テトリス」という名前は使わない。
#   何が起きるかを言われれば、名前を知らなくても組める
# ==================================================================
SAYS = [
    (r"(落ちて|おちて|降って|ふって|落ちもの|上から)", "おちもの"),
    (r"(左右|よこ|横|動か|うごか|操作)", "よこうごき"),
    (r"(回|まわ|回転|くるっ)", "まわす"),
    (r"(そろっ|揃っ|一列|1列|ならんだ|並んだ).{0,6}(消|け)", "そろい消し"),
    (r"(はねかえ|跳ね返|バウンド|玉|ボール|たま)", "たま"),
    (r"(ラケット|バー|パドル|板|打ち返)", "ラケット"),
    (r"(ブロック(を)?(ならべ|並べ)|ブロック崩し|れんが|レンガ)", "ブロックならべ"),
    (r"(交互|こうご|かわりばん|順番に置)", "こうごおき"),
    (r"(3つ|三つ|みっつ|そろえたら勝|並べたら勝|マルバツ|まるばつ|三目)",
     "そろえたら勝ち"),
    (r"(点|てん|得点|スコア)", "てんすう"),
    (r"(時間|じかん|秒|タイム|制限)", "じかん"),
]

# 名前と中身をつなぐカード。
# ここだけは「知識」なので、教えてもらうしかない。
# 教われば、名前でも呼べるようになる（辞書と同じ）
NAMES = {
    "テトリス": ["おちもの", "よこうごき", "まわす", "そろい消し", "てんすう"],
    "落ちもの": ["おちもの", "よこうごき", "まわす", "そろい消し", "てんすう"],
    "ブロック崩し": ["ブロックならべ", "たま", "ラケット", "てんすう"],
    "ブロックくずし": ["ブロックならべ", "たま", "ラケット", "てんすう"],
    "三目並べ": ["こうごおき", "そろえたら勝ち"],
    "まるばつ": ["こうごおき", "そろえたら勝ち"],
    "マルバツ": ["こうごおき", "そろえたら勝ち"],
    "ピンポン": ["たま", "ラケット", "てんすう"],
    "ポン": ["たま", "ラケット", "てんすう"],
}


def pick(text):
    """言い方から、使う部品を選ぶ。

    まず名前のカードを引く。当たらなければ、
    何が起きるかの言い方から1つずつ拾う
    """
    for name, parts in NAMES.items():
        if name.lower() in text.lower():
            return list(parts), f"「{name}」の札から"
    got = []
    for rx, p in SAYS:
        if re.search(rx, text) and p not in got:
            got.append(p)
    if got:
        return got, "言い方から拾って"

    # ── 名前も言い方も分からない。それでも「ゲーム」と言われたら ──
    # 分類子システム（bunruishi）に、部品の組み合わせを発明させる。
    # 私が札に書いた組み合わせではない、はじめての並びが出る。
    # 出したものは「前提が通っているか」を必ず確かめてある。
    if re.search(r"ゲーム|げーむ|あそ[べぶ]|遊[べぶ]", text):
        try:
            import bunruishi
            kumi = bunruishi.hatsumei()
            if kumi:
                return kumi, "自分で組み合わせを発明して"
        except Exception:
            pass
    return got, "言い方から拾って"


def resolve(names):
    """足りない前提を補って、置ける順に並べる。

    「まわす」には「こま」が要る → 「おちもの」を先に入れる、など。
    ファイル操作の solve() と同じ考え方
    """
    have, order = set(), []
    want = list(names)
    guard = 0
    while want and guard < 60:
        guard += 1
        moved = False
        for n in list(want):
            spec = PARTS.get(n)
            if not spec:
                want.remove(n); continue
            if all(k in have for k in spec["要る"]):
                order.append(n); have.update(spec["出す"]); want.remove(n)
                moved = True
        if moved:
            continue
        # 足りないものを、それを出す部品で補う
        need = None
        for n in want:
            for k in PARTS[n]["要る"]:
                if k not in have:
                    need = k; break
            if need: break
        if not need:
            break
        src = next((p for p, s in PARTS.items() if need in s["出す"]), None)
        if not src or src in order:
            want = [n for n in want
                    if all(k in have for k in PARTS[n]["要る"])]
            continue
        want.insert(0, src)
    return order


def assemble(names, title="ゲーム", cols=12, rows=18):
    """部品をつないで、1枚のページにする"""
    order = resolve(list(dict.fromkeys(["ばんめん"] + list(names))))
    if not order:
        raise Exception("使える部品がありませんでした")
    hud = "".join(f"<span>{PARTS[n]['hud']}</span>"
                  for n in order if PARTS[n]["hud"])
    helps = [PARTS[n]["help"] for n in order if PARTS[n]["help"]]
    body = "".join(PARTS[n]["js"] for n in order)
    html = (RUNTIME_HEAD
            .replace("__TITLE__", title)
            .replace("__COLS__", str(cols)).replace("__ROWS__", str(rows))
            .replace("__HUD__", hud or "<span>あそぶ</span>")
            .replace("__HELP__", "　".join(helps) or "R でもう一度")
            + body + RUNTIME_TAIL)
    return html, order


def describe():
    return [(n, s["説明"],
             "要る:" + "/".join(s["要る"]) if s["要る"] else "")
            for n, s in PARTS.items()]


if __name__ == "__main__":
    import sys
    print("■ 使える部品")
    for n, d, i in describe():
        print(f"  {n:<14} {d}   {i}")
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        names, how = pick(text)
        order = resolve(["ばんめん"] + names)
        print(f"\n■ 「{text}」")
        print(f"  {how}： {names}")
        print(f"  組み立て順： {' → '.join(order)}")
