#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
background.py -- 裏でずっと辞書を辿り続ける係

  やること:
    1. 調べた語のまわりを、辞書を辿って広げていく（「かな文字って何？」の連鎖）
    2. 辿った結果を bg_web.json に貯める。次からの「関連」が速くなる
    3. 札になりそうな語を見つけたら、候補として置いておく

  【大事な決めごと】
    候補は、勝手に札にしない。

    辞書ぜんぶを一気に札にしたら、421枚のうち半分以上が
    「宇宙飛行士 → 画像」「醤油 → PDF」のような間違いだった。
    だから裏の係は「これはどうですか」と置くところまで。
    採るかどうかは本人が /candidates で決める。

  動かし方:
    /bg start   はじめる（裏で動き続ける）
    /bg stop    とめる
    /bg status  いまどこまで進んだか
"""
import os, sys, json, time, signal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STATE = os.path.join(HERE, "bg_state.json")
QUEUE = os.path.join(HERE, "bg_queue.json")
WEB   = os.path.join(HERE, "bg_web.json")
CAND  = os.path.join(HERE, "card_candidates.json")
STOP  = os.path.join(HERE, "bg_stop")
LOG   = os.path.join(HERE, "bg.log")

# 1語ごとに少し休む。裏の係が前を邪魔しないように
REST = 0.03
# 貯めすぎない上限
MAX_WEB, MAX_CAND = 40000, 2000


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def status():
    st = _read(STATE, {})
    if not st:
        return "裏の係は、まだ一度も動いていません。"
    alive = False
    pid = st.get("pid")
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            alive = False
    age = time.time() - st.get("更新", 0)
    web = _read(WEB, {})
    cand = _read(CAND, {})
    q = _read(QUEUE, [])
    if alive and age > 120:
        head = (f"生きてはいるが、{age/60:.0f} 分ものあいだ合図がありません。"
                f"引っかかっている可能性があります（/bg stop で止められます）")
    elif alive:
        head = f"動いています（最後の合図は {age:.0f} 秒前）"
    elif st.get("終わった"):
        head = f"とまっています（{st['終わった']}・{age/60:.0f} 分前）"
    else:
        head = "とまっています（理由は分かりません。落ちた可能性があります）"
    lines = [
        f"  うごき      : {head}",
        f"  調べた語    : {st.get('調べた', 0):,} 語",
        f"  待っている語: {len(q):,} 語",
        f"  つながり    : {len(web):,} 語ぶん（bg_web.json）",
        f"  札の候補    : {len(cand)} 件  ← /candidates で見られます",
    ]
    if st.get("いま"):
        lines.append(f"  いま        : 「{st['いま']}」")
    return "\n".join(lines)


def seed_from(words):
    """調べたい語を、待ち行列の先頭に足す"""
    q = _read(QUEUE, [])
    have = set(q)
    add = [w for w in words if w and w not in have]
    _write(QUEUE, add + q)
    return len(add)


def stop():
    open(STOP, "w").close()
    st = _read(STATE, {})
    pid = st.get("pid")
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    return "とめました。"


def start():
    """裏の係を、別のプロセスとして立ち上げる"""
    st = _read(STATE, {})
    pid = st.get("pid")
    if pid:
        try:
            os.kill(pid, 0)
            return "もう動いています。（/bg status で様子が見られます）"
        except OSError:
            pass
    if os.path.exists(STOP):
        os.remove(STOP)
    import subprocess
    with open(LOG, "a") as lg:
        p = subprocess.Popen(
            ["nice", "-n", "10", sys.executable, __file__, "--run"],
            stdout=lg, stderr=lg, stdin=subprocess.DEVNULL,
            start_new_session=True, cwd=HERE)
    time.sleep(0.6)
    return f"裏で動きはじめました（pid {p.pid}）。/bg status で様子が見られます。"


# ============================================================
# ここからが、裏で回り続ける本体
# ============================================================
def run():
    import lookup, kernel, grow

    d = lookup.Dict()
    kernel.load_learned()
    base = {k: v for k, v in kernel.SEED.items()
            if v[0] in ("種類", "場所") and len(k) >= 2}

    all_words = list(d.idx)          # 辞書に載っている語ぜんぶ
    q = _read(QUEUE, [])
    if not q:
        # 何も指定が無ければ、種火の語そのものから辿りはじめる
        q = [k for k in kernel.SEED if len(k) >= 2]
    web  = _read(WEB, {})
    cand = _read(CAND, {})
    done = set(web)
    n = _read(STATE, {}).get("調べた", 0)
    skipped = 0

    def save(now=""):
        _write(STATE, {"pid": os.getpid(), "更新": time.time(),
                       "調べた": n, "いま": now})   # 「終わった」は消える
        _write(QUEUE, q[:20000])
        _write(WEB, web)
        _write(CAND, cand)

    save()
    last = time.time()
    while True:
        if os.path.exists(STOP):
            break
        if not q:
            # 辿る先を使い切ったら、辞書のまだ見ていない語から補充する。
            # ここが無いと 4,804 語で自然に止まってしまい、
            # 「ずっと動き続ける」はずが静かに終わっていた
            fresh = [w for w in all_words if w not in done][:5000]
            print(f"[{time.strftime('%H:%M:%S')}] 補充 {len(fresh)} 語"
                  f"（見た {len(done):,} / 見送り {skipped:,}）")
            if not fresh:
                _write(STATE, {"更新": time.time(), "調べた": n,
                               "いま": "", "終わった": "辞書を全部見ました"})
                break
            q.extend(fresh)
            print(f"[{time.strftime('%H:%M:%S')}] 辞書から {len(fresh)} 語 補充")
        w = q.pop(0)
        # 見送る語も「見た」に入れる。入れていなかったので、
        # 短すぎる語・長すぎる語が補充のたびに何度でも戻ってきて、
        # 1時間ずっとCPUを100%使って空回りしていた
        if w in done or not (2 <= len(w) <= 20):
            done.add(w)
            skipped += 1
            if skipped % 500 == 0:
                save(w)              # 見送り続きでも、生きている合図は出す
                time.sleep(REST)     # 休みを挟む。全力で回らせない
            continue
        done.add(w)
        try:
            body = d.look(w)
            rel = d.links(w, 8) if body else []
        except Exception:
            body, rel = None, []
        n += 1
        if body:
            if len(web) < MAX_WEB:
                web[w] = rel[:8]
            # まだ見ていない語を、後ろに足す（これが「永遠に辿る」の中身）
            for r in rel[:6]:
                if r not in done and len(q) < MAX_WEB:
                    q.append(r)
            # 札になりそうか見るだけ。採用はしない
            if len(cand) < MAX_CAND and w not in kernel.SEED and w not in grow.load():
                first = next((l.strip() for l in body.split("\n") if l.strip()), "")
                r = grow.from_definition(w, first, base)
                if r and len(first) <= 40:
                    slot, val, why = r
                    # ── 種類の札は、pc_kind に一度 相談してから ──
                    # 説明文に「資料」の2字が入っているだけで
                    #   醤油 → PDF（根拠「資料」）
                    #   メモリ → テキスト（根拠「メモ」）
                    # のような札が候補に並んでいた。字面の一致でしかない。
                    # pc_kind は記事の出方で見るので、こういう語には黙る。
                    # 黙られた語は候補にしない。
                    if slot == "種類":
                        try:
                            import pc_kind
                            if pc_kind.ready():
                                g = pc_kind.guess(w)
                                if not g or g[0] is None or g[0] != val:
                                    skipped += 1
                                    continue
                        except Exception:
                            pass
                    cand[w] = {"枠": slot, "値": val, "根拠": why,
                               "説明": first[:60]}
        if time.time() - last > 5:
            save(w)
            last = time.time()
        time.sleep(REST)

    save()
    st = _read(STATE, {})
    st.pop("pid", None)
    st.setdefault("終わった", "とめられました")
    st["更新"] = time.time()
    _write(STATE, st)
    print(f"[{time.strftime('%H:%M:%S')}] おわり： {n} 語（{st['終わった']}）")


if __name__ == "__main__":
    if "--run" in sys.argv:
        run()
    elif "--status" in sys.argv:
        print(status())
    else:
        print(__doc__)
