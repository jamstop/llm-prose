"""The deterministic rules. See RULES.md for the catalog and rationale."""

from __future__ import annotations

import re

from . import ts
from .languages import is_comment, strip_comment, scaffold
from .model import Finding

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
# so this is anchored to the start of the stripped body. Bare version/date
# mentions were dropped entirely — they false-positive on legitimate why-
# comments that cite an API version or a deprecation date.
_RESIDUE_LEAD = re.compile(
    r"""
    ^I\ (?:changed|added|updated|removed|renamed|refactored|made|fixed)\b
  | ^updated\ to\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# --- R2: commented-out code --------------------------------------------------

_PROSE_MARKER = re.compile(r"^\s*(TODO|FIXME|NOTE|HACK|XXX|WARNING|WARN)\b", re.IGNORECASE)


def _is_code_signal(node_kind: str) -> bool:
    if "signature" in node_kind:
        return False
    return "assignment" in node_kind or "call" in node_kind or "invocation" in node_kind


def _parses_as_code(language: str, fragment: str) -> bool:
    if len(fragment.strip()) < 4:
        return False
    root, _ = ts.parse(language, scaffold(language, fragment))
    if ts.has_error(root):
        return False
    return any(_is_code_signal(ts.kind(n)) for n in ts.walk(root))


# --- R3: docstring restates the signature (Python) ---------------------------

_STOP = {
    "a", "an", "the", "to", "of", "for", "in", "on", "and", "or", "is", "be",
    "this", "that", "it", "its", "with", "as", "if", "no", "by", "from", "into",
    "when", "which", "will", "should", "must", "use", "used", "given", "value",
    "values", "result", "results", "none", "true", "false", "object", "objects",
}
_ARGS_HEADER = re.compile(r"^(Args|Arguments|Parameters)\s*:\s*$")
_RETURNS_HEADER = re.compile(r"^(Returns|Yields)\s*:\s*(.*)$")
_ENTRY = re.compile(r"^([A-Za-z_]\w*)\s*(\([^)]*\))?\s*:\s*(.*)$")


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[A-Za-z]+", s.lower())}


def _name_tokens(name: str) -> set[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ")
    return _tokens(spaced)


def _unquote(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^[rbuRBU]{0,2}", "", s)
    for q in ('"""', "'''", '"', "'"):
        if s.startswith(q):
            s = s[len(q):]
            if s.endswith(q):
                s = s[: -len(q)]
            break
    return s.strip()


def _docstring_node(body):
    """First statement of a block, if it's a string literal (the docstring)."""
    for child in ts.children(body):
        k = ts.kind(child)
        if not k.strip():
            continue
        if k == "string":
            return child
        if k == "expression_statement":
            for g in ts.children(child):
                if ts.kind(g) == "string":
                    return g
        return None  # first real statement isn't a string -> no docstring
    return None


def _docstring_of(body, src: bytes) -> str | None:
    node = _docstring_node(body)
    return _unquote(ts.text(node, src)) if node is not None else None


def _redundant(desc: str, name: str, summary: set[str]) -> bool:
    content = _tokens(desc) - _STOP
    allowed = summary | _name_tokens(name) | _STOP
    return content.issubset(allowed)


def _docstring_restates(doc: str) -> bool:
    lines = [l.strip() for l in doc.splitlines()]
    summary_lines = []
    for l in lines:
        if not l:
            break
        summary_lines.append(l)
    summary = _tokens(" ".join(summary_lines))

    section = None
    returns_parts: list[str] = []
    for l in lines:
        if _ARGS_HEADER.match(l):
            section = "args"
            continue
        rm = _RETURNS_HEADER.match(l)
        if rm:
            section = "returns"
            # The description may be inline ("Returns: x") or wrapped onto the
            # next indented line. Collect either form and judge the whole block
            # once below — a bare "Returns:" header is not itself redundant.
            if rm.group(2).strip():
                returns_parts.append(rm.group(2))
            continue
        if section == "args":
            m = _ENTRY.match(l)
            if m and m.group(3).strip() and _redundant(m.group(3), m.group(1), summary):
                return True
        elif section == "returns" and l:
            returns_parts.append(l)

    return bool(returns_parts) and _redundant(" ".join(returns_parts), "", summary)


# --- rule runners ------------------------------------------------------------


def _comment_nodes(root):
    return [n for n in ts.walk(root) if is_comment(ts.kind(n))]


def run_r1(root, src, language, path):
    out = []
    for node in _comment_nodes(root):
        body = strip_comment(ts.text(node, src))
        if _RESIDUE.search(body) or _RESIDUE_LEAD.match(body):
            out.append(Finding(path, ts.row(node) + 1, "notes-to-self", "delete",
                               "comment is a note-to-self / LLM residue; delete"))
    return out


def run_r2(root, src, language, path):
    out = []
    for node in _comment_nodes(root):
        raw = ts.text(node, src)
        body = strip_comment(raw)
        if not body or _PROSE_MARKER.match(body):
            continue
        if _parses_as_code(language, body):
            out.append(Finding(path, ts.row(node) + 1, "commented-out-code", "delete",
                               "comment body parses as code; delete (it's in git history)"))
    return out


def run_r3(root, src, language, path):
    if language != "python":
        return []
    out = []
    for node in ts.walk(root):
        if ts.kind(node) != "function_definition":
            continue
        body = ts.field(node, "body")
        if body is None:
            continue
        doc = _docstring_of(body, src)
        if not doc:
            continue
        if _docstring_restates(doc):
            dn = _docstring_node(body)
            doc_line = ts.row(dn) + 1 if dn is not None else ts.row(body) + 1
            out.append(Finding(path, doc_line, "doc-dump", "tighten",
                               "docstring Args/Returns restate the signature; cut to the summary"))
    return out


RULES = {"notes-to-self": run_r1, "commented-out-code": run_r2, "doc-dump": run_r3}
