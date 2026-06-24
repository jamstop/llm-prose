"""Language detection, comment handling, and the re-parse scaffold for R2."""

from __future__ import annotations

import re

EXT_TO_LANG = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
}

# Some grammars reject bare statements at the top level, so a fragment must be
# wrapped before re-parsing for R2. "%s" means the fragment parses as-is.
REPARSE_SCAFFOLD = {
    "go": "package p\nfunc _() {\n%s\n}\n",
    "java": "class _ {\nvoid _() {\n%s\n}\n}\n",
    "c": "void _() {\n%s\n}\n",
    "cpp": "void _() {\n%s\n}\n",
    "rust": "fn _f() {\n%s\n}\n",
}

_MARKER = re.compile(r"^\s*(///?|#+|--+|;+|/\*+|\*+/?|\"\"\"|''')|(\*+/|\*/|\"\"\"|''')\s*$")


def language_for_path(path: str) -> str | None:
    for ext, lang in EXT_TO_LANG.items():
        if path.endswith(ext):
            return lang
    return None


def is_comment(node_kind: str) -> bool:
    return "comment" in node_kind


def strip_comment(text: str) -> str:
    """Remove comment markers and surrounding noise, returning the inner text."""
    lines = []
    for line in text.splitlines():
        prev = None
        while prev != line:
            prev = line
            line = _MARKER.sub("", line).strip()
        lines.append(line)
    return "\n".join(l for l in lines).strip()


def scaffold(language: str, fragment: str) -> str:
    return REPARSE_SCAFFOLD.get(language, "%s") % fragment
