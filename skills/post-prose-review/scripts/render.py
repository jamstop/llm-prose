#!/usr/bin/env python3
"""Render prose findings as a safe GitHub review.

Only edits proven to replace complete comment-only lines become suggestion
blocks. Invalid findings are dropped; unsafe edits become ordinary review
comments. The module is stdlib-only so skills can use it without installing
the host project's dependencies.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import subprocess
import sys
import tokenize
import unicodedata
from pathlib import Path
from typing import Any

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_ACTIONS = {"delete", "tighten", "move"}
# `@`-tags that JSX transforms, test runners, minifiers, and `tsc --checkJs`
# read from any comment, including the interior lines of a docblock.
_ANNOTATION = (
    r"@(?:jsx\w*|jest-environment|vitest-environment|format|flow|generated|"
    r"preserve|license|refresh|ts-\w+|type|typedef|template|param|returns?|"
    r"satisfies|import|callback|this|extends|augments|implements|enum|"
    r"deprecated|internal|module|exports)\b"
)
# Markers whose casing the compiler or its tools check, so prose that happens
# to use the same words (`// output: ...`, `// +1 ...`) is not one.
_COMPILER_DIRECTIVE = re.compile(
    r"^(?:#!|#.*\bcoding[:=]|"
    # `// +build`, `// +kubebuilder:`, `// +k8s:`: Go build tags and marker
    # comments that code generators read. `// Output:` is compared by
    # `go test`; `// Deprecated:` and `// BUG(` are read by the doc tools.
    r"///\s*<(?:reference|amd-)|//>|//go:|//\s*\+[A-Za-z]|//line\b|"
    r"//extern\b|//export\b|//sys\b|//\s*#cgo\b|#cgo\b|"
    r"//\s*(?:Output|Unordered output):|//\s*Deprecated:|//\s*BUG\(|"
    r"// Code generated .* DO NOT EDIT\.$|#\s*type:|//#|//@)"
)
_TOOL_DIRECTIVE = re.compile(
    r"^(?:"
    r"//\s*(?:swift-tools-version:|swift-format-(?:ignore|ignore-file)\b|"
    r"swiftformat:|swiftlint:|sourcery:|periphery:|"
    r"eslint-(?:disable|enable)(?:-next-line|-line)?\b|eslint-env\b|"
    r"biome-ignore(?:-all)?\b|prettier-ignore\b|istanbul\s+ignore\b|"
    r"c8\s+ignore\b|v8\s+ignore\b|tslint:|deno-lint-ignore\b|oxlint-|"
    r"deno-fmt-ignore\b|dprint-ignore\b|" + _ANNOTATION + r"|"
    r"NOSONAR\b|codeql\[|lgtm\s*\[|"
    r"ktlint-(?:disable|enable)\b|@formatter:|\$COVERAGE-(?:IGNORE|OFF|ON)\$|"
    r"scalafmt:|scalastyle:|scalafix:|format:\s*(?:off|on)\b|"
    r"noinspection\b|goland:|clang-format\b|NOLINT(?:NEXTLINE|BEGIN|END)?\b|"
    r"nolint\b|lint:ignore\b|nosec\b|#nosec\b|gocyclo:|revive:|exhaustruct:)|"
    r"///\s*sourcery:|"
    r"#\s*(?:noqa\b|flake8:|pyright:|pyre-|pylint:|mypy:|ruff:|fmt:|yapf:|isort:|"
    r"cython:|distutils:|nosec\b|nosemgrep\b|skipcq\b|codespell:|sourcery\s+skip\b|"
    r"keep$|gazelle:|buildifier:|buildozer:|vim:|-\*-|Local Variables:|"
    r"pragma:|shellcheck\b|yamllint\b)|"
    r"/\*\*?\s*(?:eslint-(?:disable|enable)|eslint-env|global|globals|exported|"
    r"biome-ignore|prettier-ignore|"
    r"istanbul\s+ignore|c8\s+ignore|v8\s+ignore|" + _ANNOTATION + r")\b|"
    r"\*\s*" + _ANNOTATION + r")",
    re.IGNORECASE,
)


def _is_directive(text: str) -> bool:
    return bool(_COMPILER_DIRECTIVE.match(text) or _TOOL_DIRECTIVE.match(text))


# Characters str.splitlines() treats as line breaks but git and GitHub do
# not (a lone \r inside a GitHub line makes the two line models disagree, so
# a suggestion validated against one line would replace a different one),
# plus the surrogates that surrogateescape uses for undecodable bytes.
_UNSAFE_TEXT = re.compile("[\r\v\f\x1c-\x1e\x85\u2028\u2029\udc80-\udcff]")
_DOCTEST_PROMPT = re.compile(r"^\s*(?:>>>|\.\.\.)(?:\s|$)")
# Any reST directive. Several read files or run code when the docs build
# (include, raw, ifconfig, testcode, csv-table :file:), and docutils allows
# a space before the `::`, so a denylist would be both incomplete and
# bypassable. A prose rewrite never needs to add one.
_RST_DIRECTIVE = re.compile(r"^\s*\.\.\s+[\w.:+-]+\s*::")
_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _has_hidden_characters(text: str) -> bool:
    """Format, control, private-use, and unassigned code points make a
    suggestion render differently from what it applies (bidi overrides,
    zero-width joiners, Unicode tags). No comment rewrite needs them."""
    return any(
        char not in "\t\n" and unicodedata.category(char) in {"Cf", "Cc", "Co", "Cn", "Cs"}
        for char in text
    )


def _split_lines(text: str) -> list[str]:
    """Split on \\n only, matching how git and GitHub number lines."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _has_unsafe_text(text: str) -> bool:
    return bool(_UNSAFE_TEXT.search(text))


def _read_untranslated(path: Path) -> str:
    # newline="" disables universal-newline translation, which would turn a
    # lone \r into \n and hide it from the line-break checks. surrogateescape
    # keeps one non-UTF-8 file from failing the whole review; findings on its
    # undecodable lines downgrade instead.
    with path.open(encoding="utf-8", errors="surrogateescape", newline="") as handle:
        return handle.read()


def added_text(diff: str) -> dict[str, dict[int, str]]:
    result: dict[str, dict[int, str]] = {}
    path: str | None = None
    line_number = 0
    in_hunk = False
    for line in _split_lines(diff):
        if line.startswith("diff --git "):
            path, in_hunk = None, False
        elif not in_hunk and line.startswith("+++ "):
            target = line[4:].strip()
            path = None if target == "/dev/null" or target.startswith('"') else re.sub(r"^b/", "", target)
        elif match := _HUNK.match(line):
            in_hunk = True
            line_number = int(match.group(1))
        elif path is None or (not in_hunk and line.startswith("--- ")):
            continue
        elif line.startswith("+"):
            result.setdefault(path, {})[line_number] = line[1:]
            line_number += 1
        elif not line.startswith(("-", "\\")):
            line_number += 1
    return result


# Which `//`-comment languages the scanner understands. `quotes` take
# backslash escapes; `raw` literals run to their closing delimiter with none
# (Go backticks; Kotlin and Scala `"""` and backtick identifiers);
# `single_line` quotes cannot legally reach the end of a line, so one that
# does means the scanner has lost sync and the whole file fails closed.
# Anything not listed fails closed: some suffixes need a real parser
# (heredocs, YAML block scalars, Groovy slashy strings); some have no comment
# syntax at all (Markdown, JSON), so "comment-only" would prove nothing and a
# one-click edit into agent-instruction Markdown or workflow YAML is a
# privileged write.
# `template` names the string kinds whose `${ ... }` holds code (JS template
# literals; Kotlin and Scala strings, where the expression may span lines).
# `block` is whether `/* */` is a comment; `splice` is whether a backslash
# before a newline joins the two lines (the C preprocessor); `fail_on` is
# syntax the scanner does not model, whose presence fails the file closed;
# `html` is whether Annex B HTML-like comments exist (JavaScript scripts).
_JS_PROFILE = {
    "quotes": ("`", '"', "'"), "raw": (), "single_line": ('"', "'"),
    "nested": False, "regex": True, "template": ("`",), "block": True, "splice": False,
    "fail_on": None, "html": True,
}
_KOTLIN_PROFILE = {
    "quotes": ('"', "'"), "raw": ('"""', "`"), "single_line": ('"', "'"),
    "nested": True, "regex": False, "template": ('"', '"""'), "block": True, "splice": False,
    "fail_on": None, "html": False,
}
_GLSL_PROFILE = {
    "quotes": (), "raw": (), "single_line": (),
    "nested": False, "regex": False, "template": (), "block": True, "splice": True,
    "fail_on": None, "html": False,
}
# Metal is C++14: string and character literals, and `R"(...)"` raw strings
# (with any encoding prefix) whose delimiters the scanner does not model.
_METAL_PROFILE = {
    "quotes": ('"', "'"), "raw": (), "single_line": ('"', "'"),
    "nested": False, "regex": False, "template": (), "block": True, "splice": True,
    "fail_on": re.compile(r'(?<![A-Za-z0-9_])(?:u8|u|U|L)?R"'), "html": False,
}
_SLASH_PROFILES = {
    # Not .jsx/.tsx: JSX text children are rendered UI, and a child that
    # starts with `//` is not a comment.
    ".js": _JS_PROFILE, ".mjs": _JS_PROFILE, ".cjs": _JS_PROFILE,
    ".ts": _JS_PROFILE, ".mts": _JS_PROFILE, ".cts": _JS_PROFILE,
    ".kt": _KOTLIN_PROFILE, ".kts": _KOTLIN_PROFILE, ".scala": _KOTLIN_PROFILE,
    ".swift": {
        "quotes": ('"""', '"'), "raw": (), "single_line": ('"',),
        "nested": True, "regex": False, "template": (), "block": True, "splice": False,
        "fail_on": None, "html": False,
    },
    ".go": {
        "quotes": ('"', "'"), "raw": ("`",), "single_line": ('"', "'"),
        "nested": False, "regex": False, "template": (), "block": True, "splice": False,
        "fail_on": None, "html": False,
    },
    # Apple localization tables: C-style comments around `"key" = "value";`.
    ".strings": {
        "quotes": ('"',), "raw": (), "single_line": (),
        "nested": False, "regex": False, "template": (), "block": True, "splice": False,
        "fail_on": None, "html": False,
    },
    # GLSL has no string literals; both shader languages have the C
    # preprocessor.
    ".glsl": _GLSL_PROFILE,
    ".metal": _METAL_PROFILE,
    # xcconfig: `//` always starts a comment, even inside a URL, and there
    # are no block comments, so `/*` and `*/` lines are live settings.
    ".xcconfig": {
        "quotes": (), "raw": (), "single_line": (),
        "nested": False, "regex": False, "template": (), "block": False, "splice": False,
        "fail_on": None, "html": False,
    },
}
_HASHES = re.compile("#+")
# Starlark (.bzl/.bazel) is a Python subset; the Python tokenizer reads it.
_PYTHON_SUFFIXES = frozenset({".py", ".pyi", ".bzl", ".bazel"})
_JS_REGEX_KEYWORDS = frozenset({
    "return", "case", "throw", "yield", "await", "else", "do", "typeof",
    "void", "delete", "new", "in", "of", "instanceof",
})


def comment_only_lines(source: str, path: str) -> set[int]:
    """Return lines whose non-whitespace content is entirely comment text."""
    suffix = Path(path).suffix
    if suffix in _PYTHON_SUFFIXES:
        return _python_comment_only_lines(source)
    profile = _SLASH_PROFILES.get(suffix)
    if profile is None:
        return set()
    return _slash_comment_only_lines(source, suffix, profile)


def _python_comment_only_lines(source: str) -> set[int]:
    # The stdlib tokenizer is exact where a hand scanner is not: nested
    # f-string quotes, escapes, continuations. Any tokenizer error fails closed.
    if "\r" in source:
        # Tokenizer versions disagree about what a lone \r is; git does not.
        return set()
    commented: set[int] = set()
    coded: set[int] = set()
    inert = {
        tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
        tokenize.ENDMARKER, tokenize.ENCODING,
    }
    # The 3.12+ tokenizer refuses the surrogates surrogateescape produces for
    # undecodable bytes. Lines carrying them are rejected as targets anyway;
    # a placeholder keeps the rest of the file provable.
    source = source.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.ERRORTOKEN:
                # Older tokenizers report an unterminated string this way
                # instead of raising; either way the file cannot be proven.
                return set()
            if token.type == tokenize.COMMENT:
                commented.add(token.start[0])
            elif token.type not in inert:
                coded.update(range(token.start[0], token.end[0] + 1))
    except (tokenize.TokenError, SyntaxError, ValueError):
        return set()
    return commented - coded


def _js_regex_end(source: str, index: int) -> int | None:
    """End index of a regex literal starting at `index`, or None if the
    slash cannot be one: no closing slash on the line, or the "closing"
    slash begins a comment (`a / b // c` read as a regex)."""
    position = index + 1
    in_class = False
    while position < len(source) and source[position] != "\n":
        char = source[position]
        if char == "\\":
            if position + 1 >= len(source) or source[position + 1] == "\n":
                # A regex literal cannot contain a line break, escaped or
                # not; this slash was division before a continued string.
                return None
            position += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            if source.startswith(("//", "/*"), position):
                return None
            position += 1
            while position < len(source) and (source[position].isalnum() or source[position] == "_"):
                position += 1
            return position
        position += 1
    return None


def _js_regex_context(source: str, index: int) -> str:
    """'yes' if a slash at `index` must start a regex, 'no' if it must be
    division, 'maybe' where only a parser could tell: after `)`, `+`, `-`
    (`if (x) /re/` vs `(a) / b`; `a + /re/.source` vs `i++ / 2`), after `}`
    or `!` (`{} / 2`, TypeScript's `a! / 2`), or at the start of a line."""
    position = index - 1
    while position >= 0 and source[position] in " \t":
        position -= 1
    if position < 0 or source[position] in "=(:,[&|?{;>*%^~<":
        return "yes"
    if source[position] in ")+-}!\n":
        return "maybe"
    word_end = position + 1
    while position >= 0 and (source[position].isalnum() or source[position] in "_$"):
        position -= 1
    word = source[position + 1:word_end]
    if word in _JS_REGEX_KEYWORDS and not (position >= 0 and source[position] in ".$"):
        return "yes"
    return "no"


def _swift_interpolation(source: str, index: int, quote: str, is_raw: bool) -> int:
    """Length of the `\\(` (or `\\#(` for a `#"..."#` literal) that opens an
    interpolation at `index`, or the length of the escape sequence there in a
    raw literal, negated. 0 when the backslash is literal text."""
    hashes = quote[len(quote.rstrip("#")):] if is_raw else ""
    if not source.startswith("\\" + hashes, index):
        return 0
    after = index + 1 + len(hashes)
    if source.startswith("(", after):
        return after + 1 - index
    if not is_raw or after >= len(source) or source[after] == "\n":
        # A `\#` before the newline is a line continuation; the newline
        # branch must still see it to count the line.
        return 0
    return -(after + 1 - index)


def _slash_comment_only_lines(source: str, suffix: str, profile: dict) -> set[int]:
    # `frames` is the lexical stack: ("quote", delimiter, is_raw) for an open
    # string, ("expr", depth, opener, closer) for code inside a string: a JS
    # or Kotlin `${ ... }`, a Swift `\( ... )`. Code mode is the empty stack
    # or an expr frame on top.
    if _UNSAFE_TEXT.search(source):
        # These languages end a `//` comment at `\r` or U+2028; git does not.
        # A comment that hides a string opener would desync every later line.
        return set()
    if profile["fail_on"] is not None and profile["fail_on"].search(source):
        return set()
    result: set[int] = set()
    frames: list[tuple] = []
    line = 1
    index = 0
    escaped = False
    if source.startswith("#!"):
        # A hashbang is a comment to the language but names the interpreter,
        # so the line is neither code to scan nor prose to edit.
        newline = source.find("\n")
        index = len(source) if newline == -1 else newline
    block_depth = 0
    block_start_line = 0
    line_has_code = index > 0
    line_has_comment = False
    template = profile["template"]
    while index < len(source):
        char = source[index]
        top = frames[-1] if frames else None
        in_quote = top is not None and top[0] == "quote"
        if char == "\n":
            if in_quote and top[1] in profile["single_line"] and not escaped:
                return set()
            if line_has_comment and not line_has_code:
                result.add(line)
            line += 1
            line_has_code = bool(frames)
            line_has_comment = block_depth > 0
            escaped = False
            index += 1
            continue
        if block_depth:
            line_has_comment = True
            if profile["nested"] and source.startswith("/*", index):
                block_depth += 1
                index += 2
            elif source.startswith("*/", index):
                block_depth -= 1
                index += 2
            else:
                index += 1
            continue
        if in_quote:
            _, quote, is_raw = top
            line_has_code = True
            swift = 0
            if suffix == ".swift" and char == "\\" and not escaped:
                swift = _swift_interpolation(source, index, quote, is_raw)
            if escaped:
                escaped = False
                index += 1
            elif swift > 0:
                frames.append(("expr", 1, "(", ")"))
                index += swift
            elif swift < 0:
                index -= swift
            elif char == "\\" and not is_raw:
                escaped = True
                index += 1
            elif quote in template and source.startswith("${", index):
                frames.append(("expr", 1, "{", "}"))
                index += 2
            elif source.startswith(quote, index):
                index += len(quote)
                if is_raw and quote == '"""':
                    # Kotlin and Scala close at the last three quotes of a
                    # run, so `"""a""""` holds `a"`.
                    while index < len(source) and source[index] == '"':
                        index += 1
                frames.pop()
            else:
                index += 1
            continue
        if char.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            line_has_comment = True
            newline = source.find("\n", index)
            index = len(source) if newline == -1 else newline
            continue
        if profile["html"] and (
            source.startswith("<!--", index)
            or (not line_has_code and source.startswith("-->", index))
        ):
            # Annex B makes these comments in scripts; modules and TypeScript
            # read them as operators. Neither reading is worth modelling.
            return set()
        if profile["block"] and source.startswith("/*", index):
            line_has_comment = True
            block_depth = 1
            block_start_line = line
            index += 2
            continue
        if top is not None and char in (top[2], top[3]):
            depth = top[1] + (1 if char == top[2] else -1)
            frames[-1] = ("expr", depth, top[2], top[3])
            if depth == 0:
                frames.pop()
            line_has_code = True
            index += 1
            continue
        if profile["regex"] and char == "/":
            end = _js_regex_end(source, index)
            context = _js_regex_context(source, index)
            if end is not None and context == "maybe":
                body = source[index:end]
                if any(marker in body for marker in ('"', "'", "`", "/*")):
                    # Division and regex readings leave different quote
                    # state, and only a parser could pick one. Fail closed.
                    return set()
            if end is not None and context != "no":
                line_has_code = True
                index = end
                continue
        if suffix == ".swift" and char == "#":
            # Extended delimiters: `#"..."#`, `#"""..."""#`, `#/.../#`.
            # Backslashes are literal unless followed by the same `#` run.
            hashes = _HASHES.match(source, index).group(0)
            opener = next((item for item in ('"""', '"', "/") if source.startswith(item, index + len(hashes))), None)
            line_has_code = True
            if opener:
                frames.append(("quote", opener + hashes, True))
                index += len(hashes) + len(opener)
            else:
                index += len(hashes)
            continue
        matched = next((item for item in profile["raw"] if source.startswith(item, index)), None)
        if matched:
            line_has_code = True
            frames.append(("quote", matched, True))
            index += len(matched)
            continue
        matched = next((item for item in profile["quotes"] if source.startswith(item, index)), None)
        if matched:
            line_has_code = True
            frames.append(("quote", matched, False))
            index += len(matched)
            continue
        line_has_code = True
        index += 1
    if frames and frames[-1][0] == "quote":
        # An unterminated string at end of file: a multi-line kind means the
        # file does not compile, a single-line kind means the scanner lost
        # sync somewhere above. Either way nothing after it is proven.
        return set()
    if line_has_comment and not line_has_code and not block_depth:
        result.add(line)
    if block_depth:
        result.difference_update(range(block_start_line, line + 1))
    if profile["splice"]:
        # A backslash before the newline joins the next line onto this one,
        # so a `//` comment ending in `\` comments out the line below it.
        # Neither line can be edited on its own.
        for number, text in enumerate(source.split("\n"), 1):
            if text.rstrip().endswith("\\"):
                result.discard(number)
                result.discard(number + 1)
    return result


def _replacement_is_safe(replacement: str, path: str) -> bool:
    if not replacement:
        return True
    lines = _split_lines(replacement)
    nonblank = {index for index, line in enumerate(lines, 1) if line.strip()}
    return (
        bool(nonblank)
        and nonblank.issubset(comment_only_lines(replacement, path))
        and not any("/*" in line or "*/" in line for line in lines)
        # The C preprocessor would join the next line onto this comment.
        and not any(line.rstrip().endswith("\\") for line in lines)
        and not any(_is_directive(line.strip()) for line in lines)
    )


def _docstring_owners(tree: ast.AST) -> list[ast.AST]:
    return [
        node for node in ast.walk(tree)
        if isinstance(node, _DOCSTRING_OWNERS)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ]


def _structure(tree: ast.AST) -> str:
    """Dump the tree with every docstring's text blanked, so two dumps agree
    exactly when nothing but docstring text differs."""
    for owner in _docstring_owners(tree):
        owner.body[0].value.value = ""
    return ast.dump(tree)


def _docstring_edit_is_safe(source: str, start: int, end: int, replacement: str) -> bool:
    """Prove the range is exactly one Python docstring and the replacement
    swaps only its text. Docstrings lex as strings, so the comment-only proof
    cannot see them; the AST can."""
    if "\r" in source:
        # The parser counts \r as a line break; git does not, so line numbers
        # from the two would disagree.
        return False
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    lines = _split_lines(source)
    owner = next(
        (
            node for node in _docstring_owners(tree)
            if node.body[0].lineno == start and node.body[0].end_lineno == end
        ),
        None,
    )
    if owner is None:
        return False
    target = owner.body[0]
    # ast column offsets count UTF-8 bytes, so compare against encoded lines.
    first, last = lines[start - 1].encode(), lines[end - 1].encode()
    if target.col_offset != len(first) - len(first.lstrip()) or last[target.end_col_offset:].strip():
        return False

    replacement_lines = _split_lines(replacement)
    # doctest and pytest --doctest-modules execute prompt lines; Sphinx runs
    # or inlines the active directives.
    if any(
        _DOCTEST_PROMPT.match(line)
        or _RST_DIRECTIVE.match(line)
        or _is_directive(line.strip())
        for line in replacement_lines
    ):
        return False
    if start <= 2 and len(replacement_lines) != end - start + 1 and any(
        _is_directive(text.strip()) for text in lines[:3]
    ):
        # Growing or shrinking a docstring at the top of the file moves the
        # lines below it, and a coding cookie is only live on lines 1-2.
        return False
    spliced = "\n".join(lines[: start - 1] + replacement_lines + lines[end:])
    if source.endswith("\n"):
        spliced += "\n"
    try:
        new_tree = ast.parse(spliced)
    except (SyntaxError, ValueError):
        return False
    if replacement:
        new_end = start + len(replacement_lines) - 1
        new_target = next(
            (
                node.body[0] for node in _docstring_owners(new_tree)
                if node.body[0].lineno == start and node.body[0].end_lineno == new_end
            ),
            None,
        )
        if new_target is None:
            return False
        if replacement_lines[-1].encode()[new_target.end_col_offset:].strip():
            # A trailing `# type: ignore` or `# noqa` is not in the AST.
            return False
    else:
        owner.body.pop(0)
        if not owner.body:
            return False
    return _structure(tree) == _structure(new_tree)


def _safe_review_text(value: str) -> str:
    """Prevent rationale text from opening a second suggestion fence."""
    return value.replace("```", "`\u200b``").replace("~~~", "~\u200b~~")


def _source_head(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip().lower()


def _finding(raw: Any, changed: dict[str, dict[int, str]], source_root: Path) -> tuple[str, dict[str, Any] | None]:
    if not isinstance(raw, dict):
        return "drop", None
    try:
        path = raw["path"]
        start = raw["start_line"]
        end = raw["end_line"]
        action = raw["action"]
        replacement = raw["replacement"]
        rationale = raw["rationale"]
        confidence = raw["confidence"]
    except KeyError:
        return "drop", None
    if (
        not isinstance(path, str) or path.startswith("/") or ".." in Path(path).parts
        or not isinstance(start, int) or isinstance(start, bool) or start < 1
        or not isinstance(end, int) or isinstance(end, bool) or end < start
        or not isinstance(action, str) or action not in _ACTIONS
        or not isinstance(confidence, str) or confidence not in {"high-confidence", "borderline"}
        or not isinstance(replacement, str) or not isinstance(rationale, str)
        or (action == "delete" and replacement) or (action != "delete" and not replacement)
    ):
        return "drop", None
    if path not in changed or any(line not in changed[path] for line in range(start, end + 1)):
        return "drop", None
    # The suggestion body wraps the replacement in its own newlines; a trailing
    # one would apply as an extra blank line the checks never saw.
    replacement = replacement.rstrip("\n")
    if action != "delete" and not replacement:
        return "drop", None
    finding = {"path": path, "start_line": start, "end_line": end, "replacement": replacement, "rationale": rationale}
    if confidence != "high-confidence":
        return "borderline", finding
    if "```" in replacement:
        # A bare fence line would close the suggestion block early, and
        # GitHub would apply only the lines above it.
        return "note", finding
    root = source_root.resolve()
    candidate = (root / path).absolute()
    try:
        # A symlink loop raises RuntimeError before 3.13.
        canonical = candidate.resolve()
    except (OSError, RuntimeError):
        return "note", finding
    if root not in candidate.parents or canonical != candidate:
        return "note", finding
    try:
        source = _read_untranslated(candidate)
    except (OSError, ValueError):
        return "note", finding
    source_lines = _split_lines(source)
    if any(line > len(source_lines) or source_lines[line - 1] != changed[path][line] for line in range(start, end + 1)):
        return "note", finding
    target_lines = [changed[path][line] for line in range(start, end + 1)]
    if (
        any(_has_unsafe_text(line) for line in target_lines)
        or _has_unsafe_text(replacement)
        or _has_hidden_characters(replacement)
    ):
        return "note", finding
    safe_lines = comment_only_lines(source, path)
    if all(line in safe_lines for line in range(start, end + 1)):
        # Resizing a comment at the top of a Python file has the docstring
        # hazard: a coding cookie is live only on lines 1-2.
        moves_cookie = (
            Path(path).suffix in _PYTHON_SUFFIXES
            and start <= 2
            and len(_split_lines(replacement)) != end - start + 1
            and any(_is_directive(text.strip()) for text in source_lines[:3])
        )
        safe = (
            not moves_cookie
            and not any("/*" in line or "*/" in line for line in target_lines)
            and not any(_is_directive(line.strip()) for line in target_lines)
            and _replacement_is_safe(replacement, path)
        )
    elif Path(path).suffix in {".py", ".pyi"}:
        try:
            safe = _docstring_edit_is_safe(source, start, end, replacement)
        except (RecursionError, MemoryError):
            # ast on a pathological head file; one finding downgrades rather
            # than the run failing.
            safe = False
    else:
        safe = False
    return ("suggestion" if safe else "note"), finding


def render(
    result: dict[str, Any],
    diff: str,
    source_root: Path,
    commit_id: str,
) -> tuple[dict[str, Any], list[str]]:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_id):
        raise ValueError("commit_id must be a full 40-character Git SHA")
    if _source_head(source_root) != commit_id.lower():
        raise ValueError("commit_id does not match source_root HEAD")
    changed = added_text(diff)
    raw_findings = result.get("comment_findings", [])
    if not isinstance(raw_findings, list):
        raw_findings = []
    comments: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for index, raw in enumerate(raw_findings):
        kind, finding = _finding(raw, changed, source_root)
        if finding is None:
            diagnostics.append(f"dropped invalid finding {index}")
            continue
        if kind == "borderline":
            diagnostics.append(f"omitted borderline finding {index} from inline review")
            continue
        comment: dict[str, Any] = {
            "path": finding["path"], "line": finding["end_line"], "side": "RIGHT",
        }
        if finding["start_line"] != finding["end_line"]:
            comment.update(start_line=finding["start_line"], start_side="RIGHT")
        rationale = _safe_review_text(finding["rationale"])
        if kind == "suggestion":
            comment["body"] = f"{rationale}\n```suggestion\n{finding['replacement']}\n```"
        else:
            comment["body"] = (
                f"{rationale}\n\n"
                "No one-click suggestion: this range was not proven to contain only replaceable comment or docstring text."
            )
            diagnostics.append(f"downgraded finding {index} to a plain note")
        comments.append(comment)
    return {
        "event": "COMMENT",
        "commit_id": commit_id.lower(),
        "comments": comments,
    }, diagnostics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--diff", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--commit-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    review, diagnostics = render(
        result,
        _read_untranslated(Path(args.diff)),
        Path(args.source_root),
        args.commit_id,
    )
    Path(args.output).write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    for diagnostic in diagnostics:
        print(diagnostic, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
