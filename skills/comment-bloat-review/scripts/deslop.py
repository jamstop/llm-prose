#!/usr/bin/env python3
"""deslop — a zero-dependency, language-agnostic catcher for the deterministic
half of the comment-bloat rubric. Stdlib only, single file, no install: it ships
inside the skill and runs with whatever python3 is on the box.

It deliberately covers only the two rules a regex/stdlib parser can decide
*without judgment*:

  R1  notes-to-self / LLM residue   — the model talking to itself or the reviewer
  R2  commented-out code            — dead code left in a comment

Everything that needs judgment (narration vs. why, doc-dump tightening, staleness)
is left to the comment-bloat-review skill. See RULES.md for the catalog.

Usage:
  python3 deslop.py path/to/file.py ...        # lint whole files
  git diff | python3 deslop.py --diff          # lint only added comment lines
  python3 deslop.py --format json src/file.go  # machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass

# --- language profiles -------------------------------------------------------
# A profile says how to find comments in a file: line markers, block-comment
# pairs, the string delimiters whose contents must be ignored (so a `#` or `//`
# inside a string never fires), and optionally `char` — a `'` that is a char/rune
# literal, not a string. The distinction matters: in Rust/Go/C a lone `'` is a
# lifetime/label or part of a literal, NOT the start of a string, so treating it
# as a string opener would swallow a trailing `//` comment on the same line.

# JS/TS: `'`, `"`, and backtick are all real string delimiters.
_JS = {"line": ["//"], "block": [("/*", "*/")], "strings": ['"', "'", "`"]}
# Rust/Go/C/C++/Java/Kotlin/Scala: `"`/backtick are strings; `'` is a char/rune
# literal, validated by pattern so a bare lifetime tick is left as ordinary text.
_CHARLIT = {"line": ["//"], "block": [("/*", "*/")], "strings": ['"', "`"], "char": "'"}
# Swift has no single-quote literal at all; just `"` and `"""`.
_SWIFT = {"line": ["//"], "block": [("/*", "*/")], "strings": ['"'], "triple": ['"""']}

_PROFILES = {
    "python": {"line": ["#"], "block": [], "strings": ['"', "'"], "triple": ['"""', "'''"]},
    "ruby": {"line": ["#"], "block": [], "strings": ['"', "'"]},
    "shell": {"line": ["#"], "block": [], "strings": ['"', "'"]},
    "yaml": {"line": ["#"], "block": [], "strings": ['"', "'"]},
    "sql": {"line": ["--"], "block": [("/*", "*/")], "strings": ["'"]},
    "lua": {"line": ["--"], "block": [], "strings": ['"', "'"]},
    "javascript": _JS, "typescript": _JS, "tsx": _JS,
    "go": _CHARLIT, "rust": _CHARLIT, "java": _CHARLIT, "kotlin": _CHARLIT,
    "scala": _CHARLIT, "c": _CHARLIT, "cpp": _CHARLIT,
    "swift": _SWIFT,
}

# A char/rune literal: a single char or an escape (incl. \xNN, \u{...}) in quotes.
# A bare `'` not matching this (a Rust lifetime `'a`, a label) is ordinary text.
_CHAR_LITERAL = re.compile(r"'(?:\\(?:x[0-9A-Fa-f]{1,8}|u\{[0-9A-Fa-f]+\}|.)|[^'\\\n])'")

_EXT_TO_LANG = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".scala": "scala",
    ".rb": "ruby", ".swift": "swift", ".sh": "shell", ".bash": "shell",
    ".yaml": "yaml", ".yml": "yaml", ".sql": "sql", ".lua": "lua",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp", ".cxx": "cpp",
}


def language_for_path(path: str) -> str | None:
    for ext, lang in _EXT_TO_LANG.items():
        if path.endswith(ext):
            return lang
    return None


# --- comment extraction ------------------------------------------------------
# A small character scanner that walks the source once, skipping string and
# triple-quoted literals so comment markers inside them don't fire. Returns
# (1-based start line, inner text) for every comment.


def extract_comments(text: str, profile: dict) -> list[tuple[int, str]]:
    line_markers = profile["line"]
    block_pairs = profile.get("block", [])
    strings = profile.get("strings", ['"', "'"])
    triples = profile.get("triple", [])
    char_quote = profile.get("char")
    comments: list[tuple[int, str]] = []
    i, n, line = 0, len(text), 1

    def startswith_any(seqs):
        return next((s for s in seqs if text.startswith(s, i)), None)

    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        triple = startswith_any(triples)
        if triple:
            i += len(triple)
            while i < n and not text.startswith(triple, i):
                if text[i] == "\n":
                    line += 1
                i += 1
            i += len(triple)
            continue
        if ch == char_quote:
            m = _CHAR_LITERAL.match(text, i)
            # A real char/rune literal: skip it. A bare tick (lifetime/label):
            # advance one char so it never opens a phantom string.
            i += m.end() - i if m else 1
            continue
        if ch in strings:
            i += 1
            while i < n and text[i] != ch:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "\n":
                    line += 1
                i += 1
            i += 1
            continue
        pair = next(((o, c) for (o, c) in block_pairs if text.startswith(o, i)), None)
        if pair:
            opener, closer = pair
            start, i = line, i + len(opener)
            buf = []
            while i < n and not text.startswith(closer, i):
                if text[i] == "\n":
                    line += 1
                buf.append(text[i])
                i += 1
            i += len(closer)
            comments.append((start, "".join(buf)))
            continue
        marker = startswith_any(line_markers)
        if marker:
            start, i = line, i + len(marker)
            buf = []
            while i < n and text[i] != "\n":
                buf.append(text[i])
                i += 1
            comments.append((start, "".join(buf)))
            continue
        i += 1
    return comments


def _clean(text: str) -> str:
    """Drop per-line block-continuation noise (leading `*`) and trim."""
    return "\n".join(re.sub(r"^\s*\*+\s?", "", ln).strip() for ln in text.splitlines()).strip()


# --- R1: notes-to-self / LLM residue -----------------------------------------

# Unambiguous residue phrases, matched anywhere in the comment.
_RESIDUE = re.compile(
    r"""
    \bas\ requested\b
  | \bas\ you\ (?:asked|requested)\b
  | \bper\ (?:your\ |the\ )?feedback\b
  | \bper\ review\b
  | \bnote:\ I\b
  | \bas\ a\ reminder\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Edit-narration reads as residue only when it *leads* the comment; the same
# verbs mid-sentence ("the digest I compute") are ordinary descriptive prose,
# so this is anchored to the start. Bare version/date mentions are deliberately
# excluded — they false-positive on why-comments that cite an API version or a
# deprecation date.
_RESIDUE_LEAD = re.compile(
    r"""
    ^I\ (?:changed|added|updated|removed|renamed|refactored|made|fixed)\b
  | ^updated\ to\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _is_residue(text: str) -> bool:
    cleaned = _clean(text)
    return bool(_RESIDUE.search(cleaned) or _RESIDUE_LEAD.match(cleaned))


# --- R2: commented-out code --------------------------------------------------

_PROSE_MARKER = re.compile(r"^(TODO|FIXME|NOTE|HACK|XXX|WARNING|WARN)\b", re.IGNORECASE)

# Tool directives / pragmas are special comments, not commented-out code — but
# many have a `key=value` or `key: value` shape that reads as code (e.g.
# `shellcheck disable=SC2012`, `type: ignore`). Skip them. (Found by dogfooding
# on a real PR, where `# shellcheck disable=SC2012` was flagged as dead code.)
_DIRECTIVE = re.compile(
    r"""^(?:
        shellcheck\b
      | noqa\b
      | type:\s*ignore\b
      | (?:pylint|flake8|mypy|ruff|pragma|isort|coverage|yapf|swiftlint):
      | fmt:\s*(?:on|off)\b
      | yamllint\b
      | nolint\b | nolintnextline\b
      | istanbul\s+ignore\b
      | (?:biome|prettier)-ignore\b
      | eslint-(?:disable|enable)
      | @ts-(?:ignore|expect-error|nocheck)\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# Heuristic code signals for non-Python languages. An assignment (one `=`, not
# `==`/`<=`/etc., with an optional type/decl word: `const x =`, `int n =`) or a
# bare call statement. Python is parsed precisely with stdlib `ast` instead.
_CODE_ASSIGN = re.compile(
    r"^[A-Za-z_$][\w.$<>\[\]]*(?:\s+[A-Za-z_$][\w.$<>\[\]]*)?\s*(?:[-+*/%&|^]?=(?!=)|:=)\s*\S"
)
_CODE_CALL = re.compile(r"^[A-Za-z_$][\w.$]*\s*\(.*\)\s*;?\s*$")
_ASSIGN_OP = re.compile(r"[-+*/%&|^]?=(?!=)|:=")
# The right-hand side must look like an expression, not prose: a call/index, an
# operator, a member access, a quote, or a number. Without this, `key = value`
# prose ("default = usd", "timeout = how long we wait") read as commented-out
# code — a precision miss this tool exists to avoid.
_RHS_CODE_SIGNAL = re.compile(r"[(\[]|[-+*/%<>&|^~]|\.\w|['\"]|\d")


def _py_is_code(fragment: str) -> bool:
    import ast
    import textwrap

    try:
        tree = ast.parse(textwrap.dedent(fragment))
    except (SyntaxError, ValueError):
        return False
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign,
                             ast.Import, ast.ImportFrom, ast.For, ast.While,
                             ast.With, ast.If, ast.Delete)):
            return True
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return True
    return False


def _line_is_code(line: str, language: str) -> bool:
    stripped = line.strip()
    frag = stripped.rstrip(";")
    if len(frag) < 4:
        return False
    if language == "python":
        return _py_is_code(stripped)
    if _CODE_CALL.match(stripped):
        return True
    if _CODE_ASSIGN.match(frag):
        parts = _ASSIGN_OP.split(frag, maxsplit=1)
        rhs = parts[1] if len(parts) > 1 else ""
        return bool(_RHS_CODE_SIGNAL.search(rhs))
    return False


def _is_exempt(line: str) -> bool:
    """A prose marker (TODO/...) or a tool directive (shellcheck/noqa/...) — not code."""
    return bool(_PROSE_MARKER.match(line) or _DIRECTIVE.match(line))


def _is_commented_code(text: str, language: str) -> bool:
    cleaned = _clean(text)
    if not cleaned or _is_exempt(cleaned):
        return False
    return any(_line_is_code(ln, language) for ln in cleaned.splitlines()
               if ln.strip() and not _is_exempt(ln.strip()))


# --- findings & rule runners -------------------------------------------------


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    action: str
    message: str

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "rule": self.rule,
                "action": self.action, "message": self.message}


_RULES = {
    "notes-to-self": (_is_residue, "delete",
                      "comment is a note-to-self / LLM residue; delete"),
    "commented-out-code": (_is_commented_code, "delete",
                           "comment body reads as code; delete (it's in git history)"),
}


def lint_source(path: str, source: str, language: str, enabled=None) -> list[Finding]:
    profile = _PROFILES.get(language)
    if profile is None:
        return []
    findings: list[Finding] = []
    for start, text in extract_comments(source, profile):
        for rule, (predicate, action, message) in _RULES.items():
            if enabled and rule not in enabled:
                continue
            hit = predicate(text, language) if rule == "commented-out-code" else predicate(text)
            if hit:
                findings.append(Finding(path, start, rule, action, message))
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def lint_path(path: str, enabled=None) -> list[Finding]:
    language = language_for_path(path)
    if language is None:
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return lint_source(path, fh.read(), language, enabled)


# --- unified-diff scope ------------------------------------------------------

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added_lines(diff: str) -> dict[str, set[int]]:
    """Map each file to the set of line numbers added in the new revision."""
    result: dict[str, set[int]] = {}
    path, new_line = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            path = None if target == "/dev/null" else re.sub(r"^b/", "", target)
        elif line.startswith("--- ") or line.startswith("diff "):
            continue
        elif (m := _HUNK.match(line)):
            new_line = int(m.group(1))
        elif path is None:
            continue
        elif line.startswith("+"):
            result.setdefault(path, set()).add(new_line)
            new_line += 1
        elif line.startswith("-") or line.startswith("\\"):
            continue
        else:
            new_line += 1
    return result


# --- CLI ---------------------------------------------------------------------


def _emit_text(findings) -> None:
    for f in findings:
        print(f"{f.file}:{f.line}: [{f.rule}/{f.action}] {f.message}")
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.rule] = counts.get(f.rule, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
    print(f"--- {len(findings)} finding(s): {summary}", file=sys.stderr)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="deslop",
        description="Zero-dependency deterministic catcher for LLM residue and commented-out code.",
    )
    p.add_argument("paths", nargs="*", help="files to lint")
    p.add_argument("--diff", action="store_true",
                   help="read a unified diff on stdin; lint only added comment lines")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--rules", help="comma-separated subset of: " + ",".join(_RULES))
    p.add_argument("--max", type=int, default=0,
                   help="max allowed findings before non-zero exit (default 0)")
    args = p.parse_args(argv)

    enabled = set(args.rules.split(",")) if args.rules else None
    findings: list[Finding] = []
    if args.diff:
        for path, lines in added_lines(sys.stdin.read()).items():
            if language_for_path(path) is None:
                continue
            try:
                file_findings = lint_path(path, enabled)
            except (FileNotFoundError, OSError):
                continue
            findings.extend(f for f in file_findings if f.line in lines)
    else:
        for path in args.paths:
            findings.extend(lint_path(path, enabled))

    findings.sort(key=lambda f: (f.file, f.line, f.rule))
    if args.format == "json":
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        _emit_text(findings)
    return 1 if len(findings) > args.max else 0


if __name__ == "__main__":
    raise SystemExit(main())
