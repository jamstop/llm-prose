---
name: review-pr
description: Full PR review pass — check comments for bloat and review/rewrite the description in one go.
---

# Review PR

Run both review passes on the same target, resolving it once.

Target: if the user named a PR number or branch, review that. Otherwise use the current branch / local diff. Ask which only if genuinely ambiguous.

1. **Comments** — follow the `comment-bloat-review` skill. Flag bloated/redundant/LLM-residue comments with concrete fixes.
2. **Description** — follow the `pr-description-review` skill. Verdict on what's weak, then a ready-to-paste rewrite covering What/Why/How and interface changes.

Present the two sections separately under clear headings. If the user asks, apply comment edits and update the description.
