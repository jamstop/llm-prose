"""Invariants for the CLI surface: exit codes, output shape, and --diff scoping."""

import io
import json

from prose_lint import cli


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_exit_zero_when_clean(tmp_path, capsys):
    p = _write(tmp_path, "ok.py", "def f():\n    return 1\n")
    assert cli.main([str(p)]) == 0


def test_exit_one_when_findings_exceed_max(tmp_path, capsys):
    p = _write(tmp_path, "bad.py", "# as requested\nx = 1\n")
    assert cli.main([str(p)]) == 1


def test_max_raises_the_threshold(tmp_path, capsys):
    p = _write(tmp_path, "bad.py", "# as requested\nx = 1\n")
    assert cli.main([str(p), "--max", "1"]) == 0


def test_json_output_has_the_finding_schema(tmp_path, capsys):
    p = _write(tmp_path, "bad.py", "# as requested\nx = 1\n")
    cli.main([str(p), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list) and data
    assert set(data[0]) == {"file", "line", "rule", "action", "message"}


def test_rules_flag_filters_to_a_subset(tmp_path, capsys):
    p = _write(tmp_path, "bad.py", "# as requested\n# total = 1 * 2\nx = 1\n")
    cli.main([str(p), "--format", "json", "--rules", "notes-to-self"])
    data = json.loads(capsys.readouterr().out)
    assert {d["rule"] for d in data} == {"notes-to-self"}


def test_diff_mode_scopes_to_added_lines(tmp_path, capsys, monkeypatch):
    # Both lines are residue, but only line 2 is "added" in the diff.
    p = _write(tmp_path, "f.py", "# pre-existing as requested\n# as requested, new\nx = 1\n")
    diff = (
        f"--- a/{p}\n+++ b/{p}\n"
        "@@ -1,2 +1,3 @@\n"
        " # pre-existing as requested\n"
        "+# as requested, new\n"
        " x = 1\n"
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(diff))
    cli.main(["--diff", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert [d["line"] for d in data] == [2]
