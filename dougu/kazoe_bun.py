#!/usr/bin/env python3
"""imatrix 用の校正文。J01〜J26 の使い方6・知識2・一般2、約4万トークン。

この worktree に記録がない場合、正本 koukai/dougu/kekka を読む（書かない）。
試験 J27〜J41 と知識試験2本の問い・答え・別解・題・根拠を文字列照合で除外。
短い答えも省略せず、正規化（NFKC・空白除去・casefold）後も照合する。
記事は試験対象の題を丸ごと除外し、本文も同じ照合をする。
トークン数は日本語等1文字、ASCII約4文字/トークンの推定（厳密値ではない）。
--tokenizer-json に同モデルの tokenizer.json を渡すと厳密に数えられる。
モデル推論・ネットワーク・DB更新・jiyuu の import は行わない。
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import random
import re
import sqlite3
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANONICAL = Path.home() / "LocalAI_mirror/koukai/dougu/kekka"
DB = Path.home() / "Library/Application Support/kernel-ai/gakushuu/chishiki.sqlite3"
MEMORY = Path.home() / "Library/Application Support/kernel-ai/memory.db"


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                yield json.loads(line)


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())


class Exclusions:
    def __init__(self, evaluation, knowledge_tests):
        self.terms = set()
        self.titles = set()
        rows = list(read_jsonl(evaluation))
        held_out = [r for r in rows if re.fullmatch(r"J(?:2[7-9]|3[0-9]|4[01])", r.get("id", ""))]
        if len({r['id'] for r in held_out}) != 15:
            raise ValueError("除外対象 J27〜J41 が揃っていない")
        for row in held_out:
            self.terms.add(row['toi'])
            self.terms.add(row['id'])
        for path in knowledge_tests:
            tests = list(read_jsonl(path))  # 無い試験ファイルを黙って飛ばさない
            if not tests:
                raise ValueError(f"知識試験が空: {path}")
            for row in tests:
                for key in ("問", "答", "題"):
                    text = row[key]
                    if not isinstance(text, str) or not text.strip():
                        raise ValueError(f"除外項目が空/文字列でない: {path} {key}")
                    self.terms.add(text)
                self.terms.update(row.get("別解", []))
                if row.get("根拠"):
                    self.terms.add(row['根拠'])
                self.titles.add(normalize(row['題']))
        self.terms.discard("")
        self.normalized = sorted({normalize(t) for t in self.terms if normalize(t)}, key=len)

    def clean(self, text):
        norm = normalize(text)
        return not any(t in norm for t in self.normalized)

    def verify(self, text):
        norm = normalize(text)
        hits = [t for t in self.normalized if t in norm]
        if hits:
            raise ValueError(f"校正文に除外対象が {len(hits)} 件ある（保存しない）")
        return 0


def definitions(path=HERE / "jiyuu.py"):
    """SYSTEM/TOOLS の式だけ読み取る。アプリ/本番を import しない。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    def tool(name, description, properties, required):
        return {"type": "function", "function": {"name": name, "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required}}}
    env = {"_tool": tool, "_s": lambda description: {"type": "string", **({"description": description} if description else {})}}
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("SYSTEM", "TOOLS"):
                    # 許すのはリテラル構造と既知の _tool/_s 呼出だけ。
                    allowed = (ast.Expression, ast.Constant, ast.List, ast.Tuple, ast.Dict,
                               ast.Call, ast.Name, ast.Load)
                    for child in ast.walk(node.value):
                        if not isinstance(child, allowed):
                            raise ValueError("jiyuu の定義式が未対応。勝手に import しない")
                        if isinstance(child, ast.Name) and child.id not in env:
                            raise ValueError(f"未対応の定義名: {child.id}")
                        if isinstance(child, ast.Call) and (not isinstance(child.func, ast.Name) or child.keywords):
                            raise ValueError("未対応の定義呼び出し")
                    result[target.id] = eval(compile(ast.Expression(node.value), str(path), "eval"),
                                            {"__builtins__": {}}, env)
    if set(result) != {"SYSTEM", "TOOLS"}:
        raise ValueError("jiyuu.py の SYSTEM/TOOLS が揃わない")
    return result['SYSTEM'], result['TOOLS']


def shorten_paths(text):
    # 実際の試験ログには /.../koukai-jiyuu-XXXX/Jnn/home/... が含まれる。
    text = re.sub(r"/(?:private/)?(?:var/folders|tmp|Users)/[^\s\"'<>]*?/J\d{2}/home(?=/|[\s\"'<>]|$)", "~", text)
    text = re.sub(r"/(?:private/)?(?:var/folders|tmp)/[^\s\"'<>]*?(?:koukai-jiyuu|jiyuu)[^\s\"'<>]*/", "~/", text)
    return text.replace(str(Path.home()), "~")


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def message(role, body):
    return f"<|im_start|>{role}\n{body}<|im_end|>\n"


def tool_call(name, args):
    # Qwen3.6: <tool_call><function=name><parameter=...>...</parameter>...
    body = f"<tool_call>\n<function={name}>\n"
    for key, val in args.items():
        val = dumps(val) if isinstance(val, (dict, list)) else str(val)
        body += f"<parameter={key}>\n{val}\n</parameter>\n"
    return body + "</function>\n</tool_call>"


def system_message(system, tools):
    # tokenizer.chat_template の tools 分岐と同じ schema/呼び出し形式。
    body = system + '\n\n# Tools\n\nYou have access to the following functions:\n\n<tools>'
    body += ''.join('\n' + dumps(t) for t in tools)
    body += ('\n</tools>\n\nFor each function call, return the function name and parameters '
             'within <tool_call></tool_call> XML tags:\n<tool_call>\n<function=example_function_name>\n'
             '<parameter=example_parameter_1>\nvalue_1\n</parameter>\n</function>\n</tool_call>')
    return message('system', body)


def usage_records(logs, exclusions, prefix):
    candidates = []
    seen = set()
    for path in sorted(Path(logs).rglob('*.jsonl')):
        # パス成分が J01〜J26 の記録だけ。J27 以降はファイルを開かない。
        ids = [p for p in path.parts if re.fullmatch(r'J\d{2}', p)]
        if not ids or not 1 <= int(ids[-1][1:]) <= 26 or len(set(ids)) != 1:
            continue
        rows = list(read_jsonl(path))
        parts = []
        request = False
        pending = False
        calls = 0
        answer = False
        for row in rows:
            stage, content = row.get('段階'), row.get('内容', {})
            if not isinstance(content, dict):
                continue
            if stage == '依頼' and content.get('文'):
                if request:
                    raise ValueError(f'1記録に複数の依頼: {path}')
                parts.append(message('user', content['文']))
                request = True
            elif stage == '提案' and content.get('道具') and request:
                if pending:
                    parts.append(message('user', '<tool_response>\n結果の記録がありません。\n</tool_response>'))
                parts.append(message('assistant', '<think>\n\n</think>\n\n' + tool_call(content['道具'], content.get('入力', {}))))
                pending = True
                calls += 1
            elif stage == '結果' and content.get('答え') and request:
                if pending:
                    parts.append(message('user', '<tool_response>\n結果の記録がありません。\n</tool_response>'))
                parts.append(message('assistant', '<think>\n\n</think>\n\n' + content['答え']))
                answer = True
                pending = False
            elif stage == '結果' and pending:
                # 輪/経路/確認済みなど計測側の記録は校正文に持ち込まない。
                result = {k: v for k, v in content.items() if k not in ('輪', '経路', '確認済み')}
                parts.append(message('user', '<tool_response>\n' + dumps(result) + '\n</tool_response>'))
                pending = False
        if not request or not calls or not answer or pending:
            continue  # 未完走のログは採らない
        text = prefix + shorten_paths(''.join(parts))
        digest = hashlib.sha256(text.encode()).hexdigest()
        if len(text) <= 26000 and digest not in seen and exclusions.clean(text):
            candidates.append((text, str(path)))
            seen.add(digest)
    return candidates


def knowledge_records(db, exclusions):
    records = []
    # mode=ro は WAL も読む。immutable=1 は現用 DB の最新 WAL を無視するので使わない。
    uri = Path(db).expanduser().resolve().as_uri() + '?mode=ro'
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.execute('PRAGMA query_only=ON')
        for title, text in conn.execute('SELECT title,text FROM chishiki ORDER BY title'):
            if not title or not text or normalize(title) in exclusions.titles or not exclusions.clean(title):
                continue
            # 記事全体が試験語を含むものは本文を切って逃がさない。
            if not exclusions.clean(text):
                continue
            excerpt = text[:1800]
            block = message('system', '日本語で簡潔に説明する係。')
            block += message('user', '知識の箱の資料を読んでください。\n題: ' + title + '\n' + excerpt)
            block += message('assistant', '<think>\n\n</think>\n\n資料を読みました。必要な用件があれば、この本文を参照して説明します。')
            if exclusions.clean(block):
                records.append((block, title))
            if len(records) >= 300:
                break
    return records


def general_records(exclusions):
    pairs = [
        ('朝の予定を整えたい。', '机を片づけて、水を飲み、今日やることを三つ書き出しましょう。急ぐ用件から順番に進めると落ち着けます。'),
        ('散歩のあとに短い日記を書きたい。', '歩いた道、空の色、耳に残った音を一つずつ書くと、その日の様子が伝わります。最後に気持ちを一文添えましょう。'),
        ('友人との待ち合わせを決める文を作って。', '土曜日の午後、駅前の広場で待ち合わせませんか。都合のよい時間を教えてください。雨なら近くの店に入りましょう。'),
        ('Explain how to keep notes tidy.', 'Use a descriptive heading, record the date, and separate observations from tasks. Review unfinished tasks regularly and keep related notes together.'),
        ('Rewrite this politely: Please send the draft.', 'Could you send me the draft when you have a moment? I would like to review it before our meeting. Thank you for your help.'),
        ('数字の一覧から偶数だけを選ぶ Python の例を見せて。', '```python\nvalues = [3, 8, 11, 14]\neven = [x for x in values if x % 2 == 0]\nprint(even)\n```\n条件を満たす値だけを新しい一覧に集めます。'),
        ('JavaScript で文字列の前後の空白を取るには。', '```javascript\nconst raw = "  hello  ";\nconst clean = raw.trim();\nconsole.log(clean);\n```\n元の文字列は変更せず、結果を別の変数に入れます。'),
        ('パンを買うメモを短く書いて。', '朝食用のパンと牛乳を買う。買い物袋を持って行き、帰ったら牛乳を冷蔵庫に入れる。'),
        ('見出しと本文の違いを説明して。', '見出しは内容の入口を短く示すものです。本文には出来事や理由を詳しく書きます。段落を分けると流れを追いやすくなります。'),
        ('How do I name variables clearly?', 'Choose names that describe the data, such as file_path or total_items. Keep naming consistent and avoid names whose meaning depends on hidden context.'),
    ]
    blocks = [(message('system', '日本語と英語で簡潔に答える係。') + message('user', q)
               + message('assistant', '<think>\n\n</think>\n\n' + a), f'一般{n}') for n, (q, a) in enumerate(pairs)]
    # 本人が実際に頼んだ言い回し（memory.db）を、続きの会話のまま3組ずつ。型文の繰り返しより本番に近い。
    real = memory_pairs()
    for n in range(0, len(real), 3):
        text = message('system', '日本語で簡潔に答える係。')
        for q, a in real[n:n + 3]:
            text += message('user', q) + message('assistant', '<think>\n\n</think>\n\n' + a)
        blocks.append((text, f'本人の頼み{n}'))
    return [(text, source) for text, source in blocks if exclusions.clean(text)]


def memory_pairs(db=MEMORY):
    if not Path(db).exists():
        return []
    # 9/24 から書かれていない控え。immutable で読むだけ（砂箱でも開ける）。
    with contextlib.closing(sqlite3.connect(Path(db).resolve().as_uri() + '?immutable=1', uri=True)) as conn:
        rows = conn.execute('SELECT role, text FROM turns ORDER BY id').fetchall()
    pairs, seen = [], set()
    for (r1, q), (r2, a) in zip(rows, rows[1:]):
        if r1 == 'user' and r2 == 'assistant' and (q or '').strip() and (a or '').strip() and (q, a) not in seen:
            seen.add((q, a))
            pairs.append((q.strip(), a.strip()))
    return pairs


def token_counter(tokenizer_json=None):
    if tokenizer_json:
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(str(Path(tokenizer_json).expanduser()))
        return lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids), 'tokenizer.json 実測'
    def estimate(text):
        non_ascii = sum(ord(c) > 127 for c in text)
        return max(1, round(non_ascii + (len(text) - non_ascii) / 4))
    return estimate, '推定: 非ASCII 1文字、ASCII 4文字 ≈ 1トークン'


def select(records, target, count, rng):
    if not records:
        raise ValueError('除外後に校正文の材料がない')
    # 完結した会話単位で取る。長文を途中切断しない。
    records = list(records)
    rng.shuffle(records)
    selected = []
    total = 0
    for _ in range(10):
        for text, source in records:
            n = count(text)
            if n > target * 1.1:
                continue
            if total >= target * .96:
                return selected, total
            if total + n <= target * 1.1:
                selected.append((text, source))
                total += n
        if total >= target * .9:
            return selected, total
    raise ValueError(f'材料が不足: 目標 {target} に対し {total} トークン（長過ぎる記録も除外）')


def build(args):
    exclusions = Exclusions(args.evaluation, args.knowledge_tests)
    system, tools = definitions()
    prefix = system_message(system, tools)
    if not exclusions.clean(prefix):
        raise ValueError('SYSTEM/TOOLS に除外語がある。試験材料を見直す必要がある')
    count, method = token_counter(args.tokenizer_json)
    pools = {'使い方': usage_records(args.logs, exclusions, prefix),
             '知識': knowledge_records(args.db, exclusions), '一般': general_records(exclusions)}
    rng = random.Random(args.seed)
    chosen, sizes = [], {}
    for category, ratio in [('使い方', .6), ('知識', .2), ('一般', .2)]:
        blocks, size = select(pools[category], round(args.tokens * ratio), count, rng)
        sizes[category] = size
        chosen.extend((category, text, source) for text, source in blocks)
    rng.shuffle(chosen)
    text = '\n'.join(block for _, block, _ in chosen)
    exclusions.verify(text)  # 会話の境界を跨ぐ一致も確認
    if re.search(r'/(?:private/)?var/folders/', text):
        raise ValueError('一時の長い path が残った（保存しない）')
    out = Path(args.out).expanduser().resolve()
    if not out.is_relative_to(HERE / 'kekka'):
        raise ValueError('出力はこの worktree の dougu/kekka/ の中だけ')
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {'tokens': count(text), 'count_method': method, 'categories': sizes,
              'target_tokens': args.tokens, 'candidate_counts': {k: len(v) for k, v in pools.items()},
              'excluded_terms': len(exclusions.normalized), 'excluded_titles': len(exclusions.titles),
              'held_out_matches': 0, 'seed': args.seed,
              'sha256': hashlib.sha256(text.encode()).hexdigest(),
              'records': [{'category': c, 'source': s} for c, _, s in chosen]}
    # 除外確認が完了してから書く。上書き可能なのは生成用の git 外の出力のみ。
    out.write_text(text, encoding='utf-8')
    out.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'校正文: {out}\n{report["tokens"]:,} トークン（{method}）・{sizes}・除外対象の一致 0 件')
    return report


def main():
    local = HERE / 'kekka'
    source = local if (local / 'jiyuu_logs').is_dir() else CANONICAL
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--logs', type=Path, default=source / 'jiyuu_logs')
    parser.add_argument('--db', type=Path, default=DB)
    parser.add_argument('--evaluation', type=Path, default=HERE.parent / 'monosashi/jiyuu.jsonl')
    parser.add_argument('--knowledge-tests', type=Path, nargs=2,
                        default=[source / 'codex_1001b_toi2.jsonl', source / 'codex_1001_toi.jsonl'])
    parser.add_argument('--tokens', type=int, default=40000)
    parser.add_argument('--tokenizer-json', type=Path)
    parser.add_argument('--seed', type=int, default=1002)
    parser.add_argument('--out', type=Path, default=local / 'kazoe_bun.txt')
    args = parser.parse_args()
    if args.tokens < 1000:
        parser.error('--tokens は 1000 以上')
    try:
        build(args)
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, f'エラー: {exc}\n')


if __name__ == '__main__':
    main()
