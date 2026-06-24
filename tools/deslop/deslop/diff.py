"""Parse a unified diff into {path: set(added line numbers in the new file)}."""

from __future__ import annotations

import re

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added_lines(diff: str) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    path = None
    new_line = 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            path = None if target == "/dev/null" else re.sub(r"^b/", "", target)
            continue
        if line.startswith("--- ") or line.startswith("diff "):
            continue
        m = _HUNK.match(line)
        if m:
            new_line = int(m.group(1))
            continue
        if path is None:
            continue
        if line.startswith("+"):
            result.setdefault(path, set()).add(new_line)
            new_line += 1
        elif line.startswith("-"):
            continue
        elif line.startswith("\\"):
            continue
        else:
            new_line += 1
    return result
