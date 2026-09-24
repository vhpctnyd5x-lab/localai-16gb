#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_kensa.py -- 先生が書いた HTML を、置く前に 使い捨ての部屋で確かめる

  ここが「右脳と左脳の関所」。
  先生(LLM)が書いたものを そのまま信じない。次の4つを通ったものだけ通す。

    ① かたち   … タグの対応・<body> がある・読める字がある
    ② 外に出ない … 外のURL・fetch・WebSocket が無い（1ファイルで閉じている）
    ③ 動かせる … node がこの機械にある
    ④ 動く     … 偽の画面を与えて読み込み、ボタンを1回押して例外が出ない

  ④ が本命。①〜③ は「置けた」しか言わないが、④ だけが「動いた」と言える。
  ④ で例外が出たものは 置かない。「作った」とも言わない。

  Python 標準ライブラリのみ。走らせる所は coderun.py の囲い（sandbox-exec）を使う。
"""
import html.parser
import json
import re

import coderun

# 閉じタグを書かなくてよいタグ
KARA = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
# 閉じ忘れても咎めないタグ（HTML では許されている）
YURUI = {"p", "li", "tr", "td", "th", "option", "thead", "tbody", "dt", "dd",
         "html", "body", "head"}

# 外に出る書きかた
SOTO = [
    (r'(?:src|href)\s*=\s*["\']\s*(?:https?:)?//', "外のURLを読みに行く"),
    (r'url\s*\(\s*["\']?\s*(?:https?:)?//', "外の画像を読みに行く"),
    (r'\bfetch\s*\(', "ネットにつなぐ(fetch)"),
    (r'\bXMLHttpRequest\b', "ネットにつなぐ(XHR)"),
    (r'\bWebSocket\b', "ネットにつなぐ(WebSocket)"),
    (r'\bimport\s*\(', "外から取り込む"),
    (r'\bnavigator\s*\.\s*sendBeacon\b', "こっそり送る"),
]


class _Yomu(html.parser.HTMLParser):
    """かたちを見るだけ。中身は書き換えない"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tumi = []          # 開いたまま
        self.tag_ari = set()
        self.ji = []            # 見える字
        self.script = []        # <script> の中身
        self.iru_script = False
        self.iru_style = False
        self.tojinai = []       # 閉じ忘れ

    def handle_starttag(self, tag, attrs):
        self.tag_ari.add(tag)
        if tag == "script":
            self.iru_script = True
        if tag == "style":
            self.iru_style = True
        if tag not in KARA:
            self.tumi.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.tag_ari.add(tag)

    def handle_endtag(self, tag):
        if tag in KARA:
            return
        if tag == "script":
            self.iru_script = False
        if tag == "style":
            self.iru_style = False
        if tag in self.tumi:
            # ここまでに閉じ忘れたものを記録して、まとめて畳む
            while self.tumi:
                t = self.tumi.pop()
                if t == tag:
                    break
                if t not in YURUI:
                    self.tojinai.append(t)
        else:
            self.tojinai.append("余分な </%s>" % tag)

    def handle_data(self, d):
        if self.iru_script:
            self.script.append(d)
        elif not self.iru_style:
            s = d.strip()
            if s:
                self.ji.append(s)


# ── ④ のための 偽の画面 ────────────────────────────────
# 本物のブラウザは要らない。要るのは「読み込んで、押せる」ことだけ。
# 足りない機能を勝手に足さない。無いものに触ったら、そこで例外にする。
NISE_GAMEN = r"""
'use strict';
function __El(tag, id) {
  const e = {
    tagName:(tag||'div').toUpperCase(), id:id||'', __kodomo:[], __oya:null,
    style:new Proxy({},{get:(t,k)=>t[k]===undefined?'':t[k],set:(t,k,v)=>{t[k]=v;return true;}}),
    classList:{ __s:new Set(),
      add(...a){a.forEach(x=>this.__s.add(x));}, remove(...a){a.forEach(x=>this.__s.delete(x));},
      toggle(x){this.__s.has(x)?this.__s.delete(x):this.__s.add(x);}, contains(x){return this.__s.has(x);} },
    dataset:{}, __attr:{}, __han:{},
    textContent:'', innerHTML:'', innerText:'', value:'', disabled:false,
    checked:false, width:300, height:150,
    appendChild(c){ this.__kodomo.push(c); c.__oya=this; return c; },
    append(...c){ c.forEach(x=>{ if(x&&x.tagName) this.appendChild(x); }); },
    prepend(...c){ c.forEach(x=>{ if(x&&x.tagName){ this.__kodomo.unshift(x); x.__oya=this; } }); },
    removeChild(c){ const i=this.__kodomo.indexOf(c); if(i>=0) this.__kodomo.splice(i,1); return c; },
    remove(){ if(this.__oya) this.__oya.removeChild(this); },
    replaceChildren(...c){ this.__kodomo=[]; this.append(...c); },
    insertBefore(n,r){ const i=this.__kodomo.indexOf(r); this.__kodomo.splice(i<0?this.__kodomo.length:i,0,n); return n; },
    setAttribute(k,v){ this.__attr[k]=String(v); if(k==='id') this.id=String(v); },
    getAttribute(k){ return this.__attr[k]===undefined?null:this.__attr[k]; },
    hasAttribute(k){ return this.__attr[k]!==undefined; },
    removeAttribute(k){ delete this.__attr[k]; },
    addEventListener(t,f){ (this.__han[t]=this.__han[t]||[]).push(f); },
    removeEventListener(t,f){ const a=this.__han[t]||[]; const i=a.indexOf(f); if(i>=0) a.splice(i,1); },
    dispatchEvent(ev){ (this.__han[ev&&ev.type]||[]).forEach(f=>f.call(this,ev)); return true; },
    click(){ __hassei(this,'click'); },
    focus(){}, blur(){}, scrollIntoView(){}, getBoundingClientRect(){
      return {top:0,left:0,right:300,bottom:150,width:300,height:150,x:0,y:0}; },
    // canvas は 何を呼んでも 黙って返していたので、
    // 盤を1マスも描かないテトリスが 通っていた。**描いた回数を数える。**
    getContext(){ const el=this; return new Proxy({}, {
      get:(t,k)=>{
        if (k==='canvas') return el;
        if (typeof k!=='string') return undefined;
        if (/^(fillRect|strokeRect|fillText|strokeText|drawImage|fill|stroke|arc|lineTo|rect|putImageData)$/.test(k))
          return (...a)=>{ __egaita.n++; return undefined; };
        return (...a)=>({});
      },
      set:()=>true }); },
    querySelector(s){ return __sagasu(this,s); },
    querySelectorAll(s){ return __sagasu_zenbu(this,s); },
    get children(){ return this.__kodomo; },
    get childNodes(){ return this.__kodomo; },
    get firstChild(){ return this.__kodomo[0]||null; },
    get lastChild(){ return this.__kodomo[this.__kodomo.length-1]||null; },
    get parentNode(){ return this.__oya; },
    get parentElement(){ return this.__oya; },
  };
  Object.defineProperty(e,'onclick',{ set(f){ e.__han.click=f?[f]:[]; }, get(){ return (e.__han.click||[])[0]||null; } });
  Object.defineProperty(e,'onchange',{ set(f){ e.__han.change=f?[f]:[]; }, get(){ return (e.__han.change||[])[0]||null; } });
  return e;
}
function __minna(el, out){ out.push(el); el.__kodomo.forEach(c=>__minna(c,out)); return out; }
function __au(el, s){
  s = String(s).trim();
  if (s.startsWith('#')) return el.id === s.slice(1);
  if (s.startsWith('.')) return el.classList.contains(s.slice(1));
  return el.tagName === s.toUpperCase();
}
function __sagasu(root, s){ const a=__minna(root,[]).slice(1); for(const e of a) if(__au(e,s)) return e; return null; }
function __sagasu_zenbu(root, s){ return __minna(root,[]).slice(1).filter(e=>__au(e,s)); }

const __body = __El('body','__body');
const __id = Object.create(null);
IDS_HERE
for (const k in __id) __body.appendChild(__id[k]);

function __hassei(el, t){
  const ev = { type:t, target:el, currentTarget:el, key:'Enter', keyCode:13, code:'Enter',
               clientX:10, clientY:10, offsetX:10, offsetY:10, button:0,
               preventDefault(){}, stopPropagation(){} };
  const a = (el.__han[t] || []).slice();
  for (const f of a) f.call(el, ev);
  return a.length;
}

const __ato = [];
const __taimaa = [];
const __egaita = { n:0 };   // canvas に 何回 描いたか

const document = {
  body:__body, documentElement:__El('html'), head:__El('head'),
  readyState:'complete', title:'',
  getElementById(x){ return __id[x] || null; },
  querySelector(s){ return __au(__body,s) ? __body : __sagasu(__body,s); },
  querySelectorAll(s){ return __sagasu_zenbu(__body,s); },
  getElementsByTagName(t){ return __sagasu_zenbu(__body,t); },
  getElementsByClassName(c){ return __sagasu_zenbu(__body,'.'+c); },
  createElement(t){ return __El(t); },
  createTextNode(t){ const e=__El('span'); e.textContent=t; return e; },
  createDocumentFragment(){ return __El('div'); },
  addEventListener(t,f){ if(t==='DOMContentLoaded'||t==='load') __ato.push(f);
    else (this.__han[t]=this.__han[t]||[]).push(f); },
  removeEventListener(){}, dispatchEvent(){ return true; },
  __han:{},
};
const window = {
  document, innerWidth:1024, innerHeight:768, devicePixelRatio:1,
  __han:{},
  addEventListener(t,f){ if(t==='DOMContentLoaded'||t==='load') __ato.push(f);
    else (this.__han[t]=this.__han[t]||[]).push(f); },
  removeEventListener(){}, dispatchEvent(){ return true; },
  alert(){}, confirm(){ return true; }, prompt(){ return ''; },
  requestAnimationFrame(f){ __taimaa.push(f); return __taimaa.length; },
  cancelAnimationFrame(){}, getComputedStyle(){ return new Proxy({},{get:()=>''}); },
  setTimeout(f){ if(typeof f==='function') __taimaa.push(f); return __taimaa.length; },
  setInterval(f){ if(typeof f==='function') __taimaa.push(f); return __taimaa.length; },
  clearTimeout(){}, clearInterval(){}, scrollTo(){},
  matchMedia(){ return {matches:false, addListener(){}, addEventListener(){}}; },
};
// 置き場は本物を使わせない（部屋の外に何も残さない）
const localStorage = { __d:{}, getItem(k){ return this.__d[k]===undefined?null:this.__d[k]; },
  setItem(k,v){ this.__d[k]=String(v); }, removeItem(k){ delete this.__d[k]; }, clear(){ this.__d={}; } };
const sessionStorage = { getItem:()=>null, setItem(){}, removeItem(){}, clear(){} };
window.localStorage = localStorage;
window.sessionStorage = sessionStorage;
window.self = window; window.top = window; window.window = window;
const navigator = { userAgent:'kernel-kensa', language:'ja' };
const location = { href:'about:blank', hash:'', search:'', reload(){} };
const alert = window.alert, confirm = window.confirm, prompt = window.prompt;
const requestAnimationFrame = window.requestAnimationFrame;
const setTimeout = window.setTimeout, setInterval = window.setInterval;
const clearTimeout = window.clearTimeout, clearInterval = window.clearInterval;
const Audio = function(){ return { play(){}, pause(){}, volume:1, currentTime:0 }; };
const Image = function(){ return __El('img'); };
const HTMLElement = function(){};
const customElements = { define(){}, get(){ return undefined; } };

// ── ここから 先生の書いたもの ──
try {

GAME_HERE

  // HTML に直接書かれた onclick="play('rock')" を 繋ぐ。
  //
  //   これを繋いでいなかったので、ちゃんと動く じゃんけん が
  //   「押せる所がひとつもありません」で 落ちていた（実測・2026-08-30）。
  //   3B は この書きかたを好む。**検査が 働く物を落としていた。**
  //
  //   eval を ここで使うのは、先生の書いた function が この場所からしか
  //   見えないため（'use strict' で ブロックの中に閉じている）。
  //   **だから この繋ぎこみは 先生のコードと 同じブロックの中に無ければならない。**
  //   別のブロックに置いて `play is not defined` を出した（実測）。
  //   走る場所は 使い捨ての部屋の中で、囲い(sandbox-exec)は外れない。
  for (const [__k, __t, __code] of __INLINE) {
    const __el = __id[__k];
    if (!__el) continue;
    __el.addEventListener(__t, function (event) { return eval(__code); });
  }

} catch (e) {
  console.log('KENSA ' + JSON.stringify({読み込み:'例外', 例外:String(e && e.stack || e)}));
  process.exit(0);
}
// ── ここまで ──

try {
  // 読み込み後に走る約束のものを、走らせる
  for (const f of __ato.splice(0)) f({type:'DOMContentLoaded'});
  for (const f of __taimaa.splice(0, 30)) f(0);
} catch (e) {
  console.log('KENSA ' + JSON.stringify({読み込み:'あとで走る所で例外', 例外:String(e && e.stack || e)}));
  process.exit(0);
}

// ── 押してみる ──
//
//   **1周では足りない。** カードゲーム・神経衰弱の典型のバグは これ:
//       1枚目をめくる → 通る
//       2枚目をめくる → 「1枚目と比べる」所で壊れる
//   1回押して終わりにすると、状態が2手目以降で壊れる物が 全部 合格する。
//   3周まわして、どの周で壊れたかを 残す。
function __sugata(){ return JSON.stringify(__minna(__body, []).map(
  e => [e.textContent, e.innerHTML, e.value, e.disabled, [...e.classList.__s].sort()])); }
function __osu_ima(){ return __minna(__body, []).filter(e => (e.__han.click || []).length); }

// キーで遊ぶ物（テトリス・スネークなど）は 押す所が無くても 動く。
// document/window の keydown を 数に入れないと、働く物を落とす
const __kii = ['keydown','keyup','keypress'].reduce(
  (n,t) => n + (document.__han[t]||[]).length + (window.__han[t]||[]).length, 0);
const __kekka = { 読み込み:'通った', 押せる数:__osu_ima().length + __kii,
                  うち鍵:__kii, 押した:[], 変わった:false, 何周:0,
                  canvasあり:__minna(__body,[]).some(e=>e.tagName==='CANVAS'),
                  描いた:0 };
const __mae = __sugata();
const __KEY = ['ArrowLeft','ArrowRight','ArrowDown','Enter'];

for (let __shuu = 1; __shuu <= 3 && !__kekka.押した.some(o => o.結果 === '例外'); __shuu++) {
  __kekka.何周 = __shuu;
  // 押す所は 押すたびに 増えたり減ったりする（札が配られる等）ので 毎周 取り直す
  for (const el of __osu_ima().slice(0, 8)) {
    const namae = (el.id || el.tagName) + '・' + __shuu + '周目';
    try {
      __hassei(el, 'click');
      for (const f of __taimaa.splice(0, 30)) { try { f(0); } catch (e) {} }
    } catch (e) {
      __kekka.押した.push({ どれ:namae, 結果:'例外',
                            中身:String(e && e.message || e) });
      break;
    }
  }
  // キーで遊ぶ物は 矢印キーを 順に押してみる
  for (const f of (document.__han.keydown||[]).concat(window.__han.keydown||[])) {
    const k = __KEY[(__shuu - 1) % __KEY.length];
    try {
      f({type:'keydown', key:k, code:k, keyCode:37,
         preventDefault(){}, stopPropagation(){}});
      for (const g of __taimaa.splice(0, 30)) { try { g(0); } catch (e) {} }
    } catch (e) {
      __kekka.押した.push({ どれ:k + '・' + __shuu + '周目', 結果:'例外',
                            中身:String(e && e.message || e) });
      break;
    }
  }
}
if (!__kekka.押した.length) __kekka.押した.push({ どれ:'ぜんぶ', 結果:'通った' });
__kekka.変わった = (__mae !== __sugata());
__kekka.描いた = __egaita.n;
// canvas で描く物は、画面の字が変わらなくても 描いていれば 動いている
if (__egaita.n > 0) __kekka.変わった = true;
console.log('KENSA ' + JSON.stringify(__kekka));
"""


# HTML に直接書かれた しかけ（onclick="play('rock')" など）
_TAG_RE = re.compile(r'<\s*([a-zA-Z][\w-]*)((?:\s+[^<>]*?)?)/?>', re.DOTALL)
_ATTR_RE = re.compile(r'([a-zA-Z_:][-\w:.]*)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s"\'<>`]+))')
# 押す・変える に当たるもの。keydown は body 側に付くことがある
_INLINE_KOTO = {"onclick": "click", "onchange": "change", "oninput": "input",
                "onsubmit": "submit", "onkeydown": "keydown",
                "onkeyup": "keyup", "onmousedown": "click"}


def _yoso(src):
    """偽の画面に並べる 箱を作る。

    id が付いた物 と、onclick="..." が直接書かれた物 の 両方を拾う。

      **onclick を拾っていなかったので、ちゃんと動く じゃんけん が
      「押せる所がひとつもありません」で 落ちていた**（実測・2026-08-30）:

          <button onclick="play('rock')">グー</button>

      3B は この書きかたを好む。検査が 働く物を落としていた。

    戻り値: ([{"key","tag","id"}...], [(key, こと, 中身)...])
    """
    hako, inline, n = [], [], 0
    mita = set()
    for m in _TAG_RE.finditer(src):
        tag = m.group(1).lower()
        if tag in ("script", "style"):
            continue
        attrs = {}
        for a in _ATTR_RE.finditer(m.group(2) or ""):
            attrs[a.group(1).lower()] = (a.group(3) if a.group(3) is not None
                                         else a.group(4) if a.group(4) is not None
                                         else a.group(5) or "")
        jibun = attrs.get("id", "").strip()
        koto = [(k, v) for k, v in attrs.items() if k in _INLINE_KOTO]
        if not jibun and not koto:
            continue
        if jibun:
            if jibun in mita:
                continue
            mita.add(jibun)
            key = jibun
        else:
            n += 1
            key = "__nashi%d" % n
        hako.append({"key": key, "tag": tag, "id": jibun})
        for k, v in koto:
            if v.strip():
                inline.append((key, _INLINE_KOTO[k], v))
    return hako, inline


# node の言い分から、**理由の行だけ**を取り出す。
#
#   これを入れる前は 最終行を取っていた。node の最終行は "Node.js v24.14.1"、
#   つまり ただのバージョン表示。落ちた理由が全部これになり、
#   しかもその文字列が そのまま先生への「直してください」に渡っていた。
#   直しが効かないのは 当たり前だった（実測で気づいた）。
_RIYUU = re.compile(r"^\s*(?:Uncaught\s+)?(\w*(?:Error|Exception))\b\s*:?(.*)$")


def _naze(r):
    err = (r.get("エラー") or "").strip().splitlines()
    for line in err:
        m = _RIYUU.match(line)
        if m:
            return (m.group(1) + ":" + m.group(2))[:150].strip()
    # 理由の行が無いなら、意味のありそうな行を上から探す
    for line in err:
        s = line.strip()
        if s and not s.startswith(("at ", "^", "Node.js v")) and len(s) > 3:
            return s[:150]
    return f"終了コード {r.get('終了コード')}"


def kensa(src, name="(名前なし)", ugoku=False):
    """HTML を確かめる。戻り値: dict

    ugoku=True … 「動く物」を頼んだ時。動く仕掛けが無ければ 落とす。

      ここを False のまま 動く物を測って、ひどい目に遭った（実測・2026-08-30）:

          テトリス       814文字  JavaScript が1行も無い  → 通った
          オセロ         692文字  JavaScript が1行も無い  → 通った
          マインスイーパ 3988文字 押せる所 0（動かない）  → 通った

      難しいお題で 6/6 が3回 出たのは 3B が優秀だからではなく、
      **検査が「壊れていないか」しか見ていなかったから**。
      4-① と同じ構図（正解チェックだけでは 1件も出ない）。

    {"合格":bool, "だめな所":[...], "気になる所":[...], "動き":{...}}
    """
    warui, kininaru = [], []

    # ── ① かたち ──
    y = _Yomu()
    try:
        y.feed(src)
        y.close()
    except Exception as e:
        return {"合格": False, "だめな所": [f"かたちが読めません: {e}"],
                "気になる所": [], "動き": None, "名前": name}

    nokori = [t for t in y.tumi if t not in YURUI]
    if nokori:
        warui.append("閉じていないタグ: " + "、".join(f"<{t}>" for t in nokori[:5]))
    if y.tojinai:
        kininaru.append("閉じ忘れ: " + "、".join(y.tojinai[:5]))
    if "body" not in y.tag_ari:
        warui.append("<body> がありません")
    # 白紙かどうかだけを見る。字数の下限を高くすると、
    # 絵だけのページや 短い見出しのページを 誤って落とす（実測で踏んだ）
    ji = "".join(y.ji)
    if not ji and not (y.tag_ari & {"canvas", "img", "svg", "input", "button"}):
        warui.append("白紙です（読める字も 絵も 押す所もありません）")

    # ── ② 外に出ない ──
    for rx, why in SOTO:
        m = re.search(rx, src)
        if m:
            warui.append(f"{why}（{m.group(0)[:30]}）")

    js = "\n".join(y.script).strip()
    if not js:
        # 見るだけのページ（一覧・文章）なら それでよい。
        # だが「動く物」を頼んだのなら、仕掛けが無い時点で 出来ていない
        if ugoku:
            warui.append("動く仕掛けがありません（<script> が1つもない）")
        return {"合格": not warui, "だめな所": warui, "気になる所": kininaru,
                "動き": {"読み込み": "script なし"}, "名前": name}

    # ── ③ 動かせるか ──
    r = coderun.run("process.stdout.write('ok')", "javascript")
    if r["終了コード"] != 0:
        kininaru.append("node が使えないので、動きは確かめられませんでした")
        return {"合格": not warui, "だめな所": warui, "気になる所": kininaru,
                "動き": None, "名前": name}

    # ── ④ 動く ──
    yoso, inline = _yoso(src)
    hako = "\n".join(
        "__id[%s] = __El(%s, %s);" % (json.dumps(h["key"]), json.dumps(h["tag"]),
                                      json.dumps(h["id"]))
        for h in yoso)
    hako += "\nconst __INLINE = " + json.dumps(
        [[k, t, v] for k, t, v in inline], ensure_ascii=False) + ";"
    code = NISE_GAMEN.replace("IDS_HERE", hako).replace("GAME_HERE", js)

    # force=True: 先生の書いた物ではなく、こちらが用意した偽の画面が
    # localStorage などの語に引っかかるため。囲い(sandbox-exec)は外れない。
    try:
        r = coderun.run(code, "javascript", timeout=20, force=True)
    except Exception as e:
        warui.append(f"動かせませんでした: {e}")
        return {"合格": False, "だめな所": warui, "気になる所": kininaru,
                "動き": None, "名前": name}

    # 使い捨て部屋に 何かを作っていないか。
    #
    #   `coderun.run()` は「作った物」を返しているのに ここで捨てていた。
    #   部屋ごと消すので 実害は無いが、**見張りが死んでいた**。
    #   4-① で `mondai_run.py` が「場を変えた」を見て 10件見つけたのと 同じ型。
    #   HTML を1枚 見せるだけなら、部屋に何かが残るのは おかしい。
    tsukutta = [x for x in (r.get("作った物") or []) if not x.startswith(".")]
    if tsukutta:
        kininaru.append("部屋に物を作りました: " + "、".join(tsukutta[:5]))

    ugoki = None
    for line in (r["出力"] or "").splitlines():
        if line.startswith("KENSA "):
            try:
                ugoki = json.loads(line[6:])
            except Exception:
                pass
    if ugoki is None:
        warui.append("読み込みで止まりました: " + _naze(r))
        return {"合格": False, "だめな所": warui, "気になる所": kininaru,
                "動き": None, "名前": name}

    if ugoki.get("例外"):
        warui.append("読み込みで例外: " + str(ugoki["例外"])[:150])
    for o in ugoki.get("押した", []):
        if o.get("結果") == "例外":
            warui.append(f"「{o['どれ']}」を押すと例外: {str(o.get('中身'))[:80]}")
    # 「動く物」を頼んだなら、押せない・押しても変わらないのは 出来ていない。
    # ここを 気になる所 止まりにしていたので、動かないページが 通っていた
    kiki = warui if ugoku else kininaru
    # canvas を置いたのに 一度も描いていないなら、盤は空のまま。
    # `getContext` が 何でも黙って返していたので、
    # 1マスも描かないテトリスが 通っていた（実測・2026-08-30）
    if ugoki.get("canvasあり") and ugoki.get("描いた", 0) == 0:
        kiki.append("canvas に 一度も描いていません（盤が空のまま）")
    if ugoki.get("押せる数", 0) == 0:
        kiki.append("押せる所がひとつもありません（見るだけのページ？）")
    elif not ugoki.get("変わった"):
        kiki.append("押しても画面が変わりませんでした")

    return {"合格": not warui, "だめな所": warui, "気になる所": kininaru,
            "動き": ugoki, "名前": name}


def report(k):
    out = ["【%s】 %s" % (k["名前"], "通った" if k["合格"] else "通らなかった")]
    for w in k["だめな所"]:
        out.append("  ✗ " + w)
    for w in k["気になる所"]:
        out.append("  ・" + w)
    u = k.get("動き")
    if u and "押せる数" in u:
        out.append("  押せる所 %d 個 ／ 押して画面が変わった: %s"
                   % (u["押せる数"], "はい" if u.get("変わった") else "いいえ"))
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    src = open(sys.argv[1], encoding="utf-8").read()
    print(report(kensa(src, sys.argv[1])))
