---
name: comment-bloat-review
description: Review a diff for bloated, redundant, or LLM-residue comments and over-documentation, then propose tighter edits. Use when reviewing a PR or code changes, when the user asks to check comments, clean up comments, or trim documentation, or when comments look auto-generated.
disable-model-invocation: true
---

# Comment Bloat Review

Audit only the **added/changed** lines in a diff for comment bloat and over-documentation. Code logic is out of scope unless a comment is actively wrong.

## 1. Get the diff

- A PR is named/numbered, or you're told to review a branch -> `gh pr diff <n>` (or `gh pr diff` on the current branch). Use `gh pr view <n> --json files,title,body` for context.
- Otherwise review local work: `git diff` (unstaged), `git diff --staged`, or `git diff <base>...HEAD` for a branch. Ask which only if ambiguous.

Focus on `+` lines. Pre-existing comments are out of scope unless the change made them stale.

## 2. Flag these patterns

- **Narration** — restates the code: `// increment counter`, `// import the module`, `// return result`. Delete.
- **LLM residue** — the model talking to itself or the user: `// As requested...`, `// Note: I changed this to...`, `// This should now handle...`, `// Updated per feedback`, changelog-in-code. Delete.
- **Doc dumps** — a giant header block or docstring restating signatures, or every param/return documented when names already say it. Cut to the non-obvious parts.
- **Stale/contradictory** — comment no longer matches the changed code. Fix or delete.
- **Commented-out code** — dead code left behind. Delete (it's in git history).
- **Misplaced** — one big block where 1-2 inline notes at the tricky spots would serve better.

## 3. Keep comments that earn their place

A comment earns its tokens when it explains what code **cannot**: intent, *why* over *what*, non-obvious trade-offs, constraints/invariants, gotchas, links to context (ticket/RFC/bug), required API doc conventions, safety/security/legal notes.

For each candidate, ask: **"What do I actually care about here — is this for a human or just the LLM's scratchpad?"** Keep human-relevant intent; cut scratchpad. Comments should be as short as possible while holding as much relevant info as possible, and live only where relevant.

## 4. Output

Group by file. For each flagged comment give: location, category, and a concrete fix (delete, or tightened rewrite). Lead with a one-line verdict (e.g. "4 to delete, 2 to tighten, rest fine"). When asked, apply the edits directly. Don't pad the report — practice what this skill preaches.
