#!/usr/bin/env python3
"""小さい偽 GGUF だけで切り出し・校正文の漏洩防止を試す（本番は触らない）。"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import gguf
import numpy as np
from gguf.quants import quantize, quant_shape_to_byte_shape

import senmonka_kezuru as prune
import kazoe_bun as corpus


def write_gguf(path, tensors, meta, arch='qwen35moe'):
    writer = gguf.GGUFWriter(path, arch)
    for key, val in meta.items():
        if isinstance(val, list):
            writer.add_array(key, val)
        elif isinstance(val, str):
            writer.add_string(key, val)
        else:
            writer.add_uint32(key, val)
    for name, (data, kind) in tensors.items():
        writer.add_tensor(name, data, raw_dtype=kind)
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kezuru-test-')
        self.root = Path(self.temp.name)
        self.model = self.root / 'model.gguf'
        self.imatrix = self.root / 'imatrix.gguf'
        self.out = self.root / 'out.gguf'
        self.old_ids = [7, 4, 2, 1]  # count 7最大、4/2同数ならsum2、1/0なら元番号

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, kind=gguf.GGMLQuantizationType.F32, mtp=0, transposed=False):
        tensors, stats = {}, {}
        self.original = {}
        f32 = gguf.GGMLQuantizationType.F32
        for layer in range(2):
            for k, name in enumerate(prune.EXPERTS):
                if kind in (f32, gguf.GGMLQuantizationType.Q8_0):
                    data = (np.arange(8 * 3 * 32, dtype=np.float32).reshape(8, 3, 32) + layer * 1000 + k * 100) / 100
                    data = quantize(data, kind)
                else:
                    # 実物の IQ 系も生バイトの形・保存を確認（復号/推論はしない）。
                    width = gguf.GGML_QUANT_SIZES[kind][0]
                    data = np.zeros(quant_shape_to_byte_shape((8, 3, width), kind), dtype=np.uint8)
                    for expert in range(8):
                        data[expert].fill(expert + layer * 8 + k * 16)
                full_name = f'blk.{layer}.{name}.weight'
                tensors[full_name] = (data, kind)
                self.original[full_name] = data.copy()
                tensors[f'blk.{layer}.{name}.bias'] = (np.arange(24, dtype=np.float32).reshape(8, 3), f32)
                c = np.array([2, 3, 5, 1, 5, 0, 0, 8], dtype=np.float32)
                sums = np.array([3, 3, 10, 3, 20, 0, 0, 3], dtype=np.float32).reshape(8, 1)
                stats[full_name + '.counts'] = (c, f32)
                stats[full_name + '.in_sum2'] = (sums, f32)
            router = np.arange(8 * 32, dtype=np.float32).reshape(8, 32) + layer * 1000
            if transposed:
                router = router.T.copy()
            name = f'blk.{layer}.ffn_gate_inp.weight'
            tensors[name] = (router, f32)
            self.original[name] = router.copy()
            tensors[f'blk.{layer}.ffn_gate_inp.bias'] = (np.arange(8, dtype=np.float32), f32)
            tensors[f'blk.{layer}.exp_probs_b.bias'] = (np.arange(8, dtype=np.float32) * 2, f32)
            tensors[f'blk.{layer}.ffn_down_shexp.weight'] = (np.ones((3, 32), dtype=np.float32), f32)
        tensors['token_embd.weight'] = (np.ones((4, 32), dtype=np.float32), f32)
        tensors['output.weight'] = (np.ones((4, 32), dtype=np.float32) * 9, f32)
        tensors['blk.1.nextn.eh_proj.weight'] = (np.ones((32, 64), dtype=np.float32), f32)
        meta = {'qwen35moe.expert_count': 8, 'qwen35moe.expert_used_count': 2,
                'qwen35moe.block_count': 2, 'qwen35moe.nextn_predict_layers': mtp,
                'qwen35moe.attention.head_count': [4, 4],
                'qwen35moe.attention.recurrent_layers': [1, 0],
                'qwen35moe.rope.dimension_sections': [1, 2, 3, 4],
                'tokenizer.ggml.tokens': ['<|im_start|>', '日本語', 'hello', '<|im_end|>'],
                'tokenizer.chat_template': 'そのまま保存する模板', 'general.name': 'fake qwen35moe'}
        write_gguf(self.model, tensors, meta)
        write_gguf(self.imatrix, stats, {'general.type': 'imatrix'}, arch='')
        return tensors, stats, meta

    def run_prune(self, keep=4, drop=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return prune.prune(self.model, self.imatrix, keep, drop, self.out)

    def check(self, kind, drop=False, transposed=False):
        tensors, _, _ = self.fixture(kind, int(drop), transposed)
        report = self.run_prune(drop=drop)
        output = gguf.GGUFReader(self.out)
        before = gguf.GGUFReader(self.model)
        out_tensors = {t.name: t for t in output.tensors}
        original_tensors = {t.name: t for t in before.tensors}
        self.assertEqual(prune.value(output, 'qwen35moe.expert_count'), 4)
        self.assertEqual(prune.value(output, 'qwen35moe.expert_used_count'), 2)
        self.assertEqual(prune.value(output, 'qwen35moe.block_count'), 1 if drop else 2)
        self.assertEqual(prune.value(output, 'qwen35moe.nextn_predict_layers'), 0)
        for key, field in before.fields.items():
            if key.startswith('GGUF.') or key in ('qwen35moe.expert_count', 'qwen35moe.block_count',
                                                  'qwen35moe.nextn_predict_layers'):
                continue
            expected = field.contents()
            if drop and key.removeprefix('qwen35moe.') in prune.LAYER_ARRAYS and isinstance(expected, list):
                expected = expected[:1]
            self.assertEqual(output.fields[key].contents(), expected, key)
            self.assertEqual(output.fields[key].types, field.types)
        for layer in range(1 if drop else 2):
            self.assertEqual(report['layers'][str(layer)], self.old_ids)
            for name in prune.EXPERTS:
                fullname = f'blk.{layer}.{name}.weight'
                actual = out_tensors[fullname]
                self.assertEqual(actual.tensor_type, kind)
                np.testing.assert_array_equal(actual.data, self.original[fullname][self.old_ids])
                np.testing.assert_array_equal(out_tensors[f'blk.{layer}.{name}.bias'].data,
                                              tensors[f'blk.{layer}.{name}.bias'][0][self.old_ids])
            name = f'blk.{layer}.ffn_gate_inp.weight'
            expected = self.original[name][:, self.old_ids] if transposed else self.original[name][self.old_ids]
            np.testing.assert_array_equal(out_tensors[name].data, expected)
            for name in ('ffn_gate_inp.bias', 'exp_probs_b.bias'):
                full = f'blk.{layer}.{name}'
                np.testing.assert_array_equal(out_tensors[full].data, tensors[full][0][self.old_ids])
        for name, tensor in original_tensors.items():
            if drop and name.startswith('blk.1.'):
                self.assertNotIn(name, out_tensors)
            elif 'exps' not in name and 'ffn_gate_inp.' not in name and 'exp_probs_b' not in name:
                self.assertEqual(out_tensors[name].data.tobytes(), tensor.data.tobytes())
        saved = json.loads(self.out.with_suffix('.experts.json').read_text())
        self.assertEqual(saved, report)
        self.assertLess(self.out.stat().st_size, self.model.stat().st_size)

    def test_f32(self):
        self.check(gguf.GGMLQuantizationType.F32)

    def test_q8_bytes(self):
        self.check(gguf.GGMLQuantizationType.Q8_0)

    def test_drop_mtp_q8(self):
        self.check(gguf.GGMLQuantizationType.Q8_0, drop=True)

    def test_transposed_router(self):
        self.check(gguf.GGMLQuantizationType.F32, transposed=True)

    def test_real_quantization_types_bytes(self):
        for kind in (gguf.GGMLQuantizationType.IQ2_XS, gguf.GGMLQuantizationType.IQ3_XXS,
                     gguf.GGMLQuantizationType.IQ4_XS, gguf.GGMLQuantizationType.Q2_K):
            with self.subTest(kind=kind.name):
                self.out.unlink(missing_ok=True)
                self.out.with_suffix('.experts.json').unlink(missing_ok=True)
                self.check(kind)

    def test_used_eight_preserved(self):
        tensors, _, meta = self.fixture()
        meta['qwen35moe.expert_used_count'] = 8
        write_gguf(self.model, tensors, meta)
        self.run_prune(keep=8)
        self.assertEqual(prune.value(gguf.GGUFReader(self.out), 'qwen35moe.expert_used_count'), 8)

    def test_count_mismatch_rejected(self):
        _, stats, _ = self.fixture()
        stats['blk.0.ffn_up_exps.weight.counts'][0][0] += 1
        write_gguf(self.imatrix, stats, {'general.type': 'imatrix'}, arch='')
        with self.assertRaisesRegex(ValueError, 'counts が不一致'):
            self.run_prune()
        self.assertFalse(self.out.exists())

    def test_no_mtp_statistics(self):
        _, stats, _ = self.fixture(mtp=1)
        stats = {k: v for k, v in stats.items() if not k.startswith('blk.1.')}
        write_gguf(self.imatrix, stats, {'general.type': 'imatrix'}, arch='')
        with self.assertRaisesRegex(ValueError, '使用統計がない'):
            self.run_prune()
        self.run_prune(drop=True)

    def test_keep_cannot_change_used_count(self):
        self.fixture()
        with self.assertRaisesRegex(ValueError, 'expert_used_count'):
            self.run_prune(keep=1)
        self.assertFalse(self.out.exists())

    def test_overwrite_forbidden(self):
        self.fixture()
        self.out.write_bytes(b'do not change')
        with self.assertRaises(FileExistsError):
            self.run_prune()
        self.assertEqual(self.out.read_bytes(), b'do not change')

    def test_protected_output_forbidden(self):
        with self.assertRaisesRegex(ValueError, '読み取り専用'):
            prune.safe_output(Path.home() / 'LocalAI_mirror/models/new.gguf')


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='corpus-test-')
        self.root = Path(self.temp.name)
        self.evaluation = self.root / 'evaluation.jsonl'
        self.evaluation.write_text('\n'.join(json.dumps({'id': f'J{i}', 'toi': f'未見課題{i}固有の頼み'}, ensure_ascii=False)
                                            for i in range(27, 42)))
        self.knowledge = self.root / 'knowledge.jsonl'
        self.knowledge.write_text(json.dumps({'題': '除外記事', '問': '特別な知識の問い', '答': '秘密の答え',
                                               '別解': ['Alternative ANSWER'], '根拠': '出題根拠'}, ensure_ascii=False))
        self.exclusions = corpus.Exclusions(self.evaluation, [self.knowledge, self.knowledge])

    def tearDown(self):
        self.temp.cleanup()

    def test_normalized_leak_rejected(self):
        for text in ('秘密の答え', 'Ｊ２７', 'Alternative   answer', '除外記事'):
            self.assertFalse(self.exclusions.clean(text))
            with self.assertRaises(ValueError):
                self.exclusions.verify(text)

    def test_system_tools_without_import(self):
        system, tools = corpus.definitions()
        self.assertIn('Mac作業係', system)
        self.assertIn('read', [t['function']['name'] for t in tools])
        self.assertIn('<function=read>', corpus.tool_call('read', {'path': '~/Documents/memo.txt'}))

    def test_path_shortening(self):
        text = '/private/var/folders/xx/yy/T/koukai-jiyuu-abc/J03/home/Documents/会議.txt'
        self.assertEqual(corpus.shorten_paths(text), '~/Documents/会議.txt')

    def test_usage_held_out_not_opened(self):
        logs = self.root / 'logs'
        for id in ('J01', 'J27'):
            (logs / id).mkdir(parents=True)
        (logs / 'J27/no_read.jsonl').write_text('invalid JSON; must never be opened')
        rows = [{'段階': '依頼', '内容': {'文': 'メモを読む'}},
                {'段階': '提案', '内容': {'道具': 'read', '入力': {'path': '~/Documents/memo.txt'}}},
                {'段階': '結果', '内容': {'ok': True, '結果': '静かな朝'}},
                {'段階': '結果', '内容': {'答え': 'メモに静かな朝と書いてあります。'}}]
        (logs / 'J01/ok.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows))
        records = corpus.usage_records(logs, self.exclusions, '')
        self.assertEqual(len(records), 1)
        self.assertIn('<tool_response>', records[0][0])
        self.assertIn('<function=read>', records[0][0])

    def test_knowledge_exclusion_and_read_only(self):
        import sqlite3
        db = self.root / 'articles.sqlite3'
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute('CREATE TABLE chishiki(title TEXT,text TEXT)')
            conn.executemany('INSERT INTO chishiki VALUES(?,?)', [('除外記事', '安全そうな本文'),
                ('別の記事', '秘密の答えを含む本文'), ('安全な記事', '緑の葉と土の話。')])
            conn.commit()
        before = db.read_bytes()
        records = corpus.knowledge_records(db, self.exclusions)
        self.assertEqual([r[1] for r in records], ['安全な記事'])
        self.assertEqual(db.read_bytes(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
