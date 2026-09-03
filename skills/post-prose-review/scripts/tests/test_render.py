import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).parents[1] / "render.py"
SPEC = importlib.util.spec_from_file_location("prose_render", MODULE)
assert SPEC and SPEC.loader
render = importlib.util.module_from_spec(SPEC)
sys.modules["prose_render"] = render
SPEC.loader.exec_module(render)

DIFF = """diff --git a/src/a.ts b/src/a.ts
--- a/src/a.ts
+++ b/src/a.ts
@@ -0,0 +1,4 @@
+// first
+run(); // inline
+// third
+const value = true;
"""
COMMIT_ID = "a" * 40


def finding(**changes):
    value = {
        "path": "src/a.ts",
        "start_line": 1,
        "end_line": 1,
        "action": "tighten",
        "replacement": "// useful reason",
        "rationale": "Narrates the code.",
        "confidence": "high-confidence",
    }
    value.update(changes)
    return value


class RenderTests(unittest.TestCase):
    def run_render(self, findings, source=None):
        source = source or "// first\nrun(); // inline\n// third\nconst value = true;\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "a.ts").write_text(source)
            with patch.object(render, "_source_head", return_value=COMMIT_ID):
                return render.render({"comment_findings": findings}, DIFF, root, COMMIT_ID)

    def test_comment_only_edit_becomes_suggestion(self):
        review, diagnostics = self.run_render([finding()])
        self.assertIn("```suggestion", review["comments"][0]["body"])
        self.assertEqual([], diagnostics)

    def test_inline_and_executable_lines_become_plain_notes(self):
        for line in (2, 4):
            with self.subTest(line=line):
                review, diagnostics = self.run_render([
                    finding(start_line=line, end_line=line, action="delete", replacement="")
                ])
                self.assertNotIn("```suggestion", review["comments"][0]["body"])
                self.assertIn("downgraded", diagnostics[0])

    def test_mixed_range_becomes_plain_note(self):
        review, _ = self.run_render([
            finding(start_line=1, end_line=2, replacement="// shorter")
        ])
        self.assertNotIn("```suggestion", review["comments"][0]["body"])

    def test_directive_and_block_delimiter_become_plain_notes(self):
        directive_diff = DIFF.replace("// first", "// eslint-disable-next-line no-console")
        source = "// eslint-disable-next-line no-console\nrun(); // inline\n// third\nconst value = true;\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "a.ts").write_text(source)
            with patch.object(render, "_source_head", return_value=COMMIT_ID):
                review, _ = render.render({
                    "comment_findings": [finding(action="delete", replacement="")]
                }, directive_diff, root, COMMIT_ID)
        self.assertNotIn("```suggestion", review["comments"][0]["body"])

        block_diff = DIFF.replace("// first", "/* first */")
        block_source = source.replace("// eslint-disable-next-line no-console", "/* first */")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "a.ts").write_text(block_source)
            with patch.object(render, "_source_head", return_value=COMMIT_ID):
                review, _ = render.render({
                    "comment_findings": [finding(action="delete", replacement="")]
                }, block_diff, root, COMMIT_ID)
        self.assertNotIn("```suggestion", review["comments"][0]["body"])

    def test_review_is_pinned_to_full_commit_sha(self):
        review, _ = self.run_render([finding()])
        self.assertEqual(COMMIT_ID, review["commit_id"])
        with self.assertRaises(ValueError):
            render.render({"comment_findings": []}, DIFF, Path("."), "abc123")
        with patch.object(render, "_source_head", return_value="b" * 40):
            with self.assertRaises(ValueError):
                render.render({"comment_findings": []}, DIFF, Path("."), COMMIT_ID)

    def test_borderline_findings_are_omitted_from_inline_review(self):
        review, diagnostics = self.run_render([finding(confidence="borderline")])
        self.assertEqual([], review["comments"])
        self.assertIn("omitted borderline", diagnostics[0])

    def test_executable_python_directive_is_not_applyable(self):
        diff = DIFF.replace("// first", "# cython: boundscheck=False")
        source = "# cython: boundscheck=False\nrun(); // inline\n// third\nconst value = true;\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "a.ts").write_text(source)
            python_path = root / "src" / "a.py"
            python_path.write_text(source, encoding="utf-8")
            python_diff = diff.replace("src/a.ts", "src/a.py")
            with patch.object(render, "_source_head", return_value=COMMIT_ID):
                review, _ = render.render(
                    {"comment_findings": [finding(path="src/a.py", action="delete", replacement="")]},
                    python_diff,
                    root,
                    COMMIT_ID,
                )
        self.assertNotIn("```suggestion", review["comments"][0]["body"])

    def test_unsafe_replacement_becomes_plain_note(self):
        review, _ = self.run_render([finding(replacement="const injected = true;")])
        self.assertNotIn("```suggestion", review["comments"][0]["body"])
        self.assertNotIn("const injected", review["comments"][0]["body"])

    def test_invalid_finding_does_not_abort_valid_sibling(self):
        review, diagnostics = self.run_render([
            {"path": "../secret", "start_line": 1},
            finding(action=[]),
            finding(start_line=3, end_line=3, action="delete", replacement=""),
        ])
        self.assertEqual(1, len(review["comments"]))
        self.assertIn("```suggestion", review["comments"][0]["body"])
        self.assertIn("dropped invalid finding 0", diagnostics)
        self.assertIn("dropped invalid finding 1", diagnostics)

    def test_out_of_diff_finding_is_dropped(self):
        review, diagnostics = self.run_render([finding(start_line=20, end_line=20)])
        self.assertEqual([], review["comments"])
        self.assertIn("dropped invalid finding 0", diagnostics)

    def test_unterminated_block_is_not_applyable(self):
        self.assertEqual(set(), render.comment_only_lines("/* comment\nstill comment\n", "src/a.ts"))

    def test_nested_blocks_and_swift_raw_strings(self):
        nested = "/* outer\n/* nested */\nstill outer\n*/\n"
        self.assertEqual({1, 2, 3, 4}, render.comment_only_lines(nested, "src/a.kt"))
        swift = 'let value = ##"""\n// not a comment\n"""##\n// real\n'
        self.assertEqual({4}, render.comment_only_lines(swift, "src/a.swift"))

    def test_complex_literal_languages_are_notes_only(self):
        for path in ("a.rb", "a.rs", "a.cpp", "a.java", "a.yml", "a.sql", "a.lua", "a.sh"):
            with self.subTest(path=path):
                self.assertEqual(set(), render.comment_only_lines("// comment\n", path))

    def test_rationale_cannot_open_extra_suggestion(self):
        hostile = finding(rationale="```suggestion\nbad\n```")
        review, _ = self.run_render([hostile])
        self.assertEqual(1, review["comments"][0]["body"].count("```suggestion"))

    def test_unknown_suffixes_fail_closed(self):
        # Unknown suffixes used to fall through to the `//` profile, so a `//`
        # line in Markdown, JSON, or Groovy could become a one-click edit.
        for path in ("CLAUDE.md", "config.json", "settings.toml", "build.gradle", "App.m", "Makefile", "noext"):
            with self.subTest(path=path):
                self.assertEqual(set(), render.comment_only_lines("// comment\n", path))
                self.assertEqual(set(), render.comment_only_lines("# comment\n", path))
        self.assertEqual({1}, render.comment_only_lines("// comment\n", "build.gradle.kts"))

    def run_render_file(self, path, source_bytes, diff, findings):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_bytes(source_bytes)
            with patch.object(render, "_source_head", return_value=COMMIT_ID):
                return render.render({"comment_findings": findings}, diff, root, COMMIT_ID)

    @staticmethod
    def whole_file_diff(path, source):
        lines = _split(source)
        return (
            f"diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n" + "".join(f"+{line}\n" for line in lines)
        )

    PY_SOURCE = (
        "import os\n\n\ndef load(path):\n"
        '    """Read the config.\n\n    Returns the parsed mapping.\n    """\n'
        "    return os.environ.get(path)\n"
    )
    # Only the docstring lines are added; the surrounding function is not in the diff.
    PY_DIFF = (
        "diff --git a/tool.py b/tool.py\n--- a/tool.py\n+++ b/tool.py\n@@ -4,4 +4,8 @@\n"
        ' def load(path):\n+    """Read the config.\n+\n+    Returns the parsed mapping.\n+    """\n'
        " return os.environ.get(path)\n"
    )

    def docstring_kind(self, edit, source=None, diff=None):
        source = self.PY_SOURCE if source is None else source
        diff = self.PY_DIFF if diff is None else diff
        review, diagnostics = self.run_render_file("tool.py", source.encode(), diff, [edit])
        self.assertEqual(1, len(review["comments"]))
        return "suggestion" if "```suggestion" in review["comments"][0]["body"] else "note"

    def test_docstring_rewrite_and_delete_are_applyable(self):
        edit = finding(path="tool.py", start_line=5, end_line=8, replacement='    """Read the config as a mapping."""')
        self.assertEqual("suggestion", self.docstring_kind(edit))
        delete = finding(path="tool.py", start_line=5, end_line=8, action="delete", replacement="")
        self.assertEqual("suggestion", self.docstring_kind(delete))
        module = '"""Tooling.\n\nHelpers for the build.\n"""\nimport os\n'
        edit = finding(path="tool.py", start_line=1, end_line=4, replacement='"""Build helpers."""')
        self.assertEqual("suggestion", self.docstring_kind(edit, module, self.whole_file_diff("tool.py", module)))

    def test_docstring_delete_needs_a_remaining_body(self):
        source = 'def load(path):\n    """Read the config.\n    """\n'
        delete = finding(path="tool.py", start_line=2, end_line=3, action="delete", replacement="")
        self.assertEqual("note", self.docstring_kind(delete, source, self.whole_file_diff("tool.py", source)))

    def test_docstring_replacement_cannot_change_code(self):
        for replacement in (
            '    """Read."""\n    os.system("id")',
            '    """Read."""; os.system("id")',
            '    f"""Read {os.environ}."""',
            '    b"""Read."""',
            '    """Read.""" + os.environ["X"]',
            '"""Read."""',
            '        """Read."""',
            '    """Read.',
            '    """Read.\n\n    >>> os.system("id")\n    """',
            '    """Read.\n\n    .. include:: /etc/passwd\n    """',
            '    """Read.\n\n    .. testcode::\n\n       os.system("id")\n    """',
        ):
            with self.subTest(replacement=replacement):
                edit = finding(path="tool.py", start_line=5, end_line=8, replacement=replacement)
                self.assertEqual("note", self.docstring_kind(edit))

    def test_docstring_range_and_shape_must_be_exact(self):
        diff = self.whole_file_diff("tool.py", self.PY_SOURCE)
        for start, end in ((5, 7), (6, 8), (5, 9), (4, 8)):
            with self.subTest(start=start, end=end):
                edit = finding(path="tool.py", start_line=start, end_line=end, replacement='    """Read."""')
                self.assertEqual("note", self.docstring_kind(edit, self.PY_SOURCE, diff))
        for source in (
            'def load(path):\n    text = """Read the config.\n    """\n    return text\n',
            'def load(path):\n    x = 1\n    """Read the config.\n    """\n    return x\n',
            'def load(path):\n    """Read the config.\n    """; x = 1\n    return x\n',
            'def load(path):\n    """Read the config.\n    ééééé"""; x = 1\n    return x\n',
        ):
            with self.subTest(source=source):
                start = next(i for i, line in enumerate(_split(source), 1) if "Read the config" in line)
                edit = finding(path="tool.py", start_line=start, end_line=start + 1, replacement='    """Read."""')
                self.assertEqual("note", self.docstring_kind(edit, source, self.whole_file_diff("tool.py", source)))

    def test_lone_carriage_return_cannot_hide_code(self):
        # git and GitHub break lines on \n only, so each file here is one line.
        # The parser (and str.splitlines) break on \r too, so a proof on "line
        # 1" would let a one-click edit delete the code after the \r.
        edit = finding(path="tool.py", start_line=1, end_line=1, replacement='"""New."""')
        diff = 'diff --git a/tool.py b/tool.py\n--- /dev/null\n+++ b/tool.py\n@@ -0,0 +1 @@\n+"""Old."""\rverify(request)\n'
        self.assertEqual("note", self.docstring_kind(edit, '"""Old."""\rverify(request)\n', diff))
        diff = "diff --git a/src/a.ts b/src/a.ts\n--- /dev/null\n+++ b/src/a.ts\n@@ -0,0 +1 @@\n+// note\rrun();\n"
        delete = finding(start_line=1, end_line=1, action="delete", replacement="")
        review, _ = self.run_render_file("src/a.ts", b"// note\rrun();\n", diff, [delete])
        self.assertNotIn("```suggestion", review["comments"][0]["body"])

    def test_added_text_breaks_lines_only_on_newline(self):
        diff = "diff --git a/src/a.ts b/src/a.ts\n--- /dev/null\n+++ b/src/a.ts\n@@ -0,0 +1,2 @@\n+// one\rrun();\n+// two\u2028run();\n"
        self.assertEqual({"src/a.ts": {1: "// one\rrun();", 2: "// two\u2028run();"}}, render.added_text(diff))

    def test_replacement_cannot_smuggle_a_line_terminator(self):
        for terminator in ("\r", "\u2028", "\u2029", "\x85", "\x0c", "\x0b"):
            with self.subTest(terminator=repr(terminator)):
                review, _ = self.run_render([finding(replacement=f"// useful reason{terminator}exfiltrate();")])
                self.assertNotIn("```suggestion", review["comments"][0]["body"])

    def test_non_utf8_file_does_not_fail_the_review(self):
        raw = b'x = "caf\xe9"\n# as requested\n'
        text = raw.decode("utf-8", "surrogateescape")
        diff = "diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n" + "".join(
            f"+{line}\n" for line in _split(text)
        )
        clean = finding(path="a.py", start_line=2, end_line=2, action="delete", replacement="")
        dirty = finding(path="a.py", start_line=1, end_line=1, action="delete", replacement="")
        review, _ = self.run_render_file("a.py", raw, diff, [clean, dirty])
        bodies = [comment["body"] for comment in review["comments"]]
        self.assertEqual(2, len(bodies))
        self.assertIn("```suggestion", bodies[0])
        self.assertNotIn("```suggestion", bodies[1])

    def test_replacement_cannot_carry_hidden_characters(self):
        # bidi overrides, zero-width, BOM, Arabic letter mark, a Unicode tag
        # (ASCII smuggling), C0/C1 controls, private use, unassigned.
        for control in (
            "\u202e", "\u200b", "\u2066", "\ufeff", "\u2060", "\u061c",
            "\U000E0041", "\x1b", "\x7f", "\x9f", "\U000F0000", "\U000E0080",
        ):
            with self.subTest(control=repr(control)):
                review, _ = self.run_render([finding(replacement=f"// useful{control} reason")])
                self.assertNotIn("```suggestion", review["comments"][0]["body"])
        review, _ = self.run_render([finding(replacement="// raison utile — c'est important")])
        self.assertIn("```suggestion", review["comments"][0]["body"])

    def test_replacement_trailing_newline_is_not_an_extra_blank_line(self):
        review, _ = self.run_render([finding(replacement="// useful reason\n")])
        self.assertTrue(review["comments"][0]["body"].endswith("```suggestion\n// useful reason\n```"))

    def test_string_literal_content_is_never_comment_only(self):
        # Regression: escape processing inside raw literals, first-three-quote
        # closing for Kotlin, and unknown JS regexes each flipped quote state so
        # the next string's body scanned as code and its `//` line became a
        # one-click target.
        cases = (
            ("a.go", "var a = `C:\\`\nvar b = `\n// inside raw string b\n`\n// real\n", 5),
            ("a.kt", 'val a = """C:\\"""\nval b = """\n// inside raw string b\n"""\n// real\n', 5),
            ("a.kt", 'val a = """say "hi""""\nval b = """\n// inside raw string b\n"""\n// real\n', 5),
            ("a.kt", 'fun `has a " quote`() {}\nval b = "x"\n// real\n', 3),
            ("a.ts", 's.replace(/"/g, "&quot;");\nconst t = `\n// inside template\n`;\n// real\n', 5),
            ("a.swift", 'let a = #"C:\\"#\nlet b = """\n// inside string b\n"""\n// real\n', 5),
        )
        for path, source, real in cases:
            with self.subTest(path=path):
                self.assertEqual({real}, render.comment_only_lines(source, path))

    def test_ambiguous_javascript_slash_fails_closed(self):
        # After `)` only a parser knows regex from division; when the two
        # readings disagree about quotes, nothing in the file is applyable.
        for source in ('const r = (a) / "b" / c;\n// note\n', 'if (x) /"/.test(y);\n// note\n'):
            with self.subTest(source=source):
                self.assertEqual(set(), render.comment_only_lines(source, "a.ts"))
        self.assertEqual({2}, render.comment_only_lines("const r = (a) / b / c;\n// note\n", "a.ts"))
        self.assertEqual({2}, render.comment_only_lines('return /"/.test(y);\n// note\n', "a.ts"))

    def test_template_expressions_are_code(self):
        # Regression: a nested template closed the outer one and the scanner
        # stayed desynced for the rest of the file.
        source = (
            "const s = `\n  ${a ? `//x` : `y`}\n  // still inside the template\n"
            "  ${b ? ` as \\`${c}\\`` : \"\"}\n`;\n// real\n"
        )
        self.assertEqual({6}, render.comment_only_lines(source, "a.ts"))
        kotlin = (
            'val s = "seeking ${\n    position // inside expression\n}"\n// real\n'
            'val t = """\n// inside raw ${x}\n"""\n// also real\n'
        )
        self.assertEqual({4, 8}, render.comment_only_lines(kotlin, "a.kt"))

    def test_unclosed_single_line_string_fails_the_file_closed(self):
        jsx = "export const A = () => (\n  <p>Don't do that</p>\n);\n// real\n"
        self.assertEqual(set(), render.comment_only_lines(jsx, "a.tsx"))
        self.assertEqual(set(), render.comment_only_lines('val a = "open\n// real\n', "a.kt"))
        self.assertEqual({3}, render.comment_only_lines("const a = 'x\\\n';\n// real\n", "a.ts"))

    def test_division_before_a_comment_is_not_a_regex(self):
        self.assertEqual({2}, render.comment_only_lines("x = i++ / 2; // it's\n// real\n", "a.ts"))
        self.assertEqual({2}, render.comment_only_lines("x = (a) / 2; // it's\n// real\n", "a.ts"))

    def test_grammars_without_string_literals(self):
        shader = '// the "paused" treatment\nfloat4 c = tex.sample(s, uv); // gamma\n'
        for path in ("Waveform.metal", "aura.glsl"):
            self.assertEqual({1}, render.comment_only_lines(shader, path))
        xcconfig = '#include "base.xcconfig"\n// "Designed for iPad"\nURL = https:/$()/x.com // c\n'
        self.assertEqual({2}, render.comment_only_lines(xcconfig, "Config/suno.xcconfig"))
        self.assertEqual({1}, render.comment_only_lines("// note\nexport {};\n", "a.mts"))

    def test_division_after_brace_bang_or_line_start_fails_closed_on_quotes(self):
        # `{} / 2`, TypeScript's `a! / 2`, and a line-leading `/` all read as
        # a regex to a lexer without a parser; when the "regex" would swallow
        # a quote the file yields nothing.
        for source in (
            'const x = {} / `a/` / `\n// inside template\n`;\n// real\n',
            'const x = a! / `a/` / `\n// inside template\n`;\n// real\n',
            'const x = a\n/ `a/` / `\n// inside template\n`;\n// real\n',
        ):
            with self.subTest(source=source):
                self.assertEqual(set(), render.comment_only_lines(source, "a.ts"))
        self.assertEqual({2}, render.comment_only_lines("if (x) {} /re/.test(y);\n// real\n", "a.ts"))

    def test_regex_scan_stops_at_a_continued_line(self):
        # Regression: a `\` before the newline was stepped over as an escape,
        # so the newline was never counted and every later line was off by one.
        source = 'const a = {} / "x\\\ny/"; // "\nrun();\n// real\n'
        self.assertEqual({4}, render.comment_only_lines(source, "a.ts"))

    def test_swift_interpolation_is_code(self):
        # Regression: `\(` was read as an escape, so a string inside the
        # interpolation closed the outer literal and a `//` in it swallowed
        # the rest of the line, including a `"""` opener.
        source = 'let s = "\\("//")"; let t = """\n// inside string t\n"""\nprint(t)\n// real\n'
        self.assertEqual({5}, render.comment_only_lines(source, "main.swift"))
        self.assertEqual({2}, render.comment_only_lines('let s = "\\(f(a, (b)))"\n// real\n', "m.swift"))
        # Extended delimiters interpolate with `\#(` and escape with `\#`.
        raw = 'let s = #"\\#("//")"#; let t = """\n// in t\n"""\n// real\n'
        self.assertEqual({4}, render.comment_only_lines(raw, "m.swift"))
        self.assertEqual({4}, render.comment_only_lines('let s = #"\\#"// "#; let t = """\n// in t\n"""\n// real\n', "m.swift"))
        self.assertEqual({2}, render.comment_only_lines('let s = #"\\("#\n// real\n', "m.swift"))
        self.assertEqual({2}, render.comment_only_lines("let x = ####\n// real\n", "m.swift"))

    def test_swift_raw_line_continuation_keeps_line_numbers(self):
        # Regression: `\#` before a newline in a `#"""` string is a line
        # continuation. The raw-escape path consumed the newline without
        # counting it, so every later line was numbered one too low and
        # `code()` was reported where `// c` really was.
        source = 'func code() {}\nlet s = #"""\nabc\\#\ndef\\#\nghi\n"""#\ncode()\ncode()\n// c\n'
        self.assertEqual({9}, render.comment_only_lines(source, "m.swift"))
        self.assertEqual({2}, render.comment_only_lines('let s = #"a\\#"b"#\n// c\n', "m.swift"))
        self.assertEqual(set(), render.comment_only_lines('let s = #"a\\#', "m.swift"))

    def test_metal_has_string_literals(self):
        # Regression: the shader profile declared Metal string-free, so a
        # `/*` inside a string opened a block comment over a kernel body.
        source = (
            '#include <metal_stdlib>\nconstant char s[] = "/*";\n'
            "kernel void k(device int *o [[buffer(0)]]) {\n o[0] = 42;\n}\n"
            'constant char t[] = "*/";\n// real\n'
        )
        self.assertEqual({7}, render.comment_only_lines(source, "a.metal"))
        self.assertEqual({2}, render.comment_only_lines("int c = '/'; // t\n// real\n", "a.metal"))
        # C++ raw strings have delimiters the scanner does not model.
        self.assertEqual(set(), render.comment_only_lines('constant char s[] = R"(x)";\n// real\n', "a.metal"))
        # GLSL still has none, so a stray quote is not an opener.
        self.assertEqual({2}, render.comment_only_lines('vec4 f() { return q"; }\n// real\n', "a.glsl"))

    def test_html_like_comments_fail_javascript_closed(self):
        # Annex B: `<!--` anywhere and `-->` at a line start are comments in
        # scripts, so a `/*` after one is not a block opener. Only code
        # position counts; the markers are common inside string literals.
        for source in (
            'x = 1 <!-- /*\ndanger();\ny = "*/";\n// real\n',
            'x = 1;\n--> /*\ndanger();\ny = "*/";\n// real\n',
            'x = 1;\n/* a */ --> /*\ndanger();\ny = "*/";\n// real\n',
        ):
            for path in ("a.js", "a.cjs", "a.mjs", "a.ts"):
                with self.subTest(source=source, path=path):
                    self.assertEqual(set(), render.comment_only_lines(source, path))
        self.assertEqual({2}, render.comment_only_lines('const m = "<!-- bot -->";\n// real\n', "a.ts"))
        self.assertEqual({2}, render.comment_only_lines("const f = () => x-->0;\n// real\n", "a.ts"))

    def test_hashbang_line_is_code_and_hides_nothing(self):
        # A `/*` on the interpreter line is part of the hashbang, not a
        # block opener; the line itself is never an applyable edit.
        source = '#!/usr/bin/env node /*\ndanger();\ny = "*/";\n// real\n'
        for path in ("a.js", "a.mjs", "a.ts", "a.swift", "a.kts"):
            with self.subTest(path=path):
                self.assertEqual({4}, render.comment_only_lines(source, path))
        self.assertEqual(set(), render.comment_only_lines("#!/usr/bin/env node", "a.js"))
        self.assertEqual({3}, render.comment_only_lines("x\n#!/not/a/hashbang\n// real\n", "a.js"))

    def test_preprocessor_line_splice_is_not_editable(self):
        # A `//` comment ending in `\` comments out the next line; deleting
        # it would revive the code below, so neither line is comment-only.
        shader = "fragment float4 f() {\n // disabled below \\\n discard_fragment();\n return float4(1);\n}\n"
        for path in ("a.metal", "a.glsl"):
            with self.subTest(path=path):
                self.assertEqual(set(), render.comment_only_lines(shader, path))
        self.assertEqual({3}, render.comment_only_lines(" // x \\ \n y();\n// real\n", "a.glsl"))
        self.assertFalse(render._replacement_is_safe("// tighter \\", "a.metal"))

    def test_slash_scanner_fails_closed_on_foreign_line_terminators(self):
        # `\r` ends a `//` comment in JS, Swift, Kotlin, and Go but not in
        # git, so a comment can hide a string opener from the scanner.
        source = "// note\rconst s = `\n// inside template\n`;\n// real\n"
        self.assertEqual(set(), render.comment_only_lines(source, "a.ts"))
        self.assertEqual(set(), render.comment_only_lines("// a\u2028let s = \"\"\"\n// in\n\"\"\"\n", "a.swift"))

    def test_unterminated_string_at_end_of_file_proves_nothing(self):
        # An odd quote in a .strings table leaves the scanner in string mode
        # with no single-line rule to trip; the whole file fails closed.
        self.assertEqual(set(), render.comment_only_lines('// note\n"key" = "value;\n// later\n', "a.strings"))
        self.assertEqual(set(), render.comment_only_lines('// note\nval s = """\n// later\n', "a.kt"))

    def test_go_sys_and_lgtm_directives_need_their_exact_shape(self):
        self.assertTrue(render._is_directive("//sys getpid() (pid int)"))
        self.assertTrue(render._is_directive("// lgtm[js/xss]"))
        self.assertFalse(render._is_directive("// sys.argv is read here"))
        self.assertFalse(render._is_directive("// LGTM, ship it"))

    def test_xcconfig_has_no_block_comments(self):
        source = "/*\nOTHER_LDFLAGS = $(inherited) -Wl,-foo\n*/\n// real\n"
        self.assertEqual({4}, render.comment_only_lines(source, "a.xcconfig"))

    def test_jsx_files_are_not_applyable(self):
        # A JSX text child that starts with `//` is rendered text.
        source = "export const A = () => (\n <p>\n // rendered text\n </p>\n);\n"
        for path in ("a.tsx", "a.jsx"):
            with self.subTest(path=path):
                self.assertEqual(set(), render.comment_only_lines(source, path))

    def test_docblock_interior_annotations_are_directives(self):
        for text in (
            " * @jsxImportSource preact", " * @jest-environment jsdom", "// @vitest-environment jsdom",
            "// @jsx h", "/** @jsx h */", "// deno-fmt-ignore-file", "// Output: a",
            "// +kubebuilder:validation:Optional", "// scalafmt: { maxColumn = 80 }",
            "// $COVERAGE-OFF$", "// scalastyle:off",
            # Block-comment ESLint forms, JSDoc tags `tsc --checkJs` reads,
            # Go doc-tool conventions, and editor mode lines.
            "/* global foo */", "/* exported foo */", "/* eslint-env node */",
            " * @type {string}", " * @param {number} x", " * @returns {void}",
            " * @typedef {Object} Foo", "/** @template T */",
            "// Deprecated: use Bar", "// BUG(rsc): loses precision",
            # `go test` matches the output marker in any case.
            "// Unordered output:", "// output:", "// UNORDERED OUTPUT:",
            "// format: off", "// nolint:errcheck",
            "//goland:noinspection Foo", "/// sourcery: skipEquality",
            "# vim: set ts=4:", "# -*- mode: python -*-", "# Local Variables:",
        ):
            with self.subTest(text=text):
                self.assertTrue(render._is_directive(text.strip()))
        for text in (
            " * explains the why", "// plus one for the header", "// output of f is cached",
            # Prose that shares words with a case-sensitive Go marker.
            "// +1 for the null terminator", "// deprecated in favour of the new path",
            "// a global lock", "// exported for tests", "// bug in the parser",
            # KDoc tags carry no `{type}`, so they are editable prose.
            " * @param request the thing to send", " * @return the parsed body",
            " * @throws IOException when the socket closes",
        ):
            with self.subTest(text=text):
                self.assertFalse(render._is_directive(text.strip()))

    def test_fence_in_docstring_replacement_downgrades(self):
        # A bare ``` line would close the suggestion block early and GitHub
        # would apply only the lines above it.
        edit = finding(path="tool.py", start_line=5, end_line=8, replacement='    """Read.\n```\n    still docstring\n    """')
        self.assertEqual("note", self.docstring_kind(edit))

    def test_symlink_loop_downgrades_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "a.ts").symlink_to("a.ts")
            with patch.object(render, "_source_head", return_value=COMMIT_ID):
                review, diagnostics = render.render({"comment_findings": [finding()]}, DIFF, root, COMMIT_ID)
        self.assertNotIn("```suggestion", review["comments"][0]["body"])
        self.assertEqual(["downgraded finding 0 to a plain note"], diagnostics)

    def test_comment_resize_cannot_move_a_coding_cookie(self):
        # The comment path has the same hazard as a docstring: deleting two
        # header lines lifts a line-3 cookie into effect, and growing line 1
        # pushes a line-2 cookie out of it.
        cases = (
            ('# header\n# another\n# -*- coding: latin-1 -*-\nprint("\xe9")\n', 1, 2, ""),
            ('# header\n# -*- coding: latin-1 -*-\nx = "caf\xe9"\n', 1, 1, "# header\n# more"),
        )
        for source, start, end, replacement in cases:
            with self.subTest(source=source):
                added = source.split("\n")[:end]
                diff = (
                    "diff --git a/tool.py b/tool.py\n--- a/tool.py\n+++ b/tool.py\n"
                    f"@@ -0,0 +1,{len(added)} @@\n" + "".join(f"+{line}\n" for line in added)
                )
                action = "delete" if not replacement else "tighten"
                edit = finding(path="tool.py", start_line=start, end_line=end, replacement=replacement, action=action)
                self.assertEqual("note", self.docstring_kind(edit, source, diff))

    def test_python_uses_the_real_tokenizer(self):
        # Nested same-quote f-strings are Python 3.12 syntax; older tokenizers
        # reject them and the file fails closed. Either way the string body on
        # line 3 is never comment-only.
        nested = 'x = f"{"\\""}"\ny = """\n# inside string y\n"""\n# real\n'
        self.assertNotIn(3, render.comment_only_lines(nested, "a.py"))
        self.assertEqual({4}, render.comment_only_lines('x = """\n# inside\n"""\n# real\n', "a.py"))
        self.assertEqual({1}, render.comment_only_lines('# real\nx = "a\\\n# continued"\n', "a.py"))
        self.assertEqual(set(), render.comment_only_lines('x = "unterminated\n# looks real\n', "a.py"))

    def test_docstring_replacement_cannot_trail_a_directive(self):
        for replacement in (
            '    """Read."""  # type: ignore', '    """Read."""  # noqa', '    """Read."""  # pragma: no cover',
            # Parentheses make the Expr end at `)`, past a comment the AST
            # never sees; a backslash joins a second string onto the first.
            '    ("""Read.""" # type: ignore\n    )', '    ("""Read."""  # flake8: noqa\n    )',
            '    """Read.""" \\\n    """More."""', '    ("""Read.""")',
        ):
            with self.subTest(replacement=replacement):
                edit = finding(path="tool.py", start_line=5, end_line=8, replacement=replacement)
                self.assertEqual("note", self.docstring_kind(edit))
                self.assertFalse(render._docstring_edit_is_safe(self.PY_SOURCE, 5, 8, replacement))

    def test_parenthesized_docstring_is_not_applyable(self):
        # The head's own docstring can hide a directive behind a parenthesis
        # too; replacing it with a bare string would drop the directive.
        source = 'def load(path):\n    ("""Read the config.\n    """  # type: ignore\n    )\n    return 1\n'
        diff = (
            "diff --git a/tool.py b/tool.py\n--- a/tool.py\n+++ b/tool.py\n"
            "@@ -0,0 +1,5 @@\n" + "".join(f"+{line}\n" for line in source.splitlines())
        )
        edit = finding(path="tool.py", start_line=2, end_line=4, replacement='    """Read."""')
        self.assertEqual("note", self.docstring_kind(edit, source, diff))
        self.assertFalse(render._docstring_edit_is_safe(source, 2, 4, '    """Read."""'))

    def test_docstring_resize_cannot_move_a_coding_cookie(self):
        source = '"""m\n"""\n# -*- coding: latin-1 -*-\nx = "caf\xe9"\n'
        diff = (
            "diff --git a/tool.py b/tool.py\n--- a/tool.py\n+++ b/tool.py\n"
            '@@ -0,0 +1,2 @@\n+"""m\n+"""\n # -*- coding: latin-1 -*-\n x = "caf\xe9"\n'
        )
        edit = finding(path="tool.py", start_line=1, end_line=2, replacement='"""n"""')
        self.assertEqual("note", self.docstring_kind(edit, source, diff))

    def test_docstring_replacement_cannot_add_any_rest_directive(self):
        for replacement in (
            '    """Read.\n\n    .. include :: /etc/passwd\n    """',
            '    """Read.\n\n    .. ifconfig:: __import__("os").system("id")\n    """',
            '    """Read.\n\n    .. csv-table::\n       :file: /etc/passwd\n    """',
        ):
            with self.subTest(replacement=replacement):
                edit = finding(path="tool.py", start_line=5, end_line=8, replacement=replacement)
                self.assertEqual("note", self.docstring_kind(edit))

    def test_wider_directive_coverage(self):
        for replacement, path in (
            ("# nosec", "a.py"), ("# nosemgrep: rule-id", "a.py"), ("# pyre-ignore[16]", "a.py"),
            ("# yapf: disable", "a.py"), ("// c8 ignore next", "a.ts"), ("/* v8 ignore next */", "a.ts"),
            ("// tslint:disable", "a.ts"), ("// deno-lint-ignore no-explicit-any", "a.ts"),
            ("// @refresh reset", "a.tsx"), ("// @generated", "a.ts"), ("// NOSONAR", "a.kt"),
            ("// codeql[js/xss]", "a.ts"), ("// ktlint-disable no-wildcard-imports", "a.kt"),
            ("// @formatter:off", "a.kt"), ("// $COVERAGE-IGNORE$", "a.kt"),
            ("// sourcery: AutoMockable", "a.swift"), ("// periphery:ignore", "a.swift"),
            ("//lint:ignore SA1019 reason", "a.go"), ("//sys getpid() (pid int)", "a.go"),
            ("// #nosec G104", "a.go"), ("//nosec", "a.go"),
        ):
            with self.subTest(replacement=replacement):
                self.assertFalse(render._replacement_is_safe(replacement, path))
        for replacement, path in (
            ("// keep the socket open until the ack arrives", "a.ts"),
            ("# keep going after a transient error", "a.py"),
            ("// system calls are retried once", "a.go"),
        ):
            with self.subTest(replacement=replacement):
                self.assertTrue(render._replacement_is_safe(replacement, path))

    def test_pathological_source_downgrades_instead_of_crashing(self):
        deep = 'def load(path):\n    """Read."""\n    return ' + "not " * 60000 + "path\n"
        diff = 'diff --git a/tool.py b/tool.py\n--- a/tool.py\n+++ b/tool.py\n@@ -1,1 +1,2 @@\n def load(path):\n+    """Read."""\n'
        edit = finding(path="tool.py", start_line=2, end_line=2, replacement='    """Load."""')
        self.assertEqual("note", self.docstring_kind(edit, deep, diff))


def _split(text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


if __name__ == "__main__":
    unittest.main()
