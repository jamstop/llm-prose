"""Exact-match tests = the deterministic score. No LLM, so these never flake.

Each fixture has a hand-specified set of expected (line, rule, action) findings.
A regression either drops an expected finding or invents a new one, and the
exact-equality assertion catches both.
"""

from pathlib import Path

from prose_lint import lint_path

FIX = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[3]

EXPECTED = {
    "sample_py.py": {
        (2, "notes-to-self", "delete"),
        (4, "commented-out-code", "delete"),
        (12, "doc-dump", "tighten"),
    },
    "sample_js.js": {
        (2, "notes-to-self", "delete"),
        (4, "commented-out-code", "delete"),
    },
    "sample_go.go": {
        (4, "notes-to-self", "delete"),
        (6, "commented-out-code", "delete"),
    },
}


def _findings(path):
    return {(f.line, f.rule, f.action) for f in lint_path(str(path))}


def test_fixtures_exact_match():
    for name, expected in EXPECTED.items():
        actual = _findings(FIX / name)
        assert actual == expected, f"{name}: missing={expected - actual} extra={actual - expected}"


def test_clean_comments_not_flagged():
    # The "why" comments and the good one-line docstring must stay clean.
    py = _findings(FIX / "sample_py.py")
    assert not any(line in (6, 7, 23) for line, _, _ in py)


def test_crosscheck_eval_fixture():
    # The shared eval fixture: R1 catches the notes-to-self, R3 the two doc dumps.
    # CMT_B3's commented-out code carries a sentinel token inside the code, so it
    # doesn't re-parse - R2 stays conservative there, by design.
    found = _findings(REPO_ROOT / "eval" / "fixtures" / "sample.py")
    assert (12, "notes-to-self", "delete") in found
    assert (25, "doc-dump", "tighten") in found
    assert (36, "doc-dump", "tighten") in found
