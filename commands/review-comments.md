---
name: review-comments
description: Review the comments in a PR or local diff for bloat, redundancy, and LLM residue.
---

# Review Comments

Load and follow the `comment-bloat-review` skill, applying it to the target diff.

Target: if the user named a PR number or branch, review that (`gh pr diff <n>`). Otherwise review the local diff (`git diff` / `git diff --staged` / `git diff <base>...HEAD`). Ask which only if it's genuinely ambiguous.

Report flagged comments grouped by file with concrete fixes. If the user asks, apply the edits directly.
