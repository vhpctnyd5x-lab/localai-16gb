#!/usr/bin/env python3
"""事前学習とスキル API の、ネット・本番モデルを使わない自己試験。"""
import json
import io
import fcntl
import importlib.util
import os
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kernel"))


def check(value, message):
    if not value:
        raise AssertionError(message)


with tempfile.TemporaryDirectory(prefix="tameshi_gakushuu_") as temporary:
    base = Path(temporary)
    os.environ["KERNEL_GAKUSHUU_DIR"] = str(base / "gakushuu")
    os.environ["KERNEL_SKILLS_DIR"] = str(base / "skills")
    os.environ["KERNEL_KIROKU_DIR"] = str(base / "kiroku")
    os.environ["KERNEL_TRASH_DIR"] = str(base / "trash")
    os.environ["KERNEL_CHATS_DB"] = str(base / "chats.sqlite3")
    import gakushuu
    import settings

    settings.PATH = str(base / "settings.json")
    cfg = settings.load()
    check(gakushuu.DEFAULT["充電中だけ"] is False
          and cfg["事前学習"]["充電中だけ"] is False, "充電中だけの既定はオフ")
    cfg["事前学習"] = gakushuu.validate(cfg["事前学習"], {"入": True, "充電中だけ": False})
    settings.save(cfg)

    class FakeWiki:
        calls = 0
        article_calls = []
        topics = []

        @classmethod
        def ask(cls, title, chars=5000):
            cls.calls += 1
            cls.topics.append(title)
            return {"題": "試験記事", "本文": "試験記事の本文。調べたい言葉が入る。", "url": "https://example.invalid/wiki/test",
                    "ほかの候補": ["候補題一", "候補題二", "候補題三", "候補題四", "候補題五", "候補題六",
                                   "A(説明)", "一覧の項目", "曖昧さ回避", "1999年の出来事", "あ"]}

        @classmethod
        def article(cls, title, chars=20000):
            cls.article_calls.append((title, chars))
            return {"題": title, "本文": "試験記事の本文全文。" + "本文の続き。" * 100}

    check(gakushuu.learn_once(cfg, wiki_module=FakeWiki), "記事を追加")
    check(FakeWiki.topics[0] in gakushuu.LEARN_SEEDS and FakeWiki.topics[0] != "あ", "最初の題は学習種から選ぶ")
    queued = gakushuu._state()["次の題"]
    check([x["題"] for x in queued] == ["候補題一", "候補題二", "候補題三", "候補題四", "候補題五"],
          "リンク候補は条件で絞って5題まで")
    check(all(x["深さ"] == 1 for x in queued), "リンク題に深さを記録")
    with sqlite3.connect(gakushuu.folder() / "chishiki.sqlite3") as db:
        check(db.execute("SELECT count(*) FROM chishiki WHERE chishiki MATCH '試験記事'").fetchone()[0] == 1, "FTS5 検索")
        check(db.execute("SELECT 1 FROM tsunagari WHERE moto='試験記事' AND saki='候補題一' AND shurui='リンク'").fetchone(),
              "記事保存時にリンク枝")
    check(FakeWiki.article_calls[0][1] == 8000, "本文は8,000字上限で取りに行く")
    check(gakushuu.learn_once(cfg, wiki_module=FakeWiki), "新記事と交互に既存記事を取り直す")
    check(not gakushuu.learn_once(cfg, wiki_module=FakeWiki), "同じ記事を重ねて追加しない")
    with sqlite3.connect(gakushuu.folder() / "chishiki.sqlite3") as db:
        full = db.execute("SELECT text FROM chishiki WHERE title='試験記事'").fetchone()[0]
        check("本文の続き" in full and len(full) > 500, "要約でなく本文を保存")
    check(gakushuu.overview(cfg)["数"]["記事"] == 1, "記事数")
    branch_dir = base / "branch-test"
    with mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": str(branch_dir)}):
        with gakushuu._db() as db:
            db.executemany("INSERT INTO chishiki(title,text,source,url,added) VALUES(?,?,?,?,?)", [
                ("関係記事", "試験記事を本文で参照する。", "Wikipedia", "", "今日"),
                ("試験記事", "独立した本文。", "Wikipedia", "", "今日")])
        rebuilt = gakushuu.rebuild_relationships()
        with gakushuu._db() as db:
            check(db.execute("SELECT 1 FROM tsunagari WHERE moto='関係記事' AND saki='試験記事' AND shurui='本文'").fetchone(),
                  "既存記事の本文枝を作り直す")
        check(gakushuu.rebuild_relationships() == rebuilt, "枝の再構築は重複しない")

    class DepthWiki:
        calls = 0
        topics = []

        @classmethod
        def ask(cls, title, chars=5000):
            cls.calls += 1
            cls.topics.append(title)
            links = ["二段目候補"] if cls.calls == 2 else ["候補題一", "候補題二", "候補題三", "候補題四", "候補題五"]
            return {"題": f"深さ記事{cls.calls}", "本文": "深さ確認の記事本文。", "ほかの候補": links}

    gakushuu._write(gakushuu.folder() / "state.json", {"版": gakushuu.STATE_VERSION, "次の題": []})
    saved_depth = gakushuu.MAX_DEPTH
    gakushuu.MAX_DEPTH = 1   # 1段の時の決まり（3段の時は下で確かめる）
    check(gakushuu.learn_once(cfg, wiki_module=DepthWiki), "種記事からリンクを追加")
    check(gakushuu.learn_once(cfg, wiki_module=DepthWiki), "深さ1の記事を学習")
    check("二段目候補" not in [x["題"] for x in gakushuu._state()["次の題"]], "深さ1からリンクを広げない")
    gakushuu.MAX_DEPTH = saved_depth
    check(gakushuu.MAX_DEPTH == 3, "既定は3段までたどる")
    # 9/30: 題が尽きたら、覚えた記事を引き直してリンクを広げる（版2の state から入れ直す）。
    v2 = {"版": 2, "見た題": ["コンピュータ", "広げる記事"], "次の題": [], "見た記録": ["x.jsonl:1"]}
    upgraded = gakushuu._version_state(v2)
    check(upgraded["広げる"] == [{"題": "広げる記事", "深さ": 1}] and upgraded["見た記録"] == ["x.jsonl:1"], "版2から版3へ")
    class GrowWiki:
        @classmethod
        def ask(cls, title, chars=5000):
            return {"題": title, "本文": "本文", "ほかの候補": ["広げた題一", "広げた題二", "(括弧)"]}
    gakushuu._write(gakushuu.folder() / "state.json", {**upgraded, "見た題": list(gakushuu.LEARN_SEEDS) + upgraded["見た題"]})
    check(not gakushuu.learn_once(cfg, wiki_module=GrowWiki), "広げる回は記事を足さない")
    grown = gakushuu._state()
    check([x["題"] for x in grown["次の題"]] == ["広げた題一", "広げた題二"] and all(x["深さ"] == 2 for x in grown["次の題"])
          and grown["広げる"] == [], "覚えた記事からリンクを広げる")
    # 10/2: 題もリンクを広げる先も尽きたら、覚えた記事の本文を取り直す（取れない題は読んだことにして先へ）。
    gakushuu._write(gakushuu.folder() / "state.json", {**gakushuu._state(), "次の題": [], "広げる": [], "全文を読んだ題": [],
                                                       "次は本文取り直し": False})
    class RereadWiki:
        calls = []
        @classmethod
        def ask(cls, title, chars=5000):
            raise AssertionError("題が尽きた時は新しい題を探さない: " + title)
        @classmethod
        def article(cls, title, chars=20000):
            cls.calls.append(title)
            return {"題": title, "本文": "取り直した本文。" * 50}
    check(gakushuu.learn_once(cfg, wiki_module=RereadWiki), "題が尽きたら本文を取り直す")
    check(RereadWiki.calls and RereadWiki.calls[0] in gakushuu._state()["全文を読んだ題"], "取り直した題を覚える")
    class NoBodyWiki(RereadWiki):
        @classmethod
        def article(cls, title, chars=20000):
            cls.calls.append(title)
            return None
    before = len(gakushuu._state()["全文を読んだ題"])
    check(not gakushuu.learn_once(cfg, wiki_module=NoBodyWiki), "本文が取れない時は False")
    check(len(gakushuu._state()["全文を読んだ題"]) == before + 1, "取れない題も読んだことにして同じ題に止まらない")
    # 10/2: Wikipedia の exchars は 1,200 字までしか効かない。長く頼む時は全文を取り、手元で切る。
    import wiki
    asked = []
    def fake_get(params):
        asked.append(dict(params))
        return {"query": {"pages": {"1": {"title": "長い記事", "extract": "あ" * 9000}}}}
    with mock.patch.object(wiki, "_get", side_effect=fake_get):
        long_body = wiki.article("長い記事", chars=8000, cache=False)["本文"]
        wiki.article("長い記事", chars=500, cache=False)
    check("exchars" not in asked[0] and len(long_body) == 8000 and asked[1].get("exchars") == 500, "1,200 字より長い本文は全文を取って切る")
    old = {"版": 1, "次の題": [{"題": "ゆめりあ", "深さ": 1}]}
    check(gakushuu._topic(old, set(), False) == gakushuu.LEARN_SEEDS[0], "旧版の次の題を捨てる")
    check(gakushuu._version_state({"版": 1, "見た記録": ["x.jsonl:1"]})["見た記録"] == [], "旧版の見た記録を捨てる")
    plain = [x for x in gakushuu.LEARN_SEEDS if "(" not in x]
    check(gakushuu._topic({"版": gakushuu.STATE_VERSION, "見た題": plain}, set(), False) == "ファイル (コンピュータ)",
          "括弧つきの種も学ぶ")
    check(gakushuu._valid_title("二字") and not gakushuu._valid_title("あ")
          and not gakushuu._valid_title("題 (説明)") and not gakushuu._valid_title("一覧")
          and not gakushuu._valid_title("曖昧さ回避") and not gakushuu._valid_title("2024年の出来事"), "題の除外条件")
    check(not gakushuu._valid_title("コンピュータゲーム") and not gakushuu._valid_title("コンピュータRPG")
          and gakushuu._valid_title("パーソナルコンピュータ"), "遊び・芸能の題を外す")

    low = {**cfg, "事前学習": {**cfg["事前学習"], "上限MB": 0}}
    before = FakeWiki.calls
    check(not gakushuu.learn_once(low, wiki_module=FakeWiki) and FakeWiki.calls == before, "上限で停止")

    original_charging = gakushuu.charging
    gakushuu.charging = lambda: False
    charge_cfg = {**cfg, "事前学習": {**cfg["事前学習"], "充電中だけ": True}}
    check(not gakushuu.learn_once(charge_cfg, wiki_module=FakeWiki) and FakeWiki.calls == before, "非充電で休む")
    gakushuu.charging = original_charging

    busy = gakushuu.folder() / "busy"
    busy.write_text("test", encoding="ascii")
    check(not gakushuu.learn_once(cfg, wiki_module=FakeWiki) and FakeWiki.calls == before, "会話中に休む")
    busy.unlink()

    logdir = base / "kiroku"
    logdir.mkdir()
    (logdir / "slow.jsonl").write_text(
        json.dumps({"段階": "開始", "内容": {"依頼": "遅い頼み"}}, ensure_ascii=False) + "\n"
        + json.dumps({"段階": "結果", "内容": {"ok": True, "ミリ秒": 45000}}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    check(any(r["題"] == "遅い頼み" for r in gakushuu._records()), "遅い記録を読む")
    # 10/2: 置き場を指定しない時は、今の輪の記録（kernel/kiroku）と前の操作記録（Application Support）の両方を読む。
    saved_kiroku = os.environ.pop("KERNEL_KIROKU_DIR")
    try:
        check(gakushuu._record_dirs() == [Path(gakushuu.__file__).resolve().parent / "kiroku", gakushuu.ROOT / "kiroku"],
              "今の輪の記録も読む")
    finally:
        os.environ["KERNEL_KIROKU_DIR"] = saved_kiroku
    nested = logdir / "atama"
    nested.mkdir()
    (nested / "operation.jsonl").write_text(json.dumps({"時": "2026-10-01 12:00:00", "目当て": "現行形式の失敗",
        "履歴": [{"手": "read_file"}], "手": {"手": "打つ", "文字": "試験"}, "秒": 8,
        "つまずき": "失敗", "正しい手": "確認"}, ensure_ascii=False) + "\n", encoding="utf-8")
    current_record = next(r for r in gakushuu._records() if r["題"] == "現行形式の失敗")
    check(current_record["成否"] == "失敗" and "read_file" in current_record["道具"], "入れ子の現行会話記録を振り返る")

    check(gakushuu.DEFAULT["振り返りで外の先生に聞く"] and not gakushuu.DEFAULT["会話の言葉から学ぶ題を選ぶ"], "外の先生への振り返りは既定で入")
    check(gakushuu._topic({"次の題": []}, set(), False) != "会話だけの題", "会話題を既定で使わない")
    check(gakushuu.validate(cfg["事前学習"], {"振り返りで外の先生に聞く": True})["振り返りで外の先生に聞く"], "送信設定")
    (base / "skills" / "容量.md").parent.mkdir(parents=True, exist_ok=True)
    (base / "skills" / "容量.md").write_text(gakushuu._skill_text("容量", "試験", False, "カーネル", "増量"), encoding="utf-8")
    check(gakushuu.used_bytes() >= (base / "skills" / "容量.md").stat().st_size, "提案スキルも容量に算入")
    (base / "skills" / "容量.md").unlink()
    log = gakushuu.folder() / "log.jsonl"
    log.write_bytes(b"x" * (5 * 1024 * 1024))
    gakushuu._log("回した後")
    check(log.stat().st_size < 1024 and log.with_suffix(".jsonl.1").exists(), "log は5MBで回す")
    log.write_text("".join(json.dumps({"文": str(i)}) + "\n" for i in range(30)), encoding="utf-8")
    check([x["中身"] for x in gakushuu.overview(cfg)["活動"]] == [str(i) for i in range(10, 30)], "活動は尻の20件")
    now = gakushuu.time.strftime("%Y-%m-%d %H:%M:%S")
    kinds = ["Wikipedia: 記事A", "本文を取り直し: 記事B（8000字）", "振り返り: 例を確認",
             "先生に聞いた: mock", "振り返り: 例 → 技を提案: 例", "覚え書き: 1件"]
    log.write_text("".join(json.dumps({"時刻": now, "文": item}, ensure_ascii=False) + "\n" for item in kinds), encoding="utf-8")
    daily = gakushuu.overview(cfg)["今日の数"]
    check(daily["読んだ記事"] == 1 and daily["本文を取り直した記事"] == 1
          and daily["振り返り"] == 2 and daily["先生に聞いた"] == 1
          and daily["技の提案"] == 1 and daily["覚え書き"] == 1
          and daily["活用カード"] == 0, "今日の活動数")
    lock_path = gakushuu.folder() / "worker.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gakushuu.run()
        check(not (gakushuu.folder() / "worker.pid").exists(), "二重起動を止める")
        fcntl.flock(lock, fcntl.LOCK_UN)

    record = {"題": "[ファイル] を直す", "文": "失敗した操作", "道具": ["read_file"],
              "成否": "失敗", "識別": "record-1"}
    gakushuu._records = lambda: [record]

    class FakeHTTP:
        def __init__(self, content, interrupt=False):
            self.content = io.BytesIO(content)
            self.interrupt = interrupt
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def read(self, *args):
            return self.content.read(*args)

        def readline(self):
            line = self.content.readline()
            if self.interrupt:
                (gakushuu.folder() / "busy").touch()
            return line

    streams = []
    prompts = []
    def fake_urlopen(req, timeout=None):
        if isinstance(req, str):
            check(req.endswith("/health"), "Qwen3.6 health")
            return FakeHTTP(b'{"status":"ok"}')
        check(req.full_url.endswith("/v1/chat/completions"), "Qwen3.6 chat API")
        payload = json.loads(req.data)
        check(payload["stream"] and payload["max_tokens"] == 300
              and payload["chat_template_kwargs"]["enable_thinking"] is False, "短い streaming・思考なし")
        prompts.append(payload["messages"][0]["content"])
        stream = FakeHTTP(('data: {"choices":[{"delta":{"content":"順に直す"}}]}\n\n'
                           'data: [DONE]\n\n').encode("utf-8"))
        streams.append(stream)
        return stream

    with mock.patch.object(gakushuu.urllib.request, "urlopen", side_effect=fake_urlopen), \
         mock.patch.object(gakushuu, "_local_memories", return_value=[
             {"文": "本人は説明を短く日本語で受け取りたい", "種類": "好み"},
             {"文": "本人のAPI keyはabc123456789秘密", "種類": "事実"},
             {"文": "本人は説明を短く日本語で受け取りたい", "種類": "好み"}]):
        check(gakushuu.reflect_once(cfg, ask=lambda *a, **k: (_ for _ in ()).throw(AssertionError("外へ送った")),
                                    network=True), "先生オフでもQwen3.6だけで提案")
    check("失敗した操作" in prompts[0] and streams[0].closed, "Qwen3.6には元の記録を見せて接続を閉じる")
    proposed = [s for s in gakushuu.skills() if s["made_by"] == "カーネル"]
    check(len(proposed) == 1 and proposed[0]["on"] is False
          and proposed[0]["body"].endswith("出どころ: Qwen3.6"), "Qwen3.6単独の提案はオフ")
    check("振り返り: ファイルを直す → 技を提案:" in (gakushuu.folder() / "log.jsonl").read_text(),
          "提案の記録")
    saved_memories = gakushuu.memories()
    check(saved_memories["数"] == 1 and saved_memories["一覧"][0]["文"] == "本人は説明を短く日本語で受け取りたい",
          "覚え書き抽出・秘密除外・重複抑止")
    check(gakushuu.add_memories([{"文": "本人は説明を短く日本語で受け取りたい", "種類": "好み"}], "again") == 0,
          "同じ文を追加しない")
    memory_id = saved_memories["一覧"][0]["id"]
    check(gakushuu.delete_memory(memory_id) and gakushuu.memories()["数"] == 0, "本人が覚え書きを削除")
    check(gakushuu.add_memories([{"文": "本人は説明を短く日本語で受け取りたい", "種類": "好み"}], "again") == 0,
          "削除済み覚え書きは再作成しない")
    check(not gakushuu.reflect_once(cfg), "10分の間隔")
    extraction_payload = {"choices": [{"message": {"content": json.dumps({"覚え書き": [
        {"文": "本人は道具の説明を短く受け取りたい", "種類": "好み"}]}, ensure_ascii=False)}}]}
    extraction_requests = []
    def extraction_response(req, timeout=None):
        extraction_requests.append(json.loads(req.data))
        return io.BytesIO(json.dumps(extraction_payload, ensure_ascii=False).encode())
    with mock.patch.object(gakushuu.urllib.request, "urlopen", side_effect=extraction_response):
        extracted = gakushuu._local_memories({"文": "私は短い説明が好きです"})
    check(extracted[0]["種類"] == "好み" and extraction_requests[0]["stream"] is False
          and extraction_requests[0]["chat_template_kwargs"]["enable_thinking"] is False
          and "JSONだけ" in extraction_requests[0]["messages"][0]["content"], "頭脳JSON抽出は思考なし")
    # 10/1: --reasoning-format none の本物の返事は空の <think></think> が付き、```json で囲むこともある
    wrapped = "<think>\n\n</think>\n\n```json\n" + json.dumps({"覚え書き": [{"文": "本人は音声入力でアプリを使う", "種類": "事実"}]}, ensure_ascii=False) + "\n```"
    with mock.patch.object(gakushuu.urllib.request, "urlopen",
                           side_effect=lambda req, timeout=None: io.BytesIO(json.dumps({"choices": [{"message": {"content": wrapped}}]}, ensure_ascii=False).encode())):
        check(gakushuu._local_memories({"文": "音声入力で話しています"})[0]["文"] == "本人は音声入力でアプリを使う", "思考の札・囲みつきの返事から覚え書きを取り出す")
    state = gakushuu._state()
    state["最後の提案時刻"] -= 601
    state["最後の振り返り試行時刻"] = 0
    gakushuu._write(gakushuu.folder() / "state.json", state)
    record["識別"] = "record-2"
    record["題"] = "[ファイル] を読み直す"   # 9/30: 同じ頼みは1回だけ振り返るので、頼みも変える
    sent = []
    def teacher(question, config, timeout=60):
        sent.append((question, config["先生"]))
        return {"答え": "順に確かめて直す。", "error": None}
    cfg["事前学習"]["振り返りで外の先生に聞く"] = True
    cfg["先生"] = ["local:main", "groq:openai/gpt-oss-120b"]
    with mock.patch.object(gakushuu, "_local_reflect", return_value=("秘密 /tmp/private.txt を読む", False)), \
         mock.patch.object(gakushuu, "_local_memories", return_value=[]):
        check(gakushuu.reflect_once(cfg, ask=teacher, network=True), "先生がQwen3.6の提案を直す")
    check("[ファイル]" in sent[0][0] and "/tmp/private.txt" not in sent[0][0]
          and "Qwen3.6の提案:" in sent[0][0] and "read_file" in sent[0][0]
          and sent[0][1] == ["groq:openai/gpt-oss-120b"], "先生に伏せた文とQwen3.6提案を渡す")
    proposed = [s for s in gakushuu.skills() if s["made_by"] == "カーネル"]
    check(len(proposed) == 2 and any(s["body"].endswith("出どころ: Qwen3.6＋先生") for s in proposed),
          "先生の答えを採用")

    record["識別"] = "record-3"
    record["題"] = "[ファイル] を並べる"   # 9/30: 同じ頼みは1回だけ振り返るので、頼みも変える
    state = gakushuu._state()
    state["最後の提案時刻"] -= 601
    state["最後の振り返り試行時刻"] = 0
    gakushuu._write(gakushuu.folder() / "state.json", state)
    cfg["事前学習"]["振り返りで外の先生に聞く"] = True
    interrupted = []
    def busy_urlopen(req, timeout=None):
        if isinstance(req, str):
            return FakeHTTP(b'{"status":"ok"}')
        stream = FakeHTTP('data: {"choices":[{"delta":{"content":"途中"}}]}\n'.encode("utf-8"),
                          interrupt=True)
        interrupted.append(stream)
        return stream
    with mock.patch.object(gakushuu.urllib.request, "urlopen", side_effect=busy_urlopen):
        check(not gakushuu.reflect_once(cfg, ask=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("busy中に先生へ送った")), network=True), "busyでQwen3.6を中断")
    check(interrupted[0].closed and "record-3" not in gakushuu._state().get("見た記録", []),
          "busyで接続を閉じ、記録を使わない")
    (gakushuu.folder() / "busy").unlink()

    cfg["事前学習"]["振り返りで外の先生に聞く"] = False
    state = gakushuu._state()
    state["最後の振り返り試行時刻"] = 0
    gakushuu._write(gakushuu.folder() / "state.json", state)
    with mock.patch.object(gakushuu, "_local_reflect", return_value=(None, False)):
        check(not gakushuu.reflect_once(cfg) and not gakushuu.reflect_once(cfg), "手元の頭脳が未応答なら間隔を置く")
    log_text = (gakushuu.folder() / "log.jsonl").read_text(encoding="utf-8")
    check(log_text.count("振り返り: 手元Qwen3.6を待っています") == 1
          and "record-3" not in gakushuu._state().get("見た記録", []), "待機は1回だけ・記録を使わない")
    state = gakushuu._state()
    state["最後の振り返り試行時刻"] -= 601
    gakushuu._write(gakushuu.folder() / "state.json", state)
    with mock.patch.object(gakushuu, "_local_reflect", return_value=("順に直す", False)):
        check(not gakushuu.reflect_once(cfg), "同じ本文は重ねない")
    check("record-3" in gakushuu._state().get("見た記録", [])
          and len([s for s in gakushuu.skills() if s["made_by"] == "カーネル"]) == 2,
          "重複した記録は処理済みにする")

    # 活用カード: 材料の順位、根拠の足切り、JSON囲み、上限、不要の抑止、匿名化、busy を全て偽物で確認。
    failed = {"題": "ファイルを保存する", "文": "保存でつまずいた", "道具": ["write_file"],
              "成否": "失敗", "識別": "card-failed"}
    slow = {"題": "ファイルを一覧する", "文": "時間がかかった", "道具": ["list_files"],
            "成否": "遅い", "識別": "card-slow"}
    gakushuu._records = lambda: [slow, failed]
    card_obj = {"題": "保存前の確認", "目的": "誤保存を減らす", "適用条件": "保存先が曖昧な時",
                "根拠": [{"記事": "ファイルシステム", "事実": "ファイルは名前と保存場所を持つ。", "考え": "場所を先に確かめる。"}],
                "手順": ["保存先を確認する", "名前を見直す", "保存した場所を開く"],
                "確かめ方": "保存先に名前があるか見る", "まだ分からない点": "上書き時の動作"}
    model_calls = []
    def fake_card_model(record, evidence):
        model_calls.append((record, evidence))
        return "<think>除去する</think>```json\n" + json.dumps(card_obj, ensure_ascii=False) + "\n```", False
    cfg["事前学習"]["振り返りで外の先生に聞く"] = False
    evidence = [{"記事": "ファイルシステム", "一文": "ファイルは名前と保存場所を持つ。"},
                {"記事": "ディレクトリ", "一文": "ディレクトリはファイルを分類する。"}]
    check(not gakushuu.make_teian_once(cfg, local=fake_card_model, search=lambda request, terms: []),
          "関連根拠が無い時はカードを作らない")
    (gakushuu.folder() / "state.json").unlink(missing_ok=True)  # 足切りは試行間隔を消費しない運用を保証
    check(gakushuu.make_teian_once(cfg, local=fake_card_model,
                                   search=lambda request, terms: evidence), "関連知識からカード作成")
    check(model_calls[0][0]["識別"] == "card-failed", "つまずいた用件を遅い用件より先に選ぶ")
    stored = gakushuu.teian_list()[0]
    check(stored["中身"]["題"] == card_obj["題"] and stored["根拠の記事"] == "ファイルシステム",
          "think と JSON 囲みを除いてカード保存")
    gakushuu._records = lambda: [failed]
    (gakushuu.folder() / "state.json").unlink(missing_ok=True)
    check(not gakushuu.make_teian_once(cfg, local=lambda *_: ("{}", False),
                                       search=lambda request, terms: evidence), "作成済み用件は再提示しない")
    gakushuu.teian_action({"id": stored["id"], "状態": "試す"})
    favored = {"題": failed["題"], "文": "同じ型", "道具": ["write_file"], "成否": "失敗", "識別": "card-favored"}
    other = {"題": "別の題", "文": "別件", "道具": ["write_file"], "成否": "失敗", "識別": "card-other"}
    gakushuu._records = lambda: [other, favored]
    (gakushuu.folder() / "state.json").unlink(missing_ok=True)
    selected_requests = []
    check(not gakushuu.make_teian_once(cfg, local=lambda *_: ("{}", False),
        search=lambda request, terms: (selected_requests.append(request),
            [{"記事": "新しい記事", "一文": "保存先を確認する。"}] if request == failed["題"] else [])[1]),
          "試すの優先候補を調べる")
    check(selected_requests == [failed["題"]], "試すが多い用件の型を少し優先")
    gakushuu._records = lambda: [failed]
    (gakushuu.folder() / "state.json").unlink(missing_ok=True)
    check(gakushuu.teian_action({"id": stored["id"], "状態": "不要", "不要の理由": "もうできる"})["ok"],
          "不要と理由を保存")
    (gakushuu.folder() / "state.json").unlink(missing_ok=True)
    check(not gakushuu.make_teian_once(cfg, local=fake_card_model,
                                       search=lambda request, terms: evidence), "不要な用件を再提示しない")
    gakushuu._records = lambda: [dict(failed, 識別="same-request-new-record")]
    (gakushuu.folder() / "state.json").unlink(missing_ok=True)
    check(not gakushuu.make_teian_once(cfg, local=fake_card_model,
                                       search=lambda request, terms: evidence), "不要にした用件・記事の組を再提示しない")

    card_obj["目的"] = "秘密の名前さんの保存説明"
    teacher_record = {"題": "秘密の名前さんの保存手順", "文": "保存先に迷った", "道具": ["write_file"],
                      "成否": "失敗", "識別": "teacher-card"}
    gakushuu._records = lambda: [teacher_record]
    (gakushuu.folder() / "state.json").unlink(missing_ok=True)
    teacher_cfg = {**cfg, "先生": ["groq:先生"], "先生を使う": True,
                   "事前学習": {**cfg["事前学習"], "振り返りで外の先生に聞く": True}}
    teacher_questions = []
    def fake_teacher(question, teacher_settings, timeout=None):
        teacher_questions.append((question, teacher_settings))
        return {"答え": "根拠に合っています。危険な操作はありません。"}
    check(gakushuu.make_teian_once(teacher_cfg, local=fake_card_model,
                                   search=lambda request, terms: evidence, ask=fake_teacher), "先生確認付きカード")
    question, teacher_settings = teacher_questions[0]
    check("対象A" in question and "秘密の名前さん" not in question and teacher_settings["先生の深さ"] == "high",
          "先生への文は仮名・high")
    check("先生の確かめ" in gakushuu.teian_list()[0]["中身"], "先生の確認をカードへ保存")
    teian_payloads = []
    def interrupted_card_http(req, timeout=None):
        payload = json.loads(req.data)
        teian_payloads.append(payload)
        return FakeHTTP('data: {"choices":[{"delta":{"content":"途中"}}]}\n'.encode(), interrupt=True)
    with mock.patch.object(gakushuu.urllib.request, "urlopen", side_effect=interrupted_card_http):
        answer, stopped = gakushuu._local_teian(teacher_record, evidence)
    check(stopped and answer is None and (gakushuu.folder() / "busy").exists(), "生成中に busy なら直ちに破棄")
    check(teian_payloads[0]["stream"] and teian_payloads[0]["max_tokens"] == 600
          and teian_payloads[0]["chat_template_kwargs"]["enable_thinking"] is False,
          "活用カードは600トークン・思考なし")
    (gakushuu.folder() / "busy").unlink(missing_ok=True)
    (gakushuu.folder() / "busy").touch()
    (gakushuu.folder() / "state.json").unlink(missing_ok=True)
    check(not gakushuu.make_teian_once(cfg, local=lambda *_: (_ for _ in ()).throw(AssertionError("busy中に呼ばれた")),
                                       search=lambda *_: evidence), "busy ならモデルを呼ばず停止")
    (gakushuu.folder() / "busy").unlink(missing_ok=True)
    gakushuu._records = lambda: [dict(teacher_record, 題="別の保存手順", 識別="card-third")]
    (gakushuu.folder() / "state.json").unlink(missing_ok=True)
    check(gakushuu.make_teian_once(cfg, local=fake_card_model, search=lambda *_: evidence), "3枚目まで作成")
    with gakushuu._teian_db() as db:
        db.execute("INSERT INTO teian(題,中身,根拠の記事,用件の識別,状態,作った日時) VALUES(?,?,?,?,?,?)",
                   ("4枚目", json.dumps(card_obj), "記事", "fourth", "提案中", gakushuu.time.strftime("%Y-%m-%d %H:%M:%S")))
    gakushuu._records = lambda: [dict(teacher_record, 識別="card-fourth")]
    (gakushuu.folder() / "state.json").unlink(missing_ok=True)
    check(not gakushuu.make_teian_once(cfg, local=fake_card_model, search=lambda *_: evidence), "1日3枚の上限")

    spec = importlib.util.spec_from_file_location("kernel_server_test", ROOT / "kernel" / "server.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    settings_path = Path(settings.PATH)
    saved_settings = settings_path.read_bytes() if settings_path.exists() else None
    teacher_cfg = {**cfg, "先生": ["local:main", "groq:openai/gpt-oss-120b"], "先生を使う": True,
                   "事前学習": {**cfg["事前学習"], "振り返りで外の先生に聞く": False}}
    try:
        settings_path.write_text(json.dumps({"先生": teacher_cfg["先生"], "先生を使う": True,
                                             "事前学習": {}}, ensure_ascii=False), encoding="utf-8")
        check(server._gakushuu_teacher_default(teacher_cfg)["事前学習"]["振り返りで外の先生に聞く"],
              "保存設定にない場合は外部先生ありで既定オン")
        settings_path.write_text(json.dumps({"事前学習": {"振り返りで外の先生に聞く": False}}), encoding="utf-8")
        teacher_cfg["事前学習"]["振り返りで外の先生に聞く"] = False
        check(not server._gakushuu_teacher_default(teacher_cfg)["事前学習"]["振り返りで外の先生に聞く"],
              "保存済みの明示オフは保持")
    finally:
        if saved_settings is None:
            settings_path.unlink(missing_ok=True)
        else:
            settings_path.write_bytes(saved_settings)
    server.CTX["設定"] = cfg
    server._IMA["pid"] = 12345
    server._TSUKATTA[0] = 0
    with mock.patch.object(server, "_temoto_shimau") as shut:
        server._temoto_tatamu_nara()
        check(not shut.called, "事前学習中は手元モデルを畳まない")
        cfg["事前学習"]["入"] = False
        server._temoto_tatamu_nara()
        check(shut.call_count == 1, "切にした後は従来どおり畳む")
    server._IMA["pid"] = None
    cfg["事前学習"]["入"] = True
    original_popen = server.subprocess.Popen

    class FakeProcess:
        stopped = False

        def poll(self):
            return 0 if self.stopped else None

        def terminate(self):
            self.stopped = True

        def wait(self, timeout=None):
            return 0

    fake_process = FakeProcess()
    server.subprocess.Popen = lambda *args, **kwargs: fake_process
    try:
        orphan = gakushuu.folder() / "worker.pid"
        orphan.write_text("987654", encoding="ascii")
        signals = []
        def fake_kill(pid, sig):
            signals.append((pid, sig))
            if sig == 0:
                raise ProcessLookupError()
        with mock.patch.object(server.subprocess, "run", return_value=type("Result", (), {"stdout": str(ROOT / "kernel" / "gakushuu.py")})()), mock.patch.object(server.os, "kill", side_effect=fake_kill):
            server._gakushuu_process(True)
        check(any(sig == server.signal.SIGTERM for _, sig in signals), "孤児の学び手を停止")
        orphan.unlink()
        check(server._GAKUSHUU_PROCESS is fake_process, "学習 process 起動")
        server._gakushuu_process(False)
        check(server._GAKUSHUU_PROCESS is None and fake_process.stopped, "学習 process 停止")
    finally:
        server.subprocess.Popen = original_popen

    httpd = server.Server(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"

    def request(path, payload=None, token=True):
        headers = {"Origin": url}
        if token:
            headers["X-Token"] = server.TOKEN
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url + path, data=data, headers=headers,
                                     method="GET" if payload is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    try:
        code, _ = request("/skills", token=False)
        check(code == 403, "GET の token")
        code, _ = request("/skills", {"動き": "保存", "name": "../bad", "description": "bad", "body": "bad"})
        check(code == 400, "名前の検査")
        code, result = request("/skills", {"動き": "保存", "name": "私の技", "description": "手順", "body": "一歩ずつ", "on": True})
        check(code == 200 and any(s["name"] == "私の技" for s in result["スキル"]), "保存")
        code, result = request("/skills", {"動き": "切替", "name": "私の技", "on": False})
        check(code == 200 and next(s for s in result["スキル"] if s["name"] == "私の技")["on"] is False, "切替")
        code, result = request("/skills", {"動き": "ゴミ箱", "name": "私の技"})
        check(code == 200 and (base / "trash" / "私の技.md").exists(), "ゴミ箱")
        code, result = request("/gakushuu")
        check(code == 200 and result["数"]["記事"] == 3, "事前学習 GET")
        code, result = request("/gakushuu/teian")
        check(code == 200 and len(result["提案"]) >= 2, "活用カード GET")
        proposal_id = result["提案"][0]["id"]
        code, result = request("/gakushuu/teian", {"id": proposal_id, "状態": "後で"})
        check(code == 200 and next(x for x in result["提案"] if x["id"] == proposal_id)["状態"] == "後で",
              "活用カード POST")
        # 9/30: 実機のモデル状態に左右されないよう、「何も載っていない」ことにする。
        with mock.patch.object(server, "_temoto_okosu", return_value="すでに動いています") as wake, \
             mock.patch.object(server, "_gakushuu_process"), \
             mock.patch.object(server, "_notteru", return_value=False), \
             mock.patch.dict(server._IMA, {"key": None, "pid": None}):
            code, result = request("/gakushuu", {"入": True})
            check(code == 200 and wake.call_count == 1, "事前学習オンで頭脳を起こす")
        code, result = request("/gakushuu", {"入": False, "上限MB": 4})
        check(code == 200 and result["入"] is False and settings.load()["事前学習"]["上限MB"] == 4,
              "事前学習 POST と保存")
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=3)

    # 10/2 本人: 試した後も採用できる。採用したカードは技（スキル）として残り、次から頭脳が使える。
    with gakushuu._teian_db() as db:
        adopt_id = db.execute("INSERT INTO teian(題,中身,根拠の記事,用件の識別,用件の題,作った日時) VALUES(?,?,?,?,?,?)",
                              ("保存先を確かめる技", json.dumps({"目的": "保存の失敗を防ぐ", "適用条件": "保存する時", "手順": ["場所を確かめる", "保存する"],
                                                              "確かめ方": "read で確かめる", "根拠": [{"記事": "ファイルシステム", "事実": "保存先を確認する。"}]},
                                                             ensure_ascii=False), "ファイルシステム", "adopt-test", "保存の頼み", "2026-09-01 08:00:00")).lastrowid
    gakushuu.teian_action({"id": adopt_id, "状態": "試す"})
    gakushuu.teian_action({"id": adopt_id, "状態": "採用"})
    adopted = next((x for x in gakushuu.skills() if x["name"] == "保存先を確かめる技"), None)
    check(adopted and adopted["on"] and "1. 場所を確かめる" in adopted["body"] and "活かす役" in adopted["body"], "採用したカードを技として残す")
    check(next(x for x in gakushuu.teian_list() if x["id"] == adopt_id)["状態"] == "採用", "カードの状態は採用")
    # 10/2: 会話の言葉から題を選ぶ時、ゴミ箱の会話と「試験: 」の会話は使わない。
    with sqlite3.connect(os.environ["KERNEL_CHATS_DB"]) as db:
        db.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT, created REAL, updated REAL,"
                   " archived INTEGER DEFAULT 0, group_name TEXT DEFAULT '', deleted_at REAL, title_manual INTEGER DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS turns (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, position INTEGER,"
                   " role TEXT, text TEXT, trace TEXT, ms INTEGER, created REAL)")
        db.executemany("INSERT INTO conversations(id,title,created,updated,deleted_at) VALUES(?,?,?,?,?)",
                       [("live", "天体観測", 1, 1, None), ("gone", "捨てた会話", 1, 1, 5), ("test", "試験: 停止", 1, 1, None)])
        db.executemany("INSERT INTO turns(conversation_id,position,role,text,created) VALUES(?,?,?,?,?)",
                       [("live", 0, "user", "天体観測の始め方", 1), ("gone", 0, "user", "紅葉の名所", 1), ("test", 0, "user", "舞鶴の港", 1)])
    topics = gakushuu._recent_topics()
    check("天体観測" in topics and not any(w in topics for w in ("紅葉", "名所", "舞鶴")), "ゴミ箱・試験の会話の言葉では学ばない")

print("OK: 本文取得・本文取り直し・活動数・FTS5・振り返り・外の先生・busy・10分・API")
