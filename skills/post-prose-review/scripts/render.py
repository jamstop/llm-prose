#!/usr/bin/env python3
"""Render prose findings as a safe GitHub review.

Only edits proven to replace complete comment-only lines become suggestion
blocks. Invalid findings are dropped; unsafe edits become ordinary review
comments. The module is stdlib-only so skills can use it without installing
the host project's dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_ACTIONS = {"delete", "tighten", "move"}
_DIRECTIVE = re.compile(
    r"^(?:#!|#.*\bcoding[:=]|"
    r"///\s*<(?:reference|amd-)|//>|//go:|// \+build\b|//line\b|"
    r"//extern\b|//export\b|//\s*#cgo\b|#cgo\b|"
    r"// Code generated .* DO NOT EDIT\.$|#\s*type:|//#|//@|"
    r"//\s*(?:swift-tools-version:|swift-format-(?:ignore|ignore-file)\b|"
    r"swiftformat:|swiftlint:|eslint-(?:disable|enable)(?:-next-line|-line)?\b|"
    r"biome-ignore(?:-all)?\b|prettier-ignore\b|istanbul\s+ignore\b|@ts-|"
    r"noinspection\b|clang-format\b|NOLINT(?:NEXTLINE|BEGIN|END)?\b|@flow\b)|"
    r"#\s*(?:noqa\b|flake8:|pyright:|pylint:|mypy:|ruff:|fmt:|isort:|"
    r"cython:|distutils:|"
    r"pragma:|shellcheck\b|yamllint\b)|"
    r"/\*\s*(?:eslint-(?:disable|enable)|biome-ignore|prettier-ignore|"
    r"istanbul\s+ignore)\b)",
    re.IGNORECASE,
)


def added_text(diff: str) -> dict[str, dict[int, str]]:
    result: dict[str, dict[int, str]] = {}
    path: str | None = None
    line_number = 0
    in_hunk = False
    for line in diff.splitlines():
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


def _profile(path: str) -> tuple[str | None, bool, bool, tuple[str, ...]]:
    suffix = Path(path).suffix.lower()
    if suffix in {".py", ".pyi"}:
        return "#", False, False, ('"""', "'''", '"', "'")
    if suffix in {
        ".rb", ".sql", ".lua", ".sh", ".bash", ".yaml", ".yml",
        ".rs", ".c", ".h", ".cpp", ".cc", ".hpp", ".cxx", ".java",
    }:
        # Their heredocs, raw strings, long strings, or block scalars require a
        # real parser. Findings remain useful, but never become one-click edits.
        return None, False, False, ()
    blocks = suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".swift", ".go", ".kt", ".scala"}
    nested = suffix in {".swift", ".kt", ".scala"}
    return "//", blocks, nested, ('"""', "'''", "`", '"', "'")


def comment_only_lines(source: str, path: str) -> set[int]:
    """Return lines containing comments and no executable or literal text."""
    marker, blocks, nested, quotes = _profile(path)
    if marker is None:
        return set()
    result: set[int] = set()
    line = 1
    index = 0
    quote: str | None = None
    escaped = False
    depth = 0
    block_start = 0
    has_code = False
    has_comment = False
    suffix = Path(path).suffix.lower()
    while index < len(source):
        if source[index] == "\n":
            if has_comment and not has_code:
                result.add(line)
            line += 1
            has_code = quote is not None
            has_comment = depth > 0
            escaped = False
            index += 1
            continue
        if depth:
            has_comment = True
            if nested and source.startswith("/*", index):
                depth += 1
                index += 2
            elif source.startswith("*/", index):
                depth -= 1
                index += 2
            else:
                index += 1
            continue
        if quote:
            has_code = True
            if escaped:
                escaped = False
                index += 1
            elif source[index] == "\\":
                escaped = True
                index += 1
            elif source.startswith(quote, index):
                index += len(quote)
                quote = None
            else:
                index += 1
            continue
        if source[index].isspace():
            index += 1
            continue
        if marker and source.startswith(marker, index):
            has_comment = True
            newline = source.find("\n", index)
            index = len(source) if newline == -1 else newline
            continue
        if blocks and source.startswith("/*", index):
            has_comment = True
            depth = 1
            block_start = line
            index += 2
            continue
        if suffix == ".swift" and source[index] == "#":
            match = re.match(r'(#+)("""|"|/)', source[index:])
            if match:
                has_code = True
                quote = match.group(2) + match.group(1)
                index += len(match.group(0))
                continue
        matched = next((item for item in quotes if source.startswith(item, index)), None)
        if matched:
            has_code = True
            quote = matched
            index += len(matched)
            continue
        has_code = True
        index += 1
    if has_comment and not has_code and not depth:
        result.add(line)
    if depth:
        result.difference_update(range(block_start, line + 1))
    return result


def _replacement_is_safe(replacement: str, path: str) -> bool:
    if not replacement:
        return True
    lines = replacement.splitlines()
    nonblank = {index for index, line in enumerate(lines, 1) if line.strip()}
    return (
        bool(nonblank)
        and nonblank.issubset(comment_only_lines(replacement, path))
        and not any("/*" in line or "*/" in line for line in lines)
        and not any(_DIRECTIVE.match(line.strip()) for line in lines)
    )


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
    finding = {"path": path, "start_line": start, "end_line": end, "replacement": replacement, "rationale": rationale}
    if confidence != "high-confidence":
        return "borderline", finding
    root = source_root.resolve()
    candidate = (root / path).absolute()
    try:
        canonical = candidate.resolve()
    except OSError:
        return "note", finding
    if root not in candidate.parents or canonical != candidate:
        return "note", finding
    try:
        source = candidate.read_text(encoding="utf-8")
    except OSError:
        return "note", finding
    source_lines = source.splitlines()
    if any(line > len(source_lines) or source_lines[line - 1] != changed[path][line] for line in range(start, end + 1)):
        return "note", finding
    safe_lines = comment_only_lines(source, path)
    safe = (
        all(line in safe_lines for line in range(start, end + 1))
        and not any("/*" in changed[path][line] or "*/" in changed[path][line] for line in range(start, end + 1))
        and not any(_DIRECTIVE.match(changed[path][line].strip()) for line in range(start, end + 1))
        and _replacement_is_safe(replacement, path)
    )
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
                "No one-click suggestion: this range was not proven to contain only replaceable comment text."
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
        Path(args.diff).read_text(encoding="utf-8"),
        Path(args.source_root),
        args.commit_id,
    )
    Path(args.output).write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    for diagnostic in diagnostics:
        print(diagnostic, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
