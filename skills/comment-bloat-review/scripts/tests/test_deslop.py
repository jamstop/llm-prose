"""The invariants, one per test, in plain inline source.

This is the *contract*: each test names a single guarantee and proves it on a
self-contained snippet, including the false-positive boundaries. deslop is
stdlib-only and deliberately narrow — it owns R1 (LLM residue) and R2
(commented-out code); doc-dump tightening is a judgment call left to the skill.
Read top to bottom to learn exactly what the tool promises.
"""

import deslop


def lint(src, lang="python", rules=None):
    return deslop.lint_source("<mem>", src, lang, rules)


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
        assert not fired(lint("# the digest I compute must match the server's\nx = 1\n",
                              rules={"notes-to-self"}))

    def test_does_not_flag_version_or_date_mentions(self):
        for c in ("# deprecated after 2025-01-01, see RFC 9110\n",
                  "# v2 of the Stripe API changes this rounding\n"):
            assert not fired(lint(c + "x = 1\n", rules={"notes-to-self"})), c

    def test_does_not_flag_plain_why_comment(self):
        assert not fired(lint("# Stripe sends cents for JPY; do not multiply\nx = 1\n",
                              rules={"notes-to-self"}))

    def test_is_language_agnostic(self):
        for lang, src in (("swift", "// as requested, default to usd\nlet x = 1\n"),
                          ("javascript", "// as requested\nconst x = 1;\n"),
                          ("go", "// as requested\nx := 1\n")):
            assert fired(lint(src, lang=lang, rules={"notes-to-self"})), lang

    def test_fires_inside_block_comment(self):
        src = "/*\n * as requested, default to usd\n */\nconst x = 1;\n"
        assert fired(lint(src, lang="javascript", rules={"notes-to-self"}))


# --- R2: commented-out code -------------------------------------------------
# Invariant: flag comments that read as code; leave prose and TODOs alone.

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

    def test_does_not_flag_tool_directives(self):
        # Regression from dogfooding a real PR: directive comments have a
        # key=value / key: value shape that used to read as commented-out code.
        cases = [
            ("# shellcheck disable=SC2012  # ls -t is simplest\nx = 1\n", "shell"),
            ("# noqa: E501\nx = 1\n", "python"),
            ("# type: ignore[arg-type]\nx = 1\n", "python"),
            ("# pylint: disable=invalid-name\nx = 1\n", "python"),
            ("// eslint-disable-next-line no-console\nconst y = 1;\n", "javascript"),
            ("// NOLINTNEXTLINE(readability-magic-numbers)\nint y = 1;\n", "cpp"),
            ("// @ts-expect-error legacy shim\nconst y = 1;\n", "typescript"),
        ]
        for src, lang in cases:
            assert not fired(lint(src, lang=lang, rules={"commented-out-code"})), src

    def test_does_not_flag_equality_comparison(self):
        # `==` is not an assignment; a comment musing about a condition is prose.
        assert not fired(lint("// fails when count == 0 on the first pass\nint x = 1;\n",
                              lang="c", rules={"commented-out-code"}))

    def test_flags_declaration_with_type_or_keyword(self):
        for lang, src in (("javascript", "// const x = computeTotal(amount);\nconst y = 1;\n"),
                          ("c", "// int total = amount * 100;\nint y = 1;\n")):
            assert fired(lint(src, lang=lang, rules={"commented-out-code"})), lang

    def test_works_in_go(self):
        src = "package p\nfunc F() {\n\t// total = computeTotal(amount, cur)\n\tx := 1\n}\n"
        assert fired(lint(src, lang="go", rules={"commented-out-code"}))

    def test_works_in_swift(self):
        src = "func f() {\n    // total = amount * 100\n    let x = 1\n}\n"
        assert fired(lint(src, lang="swift", rules={"commented-out-code"}))

    def test_does_not_flag_key_equals_prose(self):
        # Regression: `key = value` prose ("default = usd") is not commented-out
        # code. The RHS must carry a code signal (op/call/number/quote/member).
        for c in ("// default = usd\n",
                  "// mode = fast and safe\n",
                  "// timeout = how long we wait\n"):
            assert not fired(lint(c + "let y = 1\n", lang="swift",
                                  rules={"commented-out-code"})), c

    def test_does_not_flag_prose_sentence_with_parenthetical(self):
        # Regression from self-dogfooding: a prose sentence whose `=` and
        # parenthetical look expression-ish ("Pass = ... (LLM + network), not a
        # gate.") must not read as code. Natural-language tells gate the heuristic.
        for c in ("# Pass = every scenario passes every run. Smoke test (LLM + network), not a CI gate.\n",
                  "# Score = correctness (precision + recall), not raw counts.\n"):
            assert not fired(lint(c + "x=1\n", lang="shell",
                                  rules={"commented-out-code"})), c

    def test_does_not_flag_env_prefixed_usage_example(self):
        # Regression: an env-var-prefixed command in a comment is a usage example
        # (`MODEL=foo bash run.sh`), not dead code. A real assignment with no
        # trailing command token still fires (see config-assign test below).
        for c in ("#         MODEL=sonnet-4-thinking bash eval/run_description.sh\n",
                  "# RUNS=3 bash eval/run_description.sh\n",
                  "# DEBUG=1 ./run.sh --verbose\n"):
            assert not fired(lint(c + "x=1\n", lang="shell",
                                  rules={"commented-out-code"})), c

    def test_still_flags_real_config_assignment(self):
        # Guard against over-exemption: a bare `NAME = value` config line (no
        # trailing command, real numeric RHS) is still commented-out code.
        assert fired(lint("# MAX_RETRIES = 5\nx=1\n", lang="shell",
                          rules={"commented-out-code"}))

    def test_fires_inside_block_comment(self):
        src = "/*\n total = amount * 100\n*/\nlet y = 1\n"
        assert fired(lint(src, lang="swift", rules={"commented-out-code"}))


# --- string-awareness: markers inside literals must not fire ----------------

class TestStringAwareness:
    def test_hash_inside_python_string_is_not_a_comment(self):
        assert not fired(lint('url = "https://x/#as requested"\n', rules={"notes-to-self"}))

    def test_slashes_inside_string_are_not_a_comment(self):
        src = 'const u = "http://x";  // as requested\nconst y = 1;\n'
        # The real trailing comment still fires; the in-string `//` does not add a second.
        out = lint(src, lang="javascript", rules={"notes-to-self"})
        assert len(out) == 1

    def test_rust_lifetime_does_not_swallow_trailing_comment(self):
        # Regression: a lone `'` (lifetime) used to open a phantom string and eat
        # the `//` comment after it.
        assert fired(lint("fn g(x: &'a str) {} // as requested\nlet y = 1;\n",
                          lang="rust", rules={"notes-to-self"}))

    def test_go_rune_literal_is_skipped(self):
        # A real rune literal is consumed; the trailing comment still fires.
        assert fired(lint("r := '\\n' // as requested\nx := 1\n",
                          lang="go", rules={"notes-to-self"}))

    def test_char_literal_with_slashes_is_not_a_comment(self):
        # `'/'` is a char literal, not the start of a `//` comment.
        out = lint("char c = '/'; // as requested\nint y = 1;\n",
                   lang="c", rules={"notes-to-self"})
        assert len(out) == 1


# --- cross-cutting structural invariants ------------------------------------

class TestStructuralInvariants:
    SRC = (
        'def to_cents(dollars):\n'
        '    # as requested, default scale\n'
        '    # total = dollars * 100\n'
        '    return int(dollars * 100)\n'
    )

    def test_every_action_is_known(self):
        assert all(f.action == "delete" for f in lint(self.SRC))

    def test_line_numbers_are_one_based_and_accurate(self):
        out = {(f.rule, f.line) for f in lint(self.SRC)}
        assert ("notes-to-self", 2) in out and ("commented-out-code", 3) in out

    def test_findings_are_sorted_by_line(self):
        lines = [f.line for f in lint(self.SRC)]
        assert lines == sorted(lines)

    def test_rules_filter_restricts_output(self):
        only = lint(self.SRC, rules={"notes-to-self"})
        assert only and {f.rule for f in only} == {"notes-to-self"}

    def test_both_rules_coexist(self):
        assert fired(lint(self.SRC)) == {
            ("notes-to-self", "delete"), ("commented-out-code", "delete")}


def test_unknown_extension_is_skipped(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("# as requested\n")
    assert deslop.lint_path(str(p)) == []


# --- diff scope -------------------------------------------------------------

class TestDiffScope:
    def test_added_lines_tracks_new_file_numbers(self):
        diff = (
            "diff --git a/f.py b/f.py\n"
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -1,2 +1,3 @@\n"
            " x = 1\n"
            "+# as requested\n"
            " y = 2\n"
        )
        assert deslop.added_lines(diff) == {"f.py": {2}}

    def test_new_file_marks_all_added(self):
        diff = ("--- /dev/null\n"
                "+++ b/new.py\n"
                "@@ -0,0 +1,2 @@\n"
                "+# total = 1\n"
                "+x = 1\n")
        assert deslop.added_lines(diff) == {"new.py": {1, 2}}


# --- CLI --------------------------------------------------------------------

class TestCli:
    def test_nonzero_exit_when_findings(self, tmp_path, capsys):
        p = tmp_path / "f.py"
        p.write_text("# as requested\nx = 1\n")
        assert deslop.main([str(p)]) == 1

    def test_zero_exit_when_clean(self, tmp_path):
        p = tmp_path / "f.py"
        p.write_text("# Stripe sends cents for JPY; do not multiply\nx = 1\n")
        assert deslop.main([str(p)]) == 0

    def test_json_format_is_valid(self, tmp_path, capsys):
        import json
        p = tmp_path / "f.py"
        p.write_text("# as requested\nx = 1\n")
        deslop.main([str(p), "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload and payload[0]["rule"] == "notes-to-self"

    def test_rules_filter(self, tmp_path):
        p = tmp_path / "f.py"
        p.write_text("# total = amount * 100\nx = 1\n")
        # Only R1 enabled -> the commented-out line is not flagged -> clean exit.
        assert deslop.main([str(p), "--rules", "notes-to-self"]) == 0
