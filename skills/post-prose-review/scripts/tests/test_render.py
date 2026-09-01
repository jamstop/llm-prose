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


if __name__ == "__main__":
    unittest.main()
