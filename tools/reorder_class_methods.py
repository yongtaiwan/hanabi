#!/usr/bin/env python3
"""
Reorder class bodies: dunder methods (__init__ first), public methods, _-prefixed methods.
Preserves comments via ast.get_source_segment. Recurses into nested classes.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv"})


def is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def is_function(stmt: ast.stmt) -> bool:
    return isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))


def reorder_methods(methods: list[ast.FunctionDef | ast.AsyncFunctionDef]) -> list:
    dunders: list = []
    public: list = []
    private: list = []
    for m in methods:
        n = m.name
        if is_dunder(n):
            dunders.append(m)
        elif n.startswith("_"):
            private.append(m)
        else:
            public.append(m)
    inits = [m for m in dunders if m.name == "__init__"]
    rest_d = [m for m in dunders if m.name != "__init__"]
    return inits + rest_d + public + private


def partition_body(body: list[ast.stmt]) -> list[tuple[str, object]]:
    parts: list[tuple[str, object]] = []
    current: list = []
    for stmt in body:
        if is_function(stmt):
            current.append(stmt)
        else:
            if current:
                parts.append(("methods", current))
                current = []
            parts.append(("other", stmt))
    if current:
        parts.append(("methods", current))
    return parts


def node_first_line(node: ast.AST) -> int:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.decorator_list:
        return node.decorator_list[0].lineno
    return node.lineno


def node_lines_text(lines: list[str], node: ast.AST) -> str:
    """Exact source lines for *node* (includes class-body indentation; get_source_segment does not)."""
    start = node_first_line(node)
    end = node.end_lineno
    if end is None:
        raise RuntimeError(f"Missing end_lineno for {type(node).__name__}")
    return "".join(lines[start - 1 : end])


def stmt_start_line(stmt: ast.stmt) -> int:
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and stmt.decorator_list:
        return stmt.decorator_list[0].lineno
    return stmt.lineno


def rebuild_class(lines: list[str], cls: ast.ClassDef) -> str:
    if not cls.body:
        return node_lines_text(lines, cls)

    first_stmt_line = min(s.lineno for s in cls.body)
    dec_line = cls.decorator_list[0].lineno if cls.decorator_list else cls.lineno
    header = "".join(lines[dec_line - 1 : first_stmt_line - 1])

    parts = partition_body(cls.body)
    chunks: list[str] = []
    for kind, data in parts:
        if kind == "other":
            stmt = data
            if isinstance(stmt, ast.ClassDef):
                chunks.append(rebuild_class(lines, stmt))
            else:
                chunks.append(node_lines_text(lines, stmt))
        else:
            for m in reorder_methods(data):
                chunks.append(node_lines_text(lines, m))

    body = "\n\n".join(c.rstrip("\n") for c in chunks)
    return header + body + ("\n" if not body.endswith("\n") else "")


def rebuild_module(source: str, path: Path) -> str:
    tree = ast.parse(source, filename=str(path))
    if not tree.body:
        return source

    lines = source.splitlines(keepends=True)
    out: list[str] = []

    first = tree.body[0]
    start0 = stmt_start_line(first)
    out.append("".join(lines[0 : start0 - 1]))

    for i, stmt in enumerate(tree.body):
        if i > 0:
            prev = tree.body[i - 1]
            gap = "".join(lines[prev.end_lineno : stmt_start_line(stmt) - 1])
            out.append(gap)
        if isinstance(stmt, ast.ClassDef):
            out.append(rebuild_class(lines, stmt))
        else:
            out.append(node_lines_text(lines, stmt))

    last = tree.body[-1]
    out.append("".join(lines[last.end_lineno :]))
    return "".join(out)


def main(argv: list[str]) -> int:
    paths = sorted(
        p for p in ROOT.rglob("*.py") if not (SKIP_DIR_NAMES & frozenset(p.parts))
    )
    if argv[1:]:
        paths = [(ROOT / p).resolve() if not Path(p).is_absolute() else Path(p) for p in argv[1:]]
    changed = 0
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        try:
            new_text = rebuild_module(text, path)
        except SyntaxError as e:
            print(f"SKIP syntax {path}: {e}", file=sys.stderr)
            continue
        except RuntimeError as e:
            print(f"FAIL {path}: {e}", file=sys.stderr)
            return 1
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            print(path.relative_to(ROOT))
            changed += 1
    print(f"Updated {changed} file(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
