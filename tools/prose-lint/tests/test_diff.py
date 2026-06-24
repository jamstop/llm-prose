"""Invariants for unified-diff parsing (the basis of `--diff` scoping)."""

from prose_lint.diff import added_lines


def test_maps_added_lines_to_new_file_numbers():
    diff = (
        "diff --git a/f.py b/f.py\n"
        "--- a/f.py\n"
        "+++ b/f.py\n"
        "@@ -1,2 +1,3 @@\n"
        " import os\n"
        "+# as requested\n"
        " x = 1\n"
    )
    assert added_lines(diff) == {"f.py": {2}}


def test_strips_b_prefix_from_path():
    diff = "--- a/pkg/mod.py\n+++ b/pkg/mod.py\n@@ -0,0 +1 @@\n+x = 1\n"
    assert set(added_lines(diff)) == {"pkg/mod.py"}


def test_removed_lines_are_not_counted():
    diff = "--- a/f.py\n+++ b/f.py\n@@ -1,3 +1,2 @@\n x = 1\n-# old note\n y = 2\n"
    assert added_lines(diff) == {}


def test_dev_null_target_is_ignored():
    diff = "--- a/f.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x = 1\n"
    assert added_lines(diff) == {}


def test_tracks_line_numbers_across_multiple_hunks():
    diff = (
        "--- a/f.py\n+++ b/f.py\n"
        "@@ -1 +1,2 @@\n a\n+b\n"
        "@@ -10 +11,2 @@\n j\n+k\n"
    )
    assert added_lines(diff) == {"f.py": {2, 12}}
