"""The invariants, stated one per test, in plain inline source.

`test_rules.py` is the *score* (exact-match findings on fixture files).
This file is the *contract*: each test names a single guarantee and proves it
on a self-contained snippet, including the false-positive boundaries that the
0.4.x fixes pinned down. Read top to bottom to learn what the linter promises.
"""

from deslop import lint_source


def lint(src, lang="python", rules=None):
    """Lint an inline snippet. `rules` restricts to a subset by name."""
    return lint_source("<mem>", src, lang, rules)


def fired(findings):
    return {(f.rule, f.action) for f in findings}


# --- R1: notes-to-self / LLM residue ----------------------------------------
# Invariant: flag the model talking to itself; never flag a real why-comment.

class TestR1NotesToSelf:
    def test_flags_as_requested(self):
        assert ("notes-to-self", "delete") in fired(
            lint("# as requested, default to usd\nx = 1\n", rules={"notes-to-self"}))

    def test_flags_feedback_and_review_phrases(self):
        for phrase in ("per your feedback", "per review", "as you asked", "as a reminder"):
            assert fired(lint(f"# {phrase}: widen the type\nx = 1\n",
                              rules={"notes-to-self"})), phrase

    def test_flags_edit_narration_when_it_leads_the_comment(self):
        assert fired(lint("# I renamed this for clarity\nx = 1\n", rules={"notes-to-self"}))

    def test_does_not_flag_edit_verb_mid_sentence(self):
        # "I" describing behavior, not an edit, is ordinary prose.
        assert not fired(lint("# the digest I compute must match the server's\nx = 1\n",
                              rules={"notes-to-self"}))

    def test_does_not_flag_version_or_date_mentions(self):
        # Regression: bare vX.Y / ISO dates used to trip R1; legit why-comments
        # routinely cite them.
        for c in ("# deprecated after 2025-01-01, see RFC 9110\n",
                  "# v2 of the Stripe API changes this rounding\n"):
            assert not fired(lint(c + "x = 1\n", rules={"notes-to-self"})), c

    def test_does_not_flag_plain_why_comment(self):
        assert not fired(lint("# Stripe sends cents for JPY; do not multiply\nx = 1\n",
                              rules={"notes-to-self"}))

    def test_is_language_agnostic(self):
        for lang, src in (("swift", "// as requested, default to usd\nlet x = 1\n"),
                          ("javascript", "// as requested\nconst x = 1;\n")):
            assert fired(lint(src, lang=lang, rules={"notes-to-self"})), lang


# --- R2: commented-out code -------------------------------------------------
# Invariant: flag comments that re-parse as code; leave prose and TODOs alone.

class TestR2CommentedOutCode:
    def test_flags_commented_assignment(self):
        assert ("commented-out-code", "delete") in fired(
            lint("# total = amount * 100\nx = 1\n", rules={"commented-out-code"}))

    def test_flags_commented_call(self):
        assert fired(lint("# do_refund(customer, amount)\nx = 1\n",
                          rules={"commented-out-code"}))

    def test_does_not_flag_prose(self):
        assert not fired(lint("# round half-up because refunds bite us\nx = 1\n",
                              rules={"commented-out-code"}))

    def test_does_not_flag_todo_even_with_code_inside(self):
        assert not fired(lint("# TODO: total = apply_discount(total)\nx = 1\n",
                              rules={"commented-out-code"}))

    def test_works_in_go_with_scaffold(self):
        # R2 is narrow on purpose: it keys off assignment/call signals. Go's `:=`
        # is a short_var_declaration (no signal), so use a call, as real
        # commented-out Go usually has.
        src = "package p\nfunc F() {\n\t// total = computeTotal(amount, cur)\n\tx := 1\n\t_ = x\n}\n"
        assert fired(lint(src, lang="go", rules={"commented-out-code"}))

    def test_works_in_swift(self):
        src = "func f() {\n    // total = amount * 100\n    let x = 1\n}\n"
        assert fired(lint(src, lang="swift", rules={"commented-out-code"}))


# --- R3: docstring restates the signature (Python only) ---------------------
# Invariant: flag boilerplate Args/Returns; keep summaries and substantive text.

class TestR3DocDump:
    RESTATES = (
        'def to_cents(dollars):\n'
        '    """Convert dollars to cents.\n'
        '\n'
        '    Args:\n'
        '        dollars: the dollars to convert to cents.\n'
        '    Returns:\n'
        '        the cents.\n'
        '    """\n'
        '    return int(dollars * 100)\n'
    )

    def test_flags_restating_docstring(self):
        assert ("doc-dump", "tighten") in fired(lint(self.RESTATES, rules={"doc-dump"}))

    def test_keeps_tight_one_liner(self):
        src = ('def clamp(v, lo, hi):\n'
               '    """Clamp v to [lo, hi]; hi wins ties."""\n'
               '    return max(lo, min(hi, v))\n')
        assert not fired(lint(src, rules={"doc-dump"}))

    def test_keeps_substantive_multiline_returns(self):
        # Regression for the empty-inline "Returns:" bug: the header alone is not
        # redundant, and the wrapped description below is substantive.
        src = ('def load(path):\n'
               '    """Load config.\n'
               '\n'
               '    Returns:\n'
               '        the parsed config with secrets stripped and defaults applied.\n'
               '    """\n'
               '    return _load(path)\n')
        assert not fired(lint(src, rules={"doc-dump"}))

    def test_keeps_substantive_arg_description(self):
        src = ('def connect(timeout):\n'
               '    """Open a pooled connection.\n'
               '\n'
               '    Args:\n'
               '        timeout: seconds to wait before falling back to the read replica.\n'
               '    """\n'
               '    return _open(timeout)\n')
        assert not fired(lint(src, rules={"doc-dump"}))

    def test_is_python_only(self):
        # Swift /// doc comments are not parsed for restatement (by design today).
        src = "/// Returns the total in cents.\nfunc total() -> Int { return 0 }\n"
        assert not fired(lint(src, lang="swift", rules={"doc-dump"}))


# --- cross-cutting structural invariants ------------------------------------

class TestStructuralInvariants:
    SRC = (
        'def to_cents(dollars):\n'
        '    # as requested, default scale\n'
        '    # total = dollars * 100\n'
        '    """Convert dollars to cents.\n'
        '\n'
        '    Args:\n'
        '        dollars: the dollars to convert to cents.\n'
        '    """\n'
        '    return int(dollars * 100)\n'
    )

    def test_every_action_is_known(self):
        assert all(f.action in ("delete", "tighten") for f in lint(self.SRC))

    def test_line_numbers_are_one_based(self):
        assert all(f.line >= 1 for f in lint(self.SRC))

    def test_findings_are_sorted_by_line(self):
        lines = [f.line for f in lint(self.SRC)]
        assert lines == sorted(lines)

    def test_rules_filter_restricts_output(self):
        only = lint(self.SRC, rules={"notes-to-self"})
        assert only and {f.rule for f in only} == {"notes-to-self"}

    def test_all_three_rules_can_coexist(self):
        assert fired(self_findings := lint(self.SRC)) >= {
            ("notes-to-self", "delete"),
            ("commented-out-code", "delete"),
            ("doc-dump", "tighten"),
        }
        assert self_findings  # sanity


def test_unknown_extension_is_skipped(tmp_path):
    from deslop import lint_path
    p = tmp_path / "notes.txt"
    p.write_text("# as requested\n")
    assert lint_path(str(p)) == []
