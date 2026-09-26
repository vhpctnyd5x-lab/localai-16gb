#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加道具用の制限 Python 評価器。exec/eval/compile は使わない。"""
from __future__ import annotations

import ast
import json
import math
import os
import resource
import sys
from typing import Any

MAX_SOURCE_BYTES = 32 * 1024
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
MAX_STRING_BYTES = 256 * 1024
MAX_VALUE_BYTES = 1024 * 1024
MAX_ITEMS = 4096
MAX_DEPTH = 24
MAX_LOOP = 2048
MAX_STEPS = 100_000
_TOKEN_ENV = "TSUIKA_WORKER_TOKEN"
_METHODS = {
    str: {"split", "strip", "join", "replace", "lower", "upper", "startswith", "endswith", "find", "count", "splitlines"},
    list: {"append", "extend", "index", "count"},
    dict: {"get", "items", "keys", "values"},
}
_BUILTINS = {"len", "sum", "min", "max", "sorted", "range", "enumerate", "zip", "abs", "round", "any", "all", "str", "int", "float", "bool", "list", "dict", "set", "tuple"}
_BINOPS = {ast.Add, ast.Sub, ast.Mult, ast.Div}


class ToolRejected(ValueError):
    pass


def _bounded(value: Any, depth: int = 0, budget: list[int] | None = None) -> Any:
    if budget is None:
        budget = [0]
    if depth > MAX_DEPTH:
        raise ToolRejected("値の入れ子が深すぎます")
    if value is None or type(value) in (bool, int, float):
        if type(value) is int and value.bit_length() > 4096:
            raise ToolRejected("整数が大きすぎます")
        if type(value) is float and not math.isfinite(value):
            raise ToolRejected("有限でない数は使えません")
        budget[0] += max(1, (value.bit_length() + 7) // 8) if type(value) is int else 8
        if budget[0] > MAX_VALUE_BYTES: raise ToolRejected("値全体が大きすぎます")
        return value
    if type(value) is str:
        size = len(value.encode("utf-8"))
        if size > MAX_STRING_BYTES:
            raise ToolRejected("文字列が大きすぎます")
        budget[0] += size
        if budget[0] > MAX_VALUE_BYTES: raise ToolRejected("値全体が大きすぎます")
        return value
    if type(value) in (list, tuple, set):
        if len(value) > MAX_ITEMS:
            raise ToolRejected("配列が大きすぎます")
        budget[0] += len(value) * 8
        if budget[0] > MAX_VALUE_BYTES: raise ToolRejected("値全体が大きすぎます")
        for item in value:
            _bounded(item, depth + 1, budget)
        return value
    if type(value) is dict:
        if len(value) > MAX_ITEMS:
            raise ToolRejected("辞書が大きすぎます")
        budget[0] += len(value) * 16
        if budget[0] > MAX_VALUE_BYTES: raise ToolRejected("値全体が大きすぎます")
        for key, item in value.items():
            _bounded(key, depth + 1, budget); _bounded(item, depth + 1, budget)
        return value
    raise ToolRejected("許可していない値の型です")


def _ident(name: str) -> None:
    if not name.isidentifier() or "__" in name:
        raise ToolRejected("使えない名前です")


def validate_source(source: str) -> ast.Module:
    if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ToolRejected("tool.py は32KB以内にしてください")
    try:
        tree = ast.parse(source, mode="exec")
    except (SyntaxError, ValueError, MemoryError) as error:
        raise ToolRejected("Python の文法を読めません") from error
    functions = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            raise ToolRejected("一番外側には関数定義だけ書けます")
        _ident(node.name)
        if node.name in functions or node.decorator_list or node.returns or node.type_comment:
            raise ToolRejected("重複した関数・装飾・型注釈は使えません")
        if node.args.posonlyargs or node.args.vararg or node.args.kwarg or node.args.kwonlyargs or node.args.defaults or node.args.kw_defaults:
            raise ToolRejected("関数の引数は位置引数だけにしてください")
        for arg in node.args.args:
            _ident(arg.arg)
            if arg.annotation:
                raise ToolRejected("型注釈は使えません")
        functions[node.name] = node
    if not {"run", "tameshi"}.issubset(functions):
        raise ToolRejected("run(args, inputs) と tameshi() が必要です")
    if [arg.arg for arg in functions["run"].args.args] != ["args", "inputs"] or functions["tameshi"].args.args:
        raise ToolRejected("関数の形は run(args, inputs) と tameshi() にしてください")

    allowed = (
        ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign, ast.Expr, ast.If,
        ast.For, ast.While, ast.Break, ast.Continue, ast.Pass, ast.Name, ast.Constant, ast.List, ast.Tuple,
        ast.Set, ast.Dict, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Call, ast.keyword,
        ast.Attribute, ast.Subscript, ast.Slice, ast.Load, ast.Store, ast.Add, ast.Sub, ast.Mult, ast.Div,
        ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt,
        ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot, ast.JoinedStr, ast.FormattedValue,
    )
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ToolRejected("許可されていない構文です: " + type(node).__name__)
        if isinstance(node, ast.FunctionDef) and node is not tree.body[0] and node not in tree.body:
            raise ToolRejected("関数定義は tool.py の一番外側だけに書けます")
        if isinstance(node, ast.Name):
            _ident(node.id)
        elif isinstance(node, ast.arg):
            _ident(node.arg)
        elif isinstance(node, ast.Attribute):
            parent = parents.get(id(node))
            if not isinstance(parent, ast.Call) or parent.func is not node or isinstance(node.value, ast.Attribute):
                raise ToolRejected("属性をたどる書き方は使えません")
            if node.attr.startswith("_") or "__" in node.attr or not any(node.attr in methods for methods in _METHODS.values()):
                raise ToolRejected("許可されていない属性です")
        elif isinstance(node, ast.Call):
            if node.keywords:
                raise ToolRejected("名前付き引数は使えません")
            if isinstance(node.func, ast.Name):
                if node.func.id not in _BUILTINS and node.func.id not in functions:
                    raise ToolRejected("許可されていない関数です")
            elif not isinstance(node.func, ast.Attribute):
                raise ToolRejected("許可されていない関数呼び出しです")
        elif isinstance(node, ast.Constant):
            if type(node.value) not in (str, int, float, bool, type(None)):
                raise ToolRejected("許可されていない定数です")
            _bounded(node.value)
        elif isinstance(node, ast.BinOp) and type(node.op) not in _BINOPS:
            raise ToolRejected("許可されていない計算です")
        elif isinstance(node, ast.FormattedValue) and (node.conversion not in (-1, 115) or node.format_spec is not None):
            raise ToolRejected("許可されていない文字列変換です")
    return tree


class _Break(Exception): pass
class _Continue(Exception): pass
class _Return(Exception):
    def __init__(self, value): self.value = value


class _Evaluator:
    def __init__(self, tree: ast.Module):
        self.functions = {node.name: node for node in tree.body}
        self.steps = 0
        self.depth = 0

    def tick(self):
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise ToolRejected("実行の手数上限を超えました")

    @staticmethod
    def iterable(value):
        if type(value) is dict: result = list(value)
        elif type(value) in (str, list, tuple, set): result = list(value)
        else: raise ToolRejected("反復できない値です")
        if len(result) > MAX_LOOP: raise ToolRejected("反復の長さ上限を超えました")
        return result

    def call(self, name, args):
        if name in _BUILTINS:
            return self.builtin(name, args)
        fn = self.functions.get(name)
        if fn is None or len(fn.args.args) != len(args):
            raise ToolRejected("関数名または引数の数が違います")
        self.depth += 1
        if self.depth > 32:
            raise ToolRejected("関数の呼び出しが深すぎます")
        env = {arg.arg: _bounded(value) for arg, value in zip(fn.args.args, args)}
        try:
            try: self.block(fn.body, env)
            except _Return as result: return _bounded(result.value)
            return None
        finally: self.depth -= 1

    def builtin(self, name, args):
        if name == "range":
            value = range(*args)
            if len(value) > MAX_LOOP: raise ToolRejected("range の長さ上限を超えました")
            return list(value)
        if name == "enumerate":
            if len(args) not in (1, 2): raise ToolRejected("enumerate の引数が違います")
            return list(enumerate(self.iterable(args[0]), args[1] if len(args) == 2 else 0))
        if name == "zip":
            if not args: raise ToolRejected("zip の引数が違います")
            return list(zip(*(self.iterable(value) for value in args)))
        if name == "sorted":
            if len(args) not in (1, 2) or (len(args) == 2 and type(args[1]) is not bool): raise ToolRejected("sorted の引数が違います")
            return sorted(self.iterable(args[0]), reverse=args[1] if len(args) == 2 else False)
        if name == "sum":
            if len(args) not in (1, 2): raise ToolRejected("sum の引数が違います")
            values = self.iterable(args[0])
            total = args[1] if len(args) == 2 else 0
            if type(total) not in (int, float, bool) or any(type(item) not in (int, float, bool) for item in values):
                raise ToolRejected("sum は数だけに使えます")
            for item in values: total = _bounded(total + item)
            return total
        if name in ("min", "max"):
            if not args: raise ToolRejected(name + " の引数がありません")
            values = self.iterable(args[0]) if len(args) == 1 else args
            if not values: raise ToolRejected(name + " に空の値は使えません")
            return (min if name == "min" else max)(values)
        if name in ("any", "all"):
            if len(args) != 1: raise ToolRejected(name + " の引数が違います")
            return (any if name == "any" else all)(self.iterable(args[0]))
        if name == "len":
            if len(args) != 1 or type(args[0]) not in (str, list, tuple, dict, set): raise ToolRejected("len に使えない値です")
            return len(args[0])
        constructors = {"str": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict, "set": set, "tuple": tuple}
        if name in constructors:
            if len(args) > 1: raise ToolRejected(name + " の引数が多すぎます")
            if name in ("list", "set", "tuple") and args: args = [self.iterable(args[0])]
            return _bounded(constructors[name](*args))
        if name == "abs" and len(args) == 1: return _bounded(abs(args[0]))
        if name == "round" and len(args) in (1, 2) and (len(args) == 1 or abs(args[1]) <= 100): return _bounded(round(*args))
        raise ToolRejected("許可されていない関数です")

    def block(self, body, env):
        for node in body:
            self.tick(); self.stmt(node, env)

    def stmt(self, node, env):
        if isinstance(node, ast.Return): raise _Return(None if node.value is None else self.expr(node.value, env))
        if isinstance(node, ast.Assign):
            value = self.expr(node.value, env)
            for target in node.targets: self.assign(target, value, env)
        elif isinstance(node, ast.AugAssign): self.assign(node.target, self.binary(node.op, self.expr(node.target, env), self.expr(node.value, env)), env)
        elif isinstance(node, ast.Expr): self.expr(node.value, env)
        elif isinstance(node, ast.If): self.block(node.body if self.expr(node.test, env) else node.orelse, env)
        elif isinstance(node, ast.For):
            seq = self.iterable(self.expr(node.iter, env))
            for item in seq:
                self.tick(); self.assign(node.target, item, env)
                try: self.block(node.body, env)
                except _Continue: continue
                except _Break: break
            else: self.block(node.orelse, env)
        elif isinstance(node, ast.While):
            loops = 0
            while self.expr(node.test, env):
                loops += 1; self.tick()
                if loops > MAX_LOOP: raise ToolRejected("while の反復上限を超えました")
                try: self.block(node.body, env)
                except _Continue: continue
                except _Break: break
            else: self.block(node.orelse, env)
        elif isinstance(node, ast.Break): raise _Break()
        elif isinstance(node, ast.Continue): raise _Continue()
        elif not isinstance(node, ast.Pass): raise ToolRejected("許可されていない文です")

    def assign(self, target, value, env):
        value = _bounded(value)
        if isinstance(target, ast.Name): env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            seq = self.iterable(value)
            if len(seq) != len(target.elts): raise ToolRejected("代入する値の数が違います")
            for t, v in zip(target.elts, seq): self.assign(t, v, env)
        elif isinstance(target, ast.Subscript):
            obj, key = self.expr(target.value, env), self.expr(target.slice, env)
            if type(obj) is dict: obj[key] = value
            elif type(obj) is list and type(key) is int: obj[key] = value
            else: raise ToolRejected("この値には代入できません")
            _bounded(obj)
        else: raise ToolRejected("代入先に使えない形です")

    @staticmethod
    def binary(op, left, right):
        if type(op) not in _BINOPS: raise ToolRejected("許可されていない計算です")
        if isinstance(op, ast.Mult):
            if type(left) is str and type(right) is int and len(left) * max(right, 0) > MAX_STRING_BYTES: raise ToolRejected("掛け算の結果が大きすぎます")
            if type(right) is str and type(left) is int and len(right) * max(left, 0) > MAX_STRING_BYTES: raise ToolRejected("掛け算の結果が大きすぎます")
            if type(left) in (list, tuple) and type(right) is int and len(left) * max(right, 0) > MAX_ITEMS: raise ToolRejected("掛け算の結果が大きすぎます")
            if type(right) in (list, tuple) and type(left) is int and len(right) * max(left, 0) > MAX_ITEMS: raise ToolRejected("掛け算の結果が大きすぎます")
        fn = {ast.Add: lambda: left + right, ast.Sub: lambda: left - right, ast.Mult: lambda: left * right,
              ast.Div: lambda: left / right}[type(op)]
        return _bounded(fn())

    def expr(self, node, env):
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.Name):
            if node.id not in env: raise ToolRejected("未定義の名前です: " + node.id)
            return env[node.id]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [self.expr(item, env) for item in node.elts]
            return _bounded(values if isinstance(node, ast.List) else tuple(values) if isinstance(node, ast.Tuple) else set(values))
        if isinstance(node, ast.Dict): return _bounded({self.expr(k, env): self.expr(v, env) for k, v in zip(node.keys, node.values)})
        if isinstance(node, ast.BinOp): return self.binary(node.op, self.expr(node.left, env), self.expr(node.right, env))
        if isinstance(node, ast.UnaryOp):
            value = self.expr(node.operand, env)
            if isinstance(node.op, ast.Not): return not value
            if isinstance(node.op, ast.UAdd): return _bounded(+value)
            if isinstance(node.op, ast.USub): return _bounded(-value)
        if isinstance(node, ast.BoolOp):
            value = self.expr(node.values[0], env)
            for item in node.values[1:]:
                if isinstance(node.op, ast.And) and not value or isinstance(node.op, ast.Or) and value: return value
                value = self.expr(item, env)
            return value
        if isinstance(node, ast.Compare):
            left = self.expr(node.left, env)
            for op, sub in zip(node.ops, node.comparators):
                right = self.expr(sub, env)
                fn = {ast.Eq: lambda: left == right, ast.NotEq: lambda: left != right, ast.Lt: lambda: left < right,
                      ast.LtE: lambda: left <= right, ast.Gt: lambda: left > right, ast.GtE: lambda: left >= right,
                      ast.In: lambda: left in right, ast.NotIn: lambda: left not in right, ast.Is: lambda: left is right,
                      ast.IsNot: lambda: left is not right}[type(op)]
                if not fn(): return False
                left = right
            return True
        if isinstance(node, ast.IfExp): return self.expr(node.body if self.expr(node.test, env) else node.orelse, env)
        if isinstance(node, ast.Subscript):
            obj, key = self.expr(node.value, env), self.expr(node.slice, env)
            if type(obj) not in (str, list, tuple, dict): raise ToolRejected("この値は添字で読めません")
            return _bounded(obj[key])
        if isinstance(node, ast.Slice): return slice(*(self.expr(x, env) if x is not None else None for x in (node.lower, node.upper, node.step)))
        if isinstance(node, ast.Call):
            args = [self.expr(item, env) for item in node.args]
            if isinstance(node.func, ast.Name): return _bounded(self.call(node.func.id, args))
            obj = self.expr(node.func.value, env); name = node.func.attr
            if type(obj) not in _METHODS or name not in _METHODS[type(obj)]: raise ToolRejected("許可されていないメソッドです")
            if type(obj) is list and name in ("append", "extend"):
                if len(args) != 1: raise ToolRejected("リストメソッドの引数が違います")
                values = self.iterable(args[0]) if name == "extend" else args
                if len(obj) + len(values) > MAX_ITEMS: raise ToolRejected("リストが大きすぎます")
                obj.extend(values) if name == "extend" else obj.append(values[0])
                return None
            if type(obj) is dict and name in ("items", "keys", "values"):
                if args: raise ToolRejected("辞書メソッドの引数が違います")
                method = {"items": dict.items, "keys": dict.keys, "values": dict.values}[name]
                return _bounded(list(method(obj)))
            if type(obj) is str and name == "join":
                if len(args) != 1: raise ToolRejected("join の引数が違います")
                values = self.iterable(args[0])
                if any(type(item) is not str for item in values): raise ToolRejected("join には文字列の配列が必要です")
                if sum(map(len, values)) + len(obj) * max(len(values) - 1, 0) > MAX_STRING_BYTES: raise ToolRejected("join の結果が大きすぎます")
            if type(obj) is str and name == "replace" and len(args) in (2, 3):
                old, new = args[0], args[1]
                count = args[2] if len(args) == 3 else -1
                occurrences = len(obj) + 1 if old == "" else obj.count(old)
                if count >= 0: occurrences = min(occurrences, count)
                if len(obj) + occurrences * (len(new) - len(old)) > MAX_STRING_BYTES: raise ToolRejected("replace の結果が大きすぎます")
            if type(obj) is str and name == "split":
                if len(args) > 2: raise ToolRejected("split の引数が違います")
                sep = args[0] if args else None
                maxsplit = args[1] if len(args) == 2 else -1
                parts = obj.count(sep) + 1 if type(sep) is str and sep else sum(1 for index, char in enumerate(obj) if not char.isspace() and (index == 0 or obj[index - 1].isspace()))
                if maxsplit >= 0: parts = min(parts, maxsplit + 1)
                if parts > MAX_ITEMS: raise ToolRejected("split の結果が大きすぎます")
            if type(obj) is str and name == "splitlines":
                separators = ("\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")
                breaks = sum(obj.count(separator) for separator in separators) - obj.count("\r\n")
                lines = breaks + (1 if obj and obj[-1] not in separators else 1 if obj else 0)
                if lines > MAX_ITEMS: raise ToolRejected("splitlines の結果が大きすぎます")
            if type(obj) is str:
                method = {"split": str.split, "strip": str.strip, "join": str.join, "replace": str.replace,
                          "lower": str.lower, "upper": str.upper, "startswith": str.startswith,
                          "endswith": str.endswith, "find": str.find, "count": str.count, "splitlines": str.splitlines}[name]
            elif type(obj) is list:
                method = {"index": list.index, "count": list.count}[name]
            elif type(obj) is dict:
                method = {"get": dict.get}[name]
            else:
                raise ToolRejected("許可されていないメソッドです")
            return _bounded(method(obj, *args))
        if isinstance(node, ast.JoinedStr): return _bounded("".join(str(self.expr(item, env)) if isinstance(item, ast.FormattedValue) else item.value for item in node.values))
        if isinstance(node, ast.FormattedValue):
            value = self.expr(node.value, env)
            return str(value)
        raise ToolRejected("許可されていない式です")


def _valid_result(value):
    _bounded(value)
    if type(value) is not dict or set(value) != {"result", "effects"}:
        raise ToolRejected("run は result と effects の辞書を返してください")
    effects = value.get("effects", [])
    if type(effects) is not list or len(effects) > 32 or any(type(item) is not dict for item in effects):
        raise ToolRejected("effects は32件以内の辞書のリストにしてください")


def evaluate(source, args=None, inputs=None, *, tests=False):
    engine = _Evaluator(validate_source(source))
    if not tests:
        result = engine.call("run", [args, inputs]); _valid_result(result); return result
    cases = engine.call("tameshi", [])
    if type(cases) is not list or not 1 <= len(cases) <= 100: raise ToolRejected("tameshi は1〜100件の試験ケースを返してください")
    capabilities = set()
    reads_files = False
    args_shape = None
    for case in cases:
        if type(case) is not dict or set(case) != {"args", "inputs", "expected"}: raise ToolRejected("試験ケースは args、inputs、expected が必要です")
        if type(case["args"]) is not dict or type(case["inputs"]) is not dict or type(case["expected"]) is not dict:
            raise ToolRejected("試験ケースの args、inputs、expected は object にしてください")
        result = engine.call("run", [case["args"], case["inputs"]]); _valid_result(result)
        if result != case["expected"]: raise ToolRejected("tameshi の結果が expected と一致しません")
        if args_shape is None and type(case["args"]) is dict:
            args_shape = {"type": "object", "properties": {key: _json_shape(value) for key, value in sorted(case["args"].items())},
                          "required": sorted(case["args"]), "additionalProperties": False}
        files = case["inputs"].get("files", []) if type(case["inputs"]) is dict else []
        if type(files) is list and any(type(file) is dict and "path" in file and "text" in file for file in files): reads_files = True
        for effect in result.get("effects", []):
            if type(effect.get("type")) is str: capabilities.add(effect["type"])
    return {"ok": True, "cases": len(cases), "capabilities": sorted(capabilities), "reads_files": reads_files,
            "args_shape": args_shape or {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}


def _json_shape(value: Any) -> dict:
    if value is None: return {"type": "null"}
    if type(value) is bool: return {"type": "boolean"}
    if type(value) is int: return {"type": "integer"}
    if type(value) is float: return {"type": "number"}
    if type(value) is str: return {"type": "string"}
    if type(value) is list: return {"type": "array", "items": _json_shape(value[0]) if value else {}}
    if type(value) is dict:
        return {"type": "object", "properties": {key: _json_shape(item) for key, item in sorted(value.items())},
                "required": sorted(value), "additionalProperties": False}
    raise ToolRejected("args の試験値に JSON 以外があります")


def _set_limits():
    limits = (("RLIMIT_CPU", 4), ("RLIMIT_FSIZE", MAX_OUTPUT_BYTES), ("RLIMIT_CORE", 0),
              ("RLIMIT_NOFILE", 32), ("RLIMIT_AS", 384 * 1024 * 1024))
    for name, wanted in limits:
        limit = getattr(resource, name, None)
        if limit is None:
            raise ToolRejected("必要な資源制限がありません: " + name)
        soft, hard = resource.getrlimit(limit)
        soft_cap = wanted if soft == resource.RLIM_INFINITY else min(wanted, soft)
        hard_cap = wanted if hard == resource.RLIM_INFINITY else min(wanted, hard)
        cap = min(soft_cap, hard_cap)
        try:
            resource.setrlimit(limit, (cap, cap))
        except (OSError, ValueError) as error:
            # macOS は RLIMIT_AS を受け付けない（9/26 Claude が外で試して判明）。メモリは 評価器の値の上限
            # （MAX_VALUE_BYTES）と 親の6秒の時間切れで守る。ほかの上限は必ずかける。
            if name == "RLIMIT_AS":
                continue
            raise ToolRejected("資源制限を設定できません: " + name) from error
        limited_soft, limited_hard = resource.getrlimit(limit)
        if limited_soft > wanted or limited_hard > wanted:
            raise ToolRejected("資源制限を確認できません: " + name)


def _self_test():
    valid = "def run(args, inputs):\n total=0\n for x in inputs['xs']:\n  if x > 0: total=total+x\n return {'result': total, 'effects': []}\ndef tameshi():\n return [{'args':{},'inputs':{'xs':[2,-1,4]},'expected':{'result':6,'effects':[]}}]"
    assert evaluate(valid, tests=True)["cases"] == 1
    assert evaluate(valid, {}, {"xs": [2, 4]})["result"] == 6
    rejects = [
        "import os\ndef run(args, inputs): return {}\ndef tameshi(): return []",
        "def run(args, inputs): return __import__('os')\ndef tameshi(): return []",
        "def run(args, inputs): return inputs.__class__\ndef tameshi(): return []",
        "def run(args, inputs): return open('/etc/passwd').read()\ndef tameshi(): return []",
        "def run(args, inputs):\n while True: pass\ndef tameshi(): return [{'args':{},'inputs':{},'expected':{}}]",
        "def run(args, inputs): return {'result':'x'*999999999,'effects':[]}\ndef tameshi(): return []",
    ]
    for source in rejects:
        try:
            tree = validate_source(source)
            if "while True" in source: _Evaluator(tree).call("run", [{}, {}])
            elif "*999999999" in source: _Evaluator(tree).call("run", [{}, {}])
        except (ToolRejected, MemoryError, ValueError):
            pass
        else: raise AssertionError("攻撃コードを拒否しませんでした")
    try:
        evaluate("def run(args, inputs): return {'result':0,'effects':[{'type':'write','path':'/private/kernel','text':'x'}]}\ndef tameshi(): return [{'args':{},'inputs':{},'expected':{'result':0,'effects':[]}}]", tests=True)
    except ToolRejected: pass
    else: raise AssertionError("未承認 effect を拒否しませんでした")


def _main():
    if sys.argv[1:] == ["--self-test"]:
        _self_test(); print("tsuika_worker: ok"); return 0
    try:
        _set_limits()
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES: raise ToolRejected("worker 入力が大きすぎます")
        data = json.loads(raw.decode("utf-8")); token = os.environ.get(_TOKEN_ENV, "")
        if not token or data.get("token") != token: raise ToolRejected("sandbox 呼び出し札が違います")
        output = json.dumps(evaluate(data.get("source"), data.get("args"), data.get("inputs"), tests=bool(data.get("tests"))), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(output.encode("utf-8")) > MAX_OUTPUT_BYTES: raise ToolRejected("worker 出力が大きすぎます")
        sys.stdout.write(output); return 0
    except Exception as error:
        sys.stderr.write(type(error).__name__ + ": " + str(error).replace("\n", " ")[:500] + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
