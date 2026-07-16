---
name: review-prose
description: Review the prose layer of code changes — the comments in the diff and the PR description — for LLM bloat and clarity. Use when reviewing a PR or branch, finishing up a change, or when the user asks to review prose, clean up comments, or check a PR write-up. Reviews writing quality, not code correctness.
---

# Review Prose

Entry point for reviewing the *written* layer of a change: comments in the diff and the PR description. Not code correctness.

## 1. Figure out the context

Detect the situation before doing anything:

- `git rev-parse --is-inside-work-tree` — confirm this is a git repo. If not, there's nothing branch-based to review; ask the user for the file(s) or pasted diff to review comments in, and skip the description pass.
- `git branch --show-current` and `git status -s` — are they actively working on a branch with changes? If on the base branch with no diff, ask what to review.
- `gh pr view --json number,title,body,baseRefName` — does an open PR exist for this branch?

Pick the diff source from that:
- PR exists -> `gh pr diff <n>`; description = the PR body.
- Branch with changes, no PR -> `git diff <base>...HEAD` (or `git diff` / `--staged` for in-progress work); there's no description yet — offer to draft one.

For large diffs, work per file (`--name-only` first, then diff the files that actually changed comments/logic) instead of loading the whole diff at once.

## 2. Run both passes

Apply each rubric to the resolved target, **comments first** — its output feeds the description pass:

- **Comments** — follow the `comment-bloat-review` skill. It begins with a bundled deterministic pre-pass (`deslop`) on the diff, then layers judgment on top.
- **Description** — follow the `pr-description-review` skill (skip if not a git/PR context). Carry over the comment pass's harvest: rationale it moved out of comments with destination "PR description" is diff-backed Why/How material for the rewrite.

## 3. Output

Two clearly separated sections: **Comments** (flagged items grouped by file, with concrete fixes) and **Description** (verdict + ready-to-paste rewrite). Lead each with a one-line verdict. When the user asks, apply the comment edits and update the PR body. Keep the report tight.

For one pass only, use the `/prose-code-comments` or `/prose-pr-description` command. To leave the review **on the PR itself** — one-click suggestions or a stacked fix PR the owner can merge — follow the `post-prose-review` skill, but only when the user explicitly asks to post.
