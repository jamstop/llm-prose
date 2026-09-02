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
