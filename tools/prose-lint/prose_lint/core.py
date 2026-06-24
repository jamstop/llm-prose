from __future__ import annotations

from . import ts
from .languages import language_for_path
from .model import Finding
from .rules import RULES


def lint_source(path: str, source: str, language: str, enabled=None) -> list[Finding]:
    root, src = ts.parse(language, source)
    findings: list[Finding] = []
    for name, run in RULES.items():
        if enabled and name not in enabled:
            continue
        findings.extend(run(root, src, language, path))
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def lint_path(path: str, enabled=None) -> list[Finding]:
    language = language_for_path(path)
    if language is None:
        return []
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    return lint_source(path, source, language, enabled)
