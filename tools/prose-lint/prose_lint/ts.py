"""Thin wrappers over tree-sitter-language-pack's method-style node API.

Every Node accessor in the Rust binding is a method (kind(), start_byte(), ...),
so `_call` collapses the method-or-attribute difference and the rest of the code
stays readable.
"""

from __future__ import annotations

from functools import lru_cache
from tree_sitter_language_pack import get_parser


def _call(x):
    return x() if callable(x) else x


@lru_cache(maxsize=None)
def _parser(language: str):
    return get_parser(language)


def parse(language: str, source: str):
    """Return (root_node, source_bytes) for source in the given language."""
    root = _parser(language).parse(source).root_node()
    return root, source.encode("utf-8")


def kind(node) -> str:
    return _call(node.kind)


def row(node) -> int:
    """Zero-based start line."""
    return _call(_call(node.start_position).row)


def text(node, source_bytes: bytes) -> str:
    return source_bytes[_call(node.start_byte) : _call(node.end_byte)].decode("utf-8", "replace")


def children(node):
    for i in range(_call(node.child_count)):
        yield node.child(i)


def field(node, name: str):
    try:
        return node.child_by_field_name(name)
    except Exception:
        return None


def has_error(node) -> bool:
    return bool(_call(node.has_error))


def walk(node):
    """Pre-order traversal yielding every node."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        kids = list(children(n))
        stack.extend(reversed(kids))
