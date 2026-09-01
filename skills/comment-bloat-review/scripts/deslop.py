#!/usr/bin/env python3
"""deslop — a zero-dependency, language-agnostic catcher for the deterministic
half of the comment-bloat rubric. Stdlib only, single file, no install: it ships
inside the skill and runs with whatever python3 is on the box.

It covers conservative deterministic rules for residue, numbered scaffolding,
obvious adjacent-code narration, commented-out code, generated files, and PR
body debris. Judgment-heavy doc tightening, staleness, and intent remain in the
comment-bloat-review skill. See RULES.md for the catalog.

Usage:
  python3 deslop.py path/to/file.py ...        # lint whole files
  git diff | python3 deslop.py --diff          # lint only added comment lines
  python3 deslop.py --body-file pr-body.md     # lint a PR description
  python3 deslop.py --format json src/file.go  # machine-readable
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import stat
import sys
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path

_MAX_SOURCE_BYTES = 2 * 1024 * 1024

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
_SWIFT = {
    "line": ["//"], "block": [("/*", "*/")], "strings": ['"'],
    "triple": ['"""'], "extended_raw": True, "nested_blocks": True,
}

_PROFILES = {
    "python": {"line": ["#"], "block": [], "strings": ['"', "'"], "triple": ['"""', "'''"]},
    "ruby": {"line": ["#"], "block": [], "strings": ['"', "'"]},
    "shell": {"line": ["#"], "block": [], "strings": ['"', "'"]},
    "yaml": {"line": ["#"], "block": [], "strings": ['"', "'"]},
    "sql": {"line": ["--"], "block": [("/*", "*/")], "strings": ["'"]},
    "lua": {"line": ["--"], "block": [], "strings": ['"', "'"]},
    "javascript": _JS, "typescript": _JS, "tsx": _JS,
    "go": _CHARLIT,
    "rust": {**_CHARLIT, "nested_blocks": True},
    "java": _CHARLIT,
    "kotlin": {**_CHARLIT, "nested_blocks": True},
    "scala": {**_CHARLIT, "nested_blocks": True},
    "c": _CHARLIT, "cpp": _CHARLIT,
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


def _read_source(path: str | Path) -> str:
    target = Path(path)
    metadata = target.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError(f"{target} is not a regular file")
    if metadata.st_size > _MAX_SOURCE_BYTES:
        raise OSError(f"{target} exceeds {_MAX_SOURCE_BYTES} bytes")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise OSError(f"{target} changed while opening")
        if not stat.S_ISREG(opened.st_mode):
            raise OSError(f"{target} is not a regular file")
        if opened.st_size > _MAX_SOURCE_BYTES:
            raise OSError(f"{target} exceeds {_MAX_SOURCE_BYTES} bytes")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(_MAX_SOURCE_BYTES + 1)
        if len(payload) > _MAX_SOURCE_BYTES:
            raise OSError(f"{target} exceeds {_MAX_SOURCE_BYTES} bytes")
    finally:
        os.close(descriptor)
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OSError(f"{target} is not UTF-8 text") from error


# --- comment extraction ------------------------------------------------------
# A small character scanner that walks the source once, skipping string and
# triple-quoted literals so comment markers inside them don't fire. Returns
# (1-based start line, inner text) for every comment.


@dataclass(frozen=True)
class Comment:
    line: int
    text: str
    trailing: bool = False


def extract_comments(text: str, profile: dict) -> list[Comment]:
    line_markers = profile["line"]
    block_pairs = profile.get("block", [])
    strings = profile.get("strings", ['"', "'"])
    triples = profile.get("triple", [])
    char_quote = profile.get("char")
    comments: list[Comment] = []
    i, n, line = 0, len(text), 1

    def startswith_any(seqs):
        return next((s for s in seqs if text.startswith(s, i)), None)

    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if profile.get("extended_raw") and ch == "#":
            raw_quote = re.match(r'(#+)("""|"|/)', text[i:])
            if raw_quote:
                closing = raw_quote.group(2) + raw_quote.group(1)
                i += len(raw_quote.group(0))
                while i < n and not text.startswith(closing, i):
                    if text[i] == "\\" and i + 1 < n:
                        line += text[i + 1] == "\n"
                        i += 2
                        continue
                    line += text[i] == "\n"
                    i += 1
                i += len(closing)
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
            start = line
            line_start = text.rfind("\n", 0, i) + 1
            trailing = bool(text[line_start:i].strip())
            i += len(opener)
            buf = []
            depth = 1
            while i < n and depth:
                if profile.get("nested_blocks") and text.startswith(opener, i):
                    depth += 1
                    buf.append(opener)
                    i += len(opener)
                    continue
                if text.startswith(closer, i):
                    depth -= 1
                    if not depth:
                        i += len(closer)
                        break
                    buf.append(closer)
                    i += len(closer)
                    continue
                if text[i] == "\n":
                    line += 1
                buf.append(text[i])
                i += 1
            comments.append(Comment(start, "".join(buf), trailing))
            continue
        marker = startswith_any(line_markers)
        if marker:
            start = line
            line_start = text.rfind("\n", 0, i) + 1
            trailing = bool(text[line_start:i].strip())
            i += len(marker)
            buf = []
            while i < n and text[i] != "\n":
                buf.append(text[i])
                i += 1
            comments.append(Comment(start, "".join(buf), trailing))
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
  | \bas\ discussed\b(?!\s+in\b)
  | \bper\ (?:our|the)\ (?:conversation|discussion|chat)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_STEP_SCAFFOLD = re.compile(r"^step\s*\d+\s*[:.\-]", re.IGNORECASE | re.MULTILINE)

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

_NARRATION_LEAD = re.compile(
    r"^(?:set|get|create|add|remove|update|return|call|send|make|check(?: if)?|"
    r"initialize|init|start|stop|fetch|load|save|store|handle|register)\b[^,;]{0,60}$",
    re.IGNORECASE,
)
_NARRATION_RATIONALE = re.compile(
    r"\b(?:because|since|so that|avoid|prevent|otherwise|must|workaround|instead|"
    r"race|deadlock|gotcha|invariant|safety|based on|ensur(?:e|es|ing)|"
    r"guard against|fall(?:s|ing|en)?\s*back|defer|"
    r"to (?:match|keep|align|preserve|maintain|sync))\b",
    re.IGNORECASE,
)
_NARRATION_STOPWORDS = frozenset(
    "the and for with from this that when are our its all any new old out".split()
)
_IDENT_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z][a-z0-9]*")
_INFLECTIONS = frozenset(("s", "es", "d", "ed", "ing", "r", "rs"))


def _words(text: str) -> set[str]:
    return {word.lower() for word in _IDENT_WORD.findall(text) if len(word) >= 3}


def _same_word(left: str, right: str) -> bool:
    if left == right:
        return True
    base, longer = sorted((left, right), key=len)
    if len(base) >= 4 and base.endswith("y") and longer == f"{base[:-1]}ies":
        return True
    if len(base) < 4 or not longer.startswith(base):
        return False
    return longer[len(base):] in _INFLECTIONS


def _restates_next_code(cleaned: str, source_lines: list[str],
                        last_comment_line: int) -> bool:
    if "\n" in cleaned or not _NARRATION_LEAD.match(cleaned) or _NARRATION_RATIONALE.search(cleaned):
        return False
    tokens = _words(cleaned) - _NARRATION_STOPWORDS
    lead = re.match(r"[a-z]+", cleaned.lower())
    if lead:
        tokens.discard(lead.group())
    if not tokens:
        return False
    for candidate in source_lines[last_comment_line:last_comment_line + 3]:
        stripped = candidate.strip()
        if not stripped or stripped.startswith(("//", "#", "--", "/*", "*")):
            continue
        words = _words(stripped)
        return any(_same_word(token, word) for token in tokens for word in words)
    return False


def _fenced_line_comment_lines(comments: list[Comment], source_lines: list[str],
                               profile: dict) -> set[int]:
    """Physical lines inside consecutive line-comment Markdown fences."""
    fenced: set[int] = set()
    in_fence = False
    previous_line: int | None = None
    for comment in comments:
        own_line = source_lines[comment.line - 1].lstrip()
        marker = next((item for item in profile["line"] if own_line.startswith(item)), None)
        consecutive = previous_line is not None and comment.line == previous_line + 1
        if marker is None or "\n" in comment.text or (previous_line is not None and not consecutive):
            in_fence = False
        if marker is None or "\n" in comment.text:
            previous_line = None
            continue
        cleaned = comment.text.strip()
        if marker == "//":
            cleaned = cleaned.lstrip("/!").lstrip()
        if cleaned.startswith(("```", "~~~")):
            in_fence = not in_fence
        elif in_fence:
            fenced.add(comment.line)
        previous_line = comment.line
    return fenced


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
        Code\ generated\ .*\ DO\ NOT\ EDIT\.$
      | >\s*using\b
      | \#?cgo\b
      | shellcheck\b
      | noqa\b
      | type:
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
_CODE_CALL = re.compile(
    r"^[A-Za-z_$][\w.$]*(?:\(.*\)\s*;?|\s+\(.*\)\s*;)\s*$"
)
_ASSIGN_OP = re.compile(r"[-+*/%&|^]?=(?!=)|:=")
# The right-hand side must look like an expression, not prose: a call/index, an
# operator, a member access, a quote, or a number. Without this, `key = value`
# prose ("default = usd", "timeout = how long we wait") read as commented-out
# code — a precision miss this tool exists to avoid.
_RHS_CODE_SIGNAL = re.compile(r"[(\[]|[-+*/%<>&|^~]|\.\w|['\"]|\d")

# A comment that reads as an English sentence is prose, not commented-out code —
# even when it carries an `=` and a parenthetical that looks expression-ish, e.g.
# "Pass = every run. Smoke test (LLM + network), not a gate." Gate the non-Python
# assignment heuristic on these natural-language tells. (Python is parsed by ast,
# which already rejects prose, so this only guards the regex path.)
_PROSE_SENTENCE = re.compile(
    r"[a-z]\.\s+[A-Z]"                                              # "... run. Smoke ..."
    r"|[a-z]{2}\.\s*$"                                              # "... a CI gate."
    r"|,\s+(?:not|but|so|which|because|instead|rather|unless|otherwise)\b"
)

# An env-var-prefixed command (`MODEL=foo bash run.sh`, `DEBUG=1 ./x`) inside a
# comment is almost always a usage example, not dead code. A real one-line
# assignment (`x = foo()`, `total=amount*100`) has no trailing command token, so
# it stays caught — the `=` must be glued to the name and a second token must
# follow a space.
_USAGE_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S+\s+\S")
def _py_is_code(fragment: str) -> bool:
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
    if _PROSE_SENTENCE.search(stripped):
        return False
    if _CODE_CALL.match(stripped):
        return True
    if _CODE_ASSIGN.match(frag):
        parts = _ASSIGN_OP.split(frag, maxsplit=1)
        rhs = parts[1] if len(parts) > 1 else ""
        first_value = rhs.split(",", maxsplit=1)[0]
        return bool(_RHS_CODE_SIGNAL.search(first_value))
    return False


def _is_exempt(line: str) -> bool:
    """A prose marker (TODO/...), a tool directive (shellcheck/noqa/...), or an
    env-prefixed usage example (`VAR=val cmd`) — none are commented-out code."""
    return bool(_PROSE_MARKER.match(line) or _DIRECTIVE.match(line) or _USAGE_ENV.match(line))


def _is_commented_code(text: str, language: str) -> bool:
    cleaned = _clean(text)
    if not cleaned or _is_exempt(cleaned):
        return False
    in_fence = False
    for line in cleaned.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or _is_exempt(stripped):
            continue
        if _line_is_code(stripped, language):
            return True
    return False


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

_GENERATED = re.compile(r"Code generated|DO NOT EDIT|@generated|Generated by", re.IGNORECASE)
_GENERATED_PATH = re.compile(r"(?:^|/)Generated/")


def _body_lines(comment: Comment) -> list[tuple[int, str]]:
    """Return physical source lines for a comment body.

    Block-comment findings use the line containing the offending text, rather
    than pinning every result to the opener.
    """
    lines = comment.text.splitlines() or [comment.text]
    return [(comment.line + offset, re.sub(r"^\s*\*+\s?", "", text).strip())
            for offset, text in enumerate(lines)]


def lint_source(path: str, source: str, language: str, enabled=None) -> list[Finding]:
    profile = _PROFILES.get(language)
    if profile is None:
        return []
    source_lines = source.splitlines()
    header = "\n".join(source_lines[:5])
    generated_header = any(
        _GENERATED.search(comment.text)
        for comment in extract_comments(header, profile)
    )
    if _GENERATED_PATH.search(path) or generated_header:
        return []
    comments = extract_comments(source, profile)
    fenced_lines = _fenced_line_comment_lines(comments, source_lines, profile)
    findings: list[Finding] = []
    for comment in comments:
        parts = _body_lines(comment)
        code_lines: set[int] = set()
        in_fence = False
        for physical_line, text in parts:
            if text.startswith(("```", "~~~")):
                in_fence = not in_fence
            elif in_fence:
                fenced_lines.add(physical_line)
            elif physical_line not in fenced_lines and _is_commented_code(text, language):
                code_lines.add(physical_line)
        last_comment_line = comment.line + comment.text.count("\n")
        for physical_line, text in parts:
            if not text or physical_line in fenced_lines:
                continue
            if (not enabled or "notes-to-self" in enabled) and _is_residue(text):
                findings.append(Finding(
                    path, physical_line, "notes-to-self", "delete",
                    _RULES["notes-to-self"][2],
                ))
            if (not enabled or "step-scaffold" in enabled) and _STEP_SCAFFOLD.search(text):
                findings.append(Finding(
                    path, physical_line, "step-scaffold", "tighten",
                    "numbered step scaffold; keep only a non-obvious clause",
                ))
            if (
                (not enabled or "commented-out-code" in enabled)
                and (not comment.trailing or physical_line > comment.line)
                and physical_line in code_lines
            ):
                findings.append(Finding(
                    path, physical_line, "commented-out-code", "delete",
                    _RULES["commented-out-code"][2],
                ))
            if (
                (not enabled or "narration" in enabled)
                and (not comment.trailing or physical_line > comment.line)
                and _restates_next_code(text, source_lines, last_comment_line)
            ):
                findings.append(Finding(
                    path, physical_line, "narration", "tighten",
                    "comment restates adjacent code; delete or keep only a non-obvious clause",
                ))
    findings = list(dict.fromkeys(findings))
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def lint_path(path: str, enabled=None) -> list[Finding]:
    language = language_for_path(path)
    if language is None:
        return []
    return lint_source(path, _read_source(path), language, enabled)


# --- PR-description lint ----------------------------------------------------

_BODY_PATH = "PR description"
_EMPTY_IMG = re.compile(r'<img\s[^>]*src=""', re.IGNORECASE)
_TEMPLATE_COMMENT = re.compile(
    r"<!--\s*(?:TODO|PLACEHOLDER|add |describe |explain |insert |"
    r"optional:|screenshots?\b|testing\b)",
    re.IGNORECASE,
)
_INLINE_CODE = re.compile(r"`[^`]*`")
_CHECKBOX = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s")
_HEADING = re.compile(r"^#{1,6}\s+\S")
_FILLER = re.compile(
    r"\b(comprehensive|robust|seamless(?:ly)?|enhanced|streamlined?)\b",
    re.IGNORECASE,
)
_POLITENESS = re.compile(r"\b(simply|easily|please note|note that)\b", re.IGNORECASE)


def lint_body(body: str, enabled=None) -> list[Finding]:
    """Lint deterministic PR-body debris without assuming a host template."""
    findings: list[Finding] = []
    boxes: list[tuple[int, str]] = []
    lines = body.splitlines()
    fenced: set[int] = set()
    in_fence = False
    for index, line in enumerate(lines, 1):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            fenced.add(index)
        elif in_fence:
            fenced.add(index)

    headings = [
        index for index, line in enumerate(lines, 1)
        if index not in fenced and _HEADING.match(line)
    ]
    for position, start in enumerate(headings):
        end = headings[position + 1] - 1 if position + 1 < len(headings) else len(lines)
        if all(not lines[index].strip() for index in range(start, end)):
            findings.append(Finding(
                _BODY_PATH, start, "template-debris", "tighten",
                "empty section; add content, mark it not applicable, or remove it if optional",
            ))

    for index, raw_line in enumerate(lines, 1):
        if index in fenced:
            continue
        line = _INLINE_CODE.sub(" ", raw_line)
        if _EMPTY_IMG.search(line):
            findings.append(Finding(
                _BODY_PATH, index, "template-debris", "delete",
                "empty media placeholder; fill it in or remove it",
            ))
        if _TEMPLATE_COMMENT.search(line):
            findings.append(Finding(
                _BODY_PATH, index, "template-debris", "delete",
                "leftover authoring placeholder; fill it in or remove it",
            ))
        if _RESIDUE.search(line):
            findings.append(Finding(
                _BODY_PATH, index, "notes-to-self", "delete",
                "session residue in description; delete",
            ))
        if match := _FILLER.search(line):
            findings.append(Finding(
                _BODY_PATH, index, "filler-adjective", "tighten",
                f"filler adjective '{match.group(1)}'; replace it with a concrete fact or delete it",
            ))
        if match := _POLITENESS.search(line):
            findings.append(Finding(
                _BODY_PATH, index, "politeness", "tighten",
                f"'{match.group(1)}' adds no information; state the instruction directly",
            ))
        if match := _CHECKBOX.match(line):
            boxes.append((index, match.group(1)))
    if len(boxes) >= 2 and all(state == " " for _, state in boxes):
        findings.append(Finding(
            _BODY_PATH, boxes[0][0], "unchecked-checklist", "tighten",
            "checklist has no checked items; state what was verified or remove it",
        ))
    if enabled:
        findings = [finding for finding in findings if finding.rule in enabled]
    return sorted(findings, key=lambda finding: (finding.line, finding.rule))


# --- unified-diff scope ------------------------------------------------------

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added_lines(diff: str) -> dict[str, set[int]]:
    """Map each file to the set of line numbers added in the new revision."""
    result: dict[str, set[int]] = {}
    path, new_line = None, 0
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path, in_hunk = None, False
        elif not in_hunk and line.startswith("+++ "):
            target = line[4:].strip()
            path = (
                None
                if target == "/dev/null" or target.startswith('"')
                else re.sub(r"^b/", "", target)
            )
        elif not in_hunk and line.startswith("--- "):
            continue
        elif (m := _HUNK.match(line)):
            in_hunk = True
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
    available_rules = sorted({
        *_RULES,
        "step-scaffold", "narration", "template-debris",
        "filler-adjective", "politeness", "unchecked-checklist",
    })
    p = argparse.ArgumentParser(
        prog="deslop",
        description="Zero-dependency deterministic prose lint.",
    )
    p.add_argument("paths", nargs="*", help="files to lint")
    p.add_argument("--diff", action="store_true",
                   help="read a unified diff on stdin; lint only added comment lines")
    p.add_argument("--body-file", help="lint a PR description body from this file")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--rules", help="comma-separated subset of: " + ",".join(available_rules))
    p.add_argument("--max", type=int, default=0,
                   help="max allowed findings before non-zero exit (default 0)")
    args = p.parse_args(argv)

    enabled = set(args.rules.split(",")) if args.rules else None
    findings: list[Finding] = []
    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as fh:
            findings.extend(lint_body(fh.read(), enabled))
    if args.diff:
        missing = []
        for path, lines in added_lines(sys.stdin.read()).items():
            if language_for_path(path) is None:
                continue
            try:
                file_findings = lint_path(path, enabled)
            except (FileNotFoundError, OSError):
                missing.append(path)
                continue
            findings.extend(f for f in file_findings if f.line in lines)
        if missing:
            # --diff lints the files on disk (the diff alone lacks full-file
            # context), so a diff from a branch that isn't checked out would
            # otherwise "pass" silently. Make the gap loud.
            print(f"deslop: {len(missing)} file(s) in the diff not found on disk — "
                  f"findings are incomplete; check out the branch first: "
                  + ", ".join(missing), file=sys.stderr)
    else:
        for path in args.paths:
            findings.extend(lint_path(path, enabled))

    findings.sort(key=lambda f: (f.file, f.line, f.rule))
    if args.format == "json":
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        _emit_text(findings)
    return 1 if len(findings) > args.max else 0


if __name__ == "__main__":
    raise SystemExit(main())
