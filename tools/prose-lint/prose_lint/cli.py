from __future__ import annotations

import argparse
import json
import sys

from .core import lint_path
from .diff import added_lines
from .languages import language_for_path
from .rules import RULES


def _emit_text(findings) -> None:
    for f in findings:
        print(f"{f.file}:{f.line}: [{f.rule}/{f.action}] {f.message}")
    counts = {}
    for f in findings:
        counts[f.rule] = counts.get(f.rule, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
    print(f"--- {len(findings)} finding(s): {summary}", file=sys.stderr)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="prose-lint",
        description="Deterministic, AST-based linter for mechanical comment bloat.",
    )
    p.add_argument("paths", nargs="*", help="files to lint")
    p.add_argument("--diff", action="store_true",
                   help="read a unified diff on stdin; lint only added comment lines")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--rules", help="comma-separated subset of: " + ",".join(RULES))
    p.add_argument("--max", type=int, default=0,
                   help="max allowed findings before non-zero exit (default 0)")
    args = p.parse_args(argv)

    enabled = set(args.rules.split(",")) if args.rules else None

    findings = []
    if args.diff:
        scope = added_lines(sys.stdin.read())
        for path, lines in scope.items():
            if language_for_path(path) is None:
                continue
            try:
                file_findings = lint_path(path, enabled)
            except FileNotFoundError:
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
