---
name: comment-bloat-review
description: Review a diff for bloated, redundant, or LLM-residue comments and over-documentation, then propose tighter edits. Use when reviewing a PR or code changes, when the user asks to check comments, clean up comments, or trim documentation, or when comments look auto-generated.
disable-model-invocation: true
---

# Comment Bloat Review

Audit only the **added/changed** lines in a diff for comment bloat and over-documentation. Code logic is out of scope unless a comment is actively wrong.

Your value here is **judgment**, not pattern-matching. The two unambiguous, mechanical cases — exact-phrase LLM residue and commented-out code — are caught deterministically by the bundled `deslop` pre-pass (step 1). Spend your attention on what a regex can't decide: whether a comment narrates *what* instead of explaining *why*, whether a docstring restates the signature or earns its keep, whether it's a scratchpad note to the model vs. real intent for a human, whether it's gone stale against the changed code. When in doubt, that's exactly the call only you can make.

## 1. Get the diff

- A PR is named/numbered, or you're told to review a branch -> `gh pr diff <n>` (or `gh pr diff` on the current branch). Use `gh pr view <n> --json files,title,body` for context.
- Otherwise review local work: `git diff` (unstaged), `git diff --staged`, or `git diff <base>...HEAD` for a branch. Ask which only if ambiguous.

Focus on `+` lines. Pre-existing comments are out of scope unless the change made them stale.

**Deterministic pre-pass — run it first.** `deslop` is a stdlib-only script bundled in this skill (no install). Pipe the diff through it before you start reading:

```
git diff | python3 scripts/deslop.py --diff
# or, for a PR:  gh pr diff <n> | python3 scripts/deslop.py --diff
```

`scripts/deslop.py` is relative to this skill's directory. It reproducibly flags the two unambiguous cases — notes-to-self / LLM residue and commented-out code — and stays silent on everything debatable. Treat its hits as already decided; spend your own judgment on the rest (narration, why-over-what, doc-dump tightening, staleness). If the script can't be located or run for any reason, just proceed with judgment — it's an accelerant, not a gate. (On Python-only repos, `eradicate` and `pydoclint`/`docsig` are mature deeper checks for commented-out code and docstrings.)

## 2. Flag these patterns

- **Narration** — restates the code: `// increment counter`, `// import the module`, `// return result`. Delete.
- **LLM residue** — the model talking to itself or the user: `// As requested...`, `// Note: I changed this to...`, `// This should now handle...`, `// Updated per feedback`, changelog-in-code. Delete.
- **Doc dumps** — a giant header block or docstring restating signatures, or every param/return documented when names already say it. For an internal symbol, cut it. For a public API where a doc comment is warranted, *tighten* rather than delete: lead with a one-sentence summary, drop the params/returns the names already cover, and keep only the sections that add information (why a value is returned, errors/throws, safety, an example). See *Further reading* in the README for the per-language conventions.
- **Stale/contradictory** — comment no longer matches the changed code. Fix or delete.
- **Commented-out code** — dead code left behind. Delete (it's in git history).
- **Misplaced** — one big block where 1-2 inline notes at the tricky spots would serve better.
- **Design-doc density** — the trap the other patterns miss: a comment that is *correct and informative* but oversized for the code it annotates. Tells: multiple sentences of rationale chained with em-dashes; cross-references and narrative ("see the migration plan…", "that write path ships with…"); a doc comment longer than the function under it. Being packed with real information is not a defense — it's the failure mode. **Tighten to 1-2 direct lines about the adjacent code**; rationale at paragraph scale belongs in the PR description, the commit message, or docs, where it has room and an audience.

  ```swift
  // Before — every clause true, none of it earning its place here:
  /// Re-hydrates stored clips with their joined creator identity. Creator
  /// Profiles are the only join — one batch query for the whole set, not
  /// one per clip. Every other collection is already a column on the clip row.

  // After — one direct line about what the reader needs at this callsite:
  /// Loads all creator profiles in one batch query — no per-clip lookups.
  ```

## 3. Keep comments that earn their place

A comment earns its tokens when it explains what code **cannot**: intent, *why* over *what*, non-obvious trade-offs, constraints/invariants, gotchas, links to context (ticket/RFC/bug), required API doc conventions, safety/security/legal notes.

For each candidate, ask two things: **"What do I actually care about here — is this for a human or just the LLM's scratchpad?"** (keep human-relevant intent; cut scratchpad) and **"Could the code change so the comment isn't needed?"** (a clearer name or a named constant often beats a comment).

The bar is **annotation, not documentation**: a comment's job is to mark the one non-obvious thing about the code directly under it, in the fewest words that do it — usually one line, two at most. "It holds a lot of relevant information" is how bloat defends itself; relevance decides *whether* a comment exists, brevity decides its *size*, and information that outgrows two lines belongs in the PR, commit message, or docs.

**Review as a skeptical stranger, especially for comments you wrote.** If you authored the diff, the pass tends to confirm your own taste — the density that felt justified while writing still feels justified while reviewing. Counter it mechanically: for every comment over two lines, draft the one-line version first, then argue for each clause you'd restore. Most don't come back.

**If you wrote these comments in the current session, don't self-review — delegate.** Your context is where the bias lives: the rationale that justified each comment is still in it. Launch a fresh subagent (the Task/agent tool in Cursor and Claude Code) whose prompt contains only this skill's path (to read and follow) and the diff — no conversation history — and have it return the flag list; then apply its calls, arguing only against clear mistakes. If subagents aren't available, fall back to the draft-the-one-line-version protocol above on every multi-line comment, no exceptions.

## 4. Output

Group by file. For each flagged comment give: location, category, and a concrete fix (delete, or tightened rewrite). Lead with a one-line verdict (e.g. "4 to delete, 2 to tighten, rest fine"). When asked, apply the edits directly. Keep the report tight.
