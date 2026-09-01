---
name: comment-bloat-review
description: Review a diff for bloated, redundant, or LLM-residue comments and over-documentation, then propose tighter edits. Use when reviewing a PR or code changes, when the user asks to check comments, clean up comments, or trim documentation, or when comments look auto-generated.
disable-model-invocation: true
---

# Comment Bloat Review

Audit only the **added/changed** lines in a diff for comment bloat and over-documentation. Code logic is out of scope unless a comment is actively wrong.

Your value here is **judgment**, not pattern-matching. The bundled `deslop` pre-pass catches high-precision residue, numbered-step scaffolding, obvious adjacent-code narration, commented-out code, generated files, and deterministic PR-body debris. Spend your attention on what those conservative checks cannot decide: whether a comment explains *why*, whether a docstring earns its keep, whether content is a scratchpad note or real intent, and whether it has gone stale.

Every finding gets one of three actions: **delete** (the content has no audience), **tighten** (the kernel stays here, smaller), or **move** (the content is worth keeping but is in the wrong place — inline at the line it actually describes, or out of the code entirely into the PR description, commit message, or docs). Deleting good content because it was badly placed is a miss; move exists so it isn't.

## 1. Get the diff

- A PR is named/numbered, or you're told to review a branch -> `gh pr diff <n>` (or `gh pr diff` on the current branch). Use `gh pr view <n> --json files,title,body` for context.
- Otherwise review local work: `git diff` (unstaged), `git diff --staged`, or `git diff <base>...HEAD` for a branch. Ask which only if ambiguous.

Focus on `+` lines. Pre-existing comments are out of scope unless the change made them stale.

**Deterministic pre-pass — run it first.** `deslop` is a stdlib-only script bundled in this skill (no install). Pipe the diff through it before you start reading:

```
git diff | python3 scripts/deslop.py --diff
# or, for a PR:  gh pr diff <n> | python3 scripts/deslop.py --diff
```

`scripts/deslop.py` is relative to this skill's directory. It also accepts `--body-file <path>` for deterministic PR-description checks. Treat its hits as strong evidence, but inspect the source before reporting them. It intentionally skips generated files and stays conservative around trailing annotations, fenced examples, prose mappings, complex strings, and language directives. If the script cannot run, proceed with judgment and note the gap.

Run it with the system `python3` exactly as above — it is stdlib-only, so it
never needs a project environment. Never run it through `uv run`, `uv sync`, or
another environment manager during the review: those commands can regenerate
dependency lockfiles. A prose review must change nothing but comments and the
description. Never revert an unexpected lockfile or other repository change;
report it and obtain the user's explicit approval before cleanup.

## 2. Flag these patterns

- **Narration** — restates the code: `// increment counter`, `// import the module`, `// return result`. Delete.
- **LLM residue** — the model talking to itself or the user: `// As requested...`, `// Note: I changed this to...`, `// This should now handle...`, `// Updated per feedback`, changelog-in-code. Delete.
- **Doc dumps** — a giant header block or docstring restating signatures, or every param/return documented when names already say it. For an internal symbol, cut it. For a public API where a doc comment is warranted, *tighten* rather than delete: lead with a one-sentence summary, drop the params/returns the names already cover, and keep only the sections that add information (why a value is returned, errors/throws, safety, an example). See *Further reading* in the README for the per-language conventions.
- **Change-relative language** — the comment describes the *delta*, not the code: `// now handles retries`, `// the new implementation`, `// currently unsupported`, `// legacy path` with no referent. Timeless writing (per Google's style guide): describe the code as it stands — "now" is implied by the code existing, and these rot into lies at the next change. Rewrite timelessly or delete. (A PR description is timestamped content where "now" is fine; a comment isn't.)
- **Repetition across the diff** — the same fact stated in comments at two or more sites (a lifecycle rule in the file header, again at the writer, again at each reader). Each instance looks defensible alone, so per-comment review misses it: after the per-comment pass, do one cross-comment sweep asking "have I read this sentence before?" Keep the fact **once**, at the site where it's load-bearing (usually where the behavior happens, not where it's consumed); delete the echoes.
- **Stale/contradictory** — comment no longer matches the changed code. Fix or delete.
- **Commented-out code** — dead code left behind. Delete (it's in git history).
- **Misplaced** — one large block where focused notes at the tricky spots would serve better. **Move**, don't delete: place each surviving fact at the line it describes and drop the connective tissue.
- **Design-doc density** — the trap the other patterns miss: a comment that is *correct and informative* but oversized for the code it annotates. Tells include chained rationale, cross-references, and narrative better suited to durable docs or the PR. **Keep the local constraint concise and move the broader rationale** to the PR description, commit message, or docs. There is no universal line limit: API docs, safety contracts, and protocol invariants may need more room. If the survivor only restates the symbol or adjacent declaration, delete it.

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

Prefer the smallest comment that preserves the non-obvious fact. Size follows content and audience, not a fixed line count; public API contracts, examples, safety notes, and invariants can legitimately be multiline.

**Review as a skeptical stranger, especially for comments you wrote.** If you authored the diff, draft a shorter version for comments that feel disproportionate to their subject, then restore only clauses the reader needs at that location.

**If you wrote these comments in the current session — or you're re-reviewing after pushback — don't self-judge; delegate.** Your context is where the bias lives. Launch a fresh subagent whose prompt contains only this skill's path and the diff, then verify its calls against the source. If subagents are unavailable, draft a materially shorter version of each disproportionate comment and restore only necessary local facts. Finish by rereading the survivors as a skeptical reviewer.

## 4. Flag missing annotations — sparingly

Absence can be the defect too, but hold this to a far narrower bar than removal: over-commenting is the disease this skill treats, so suggest an addition only in the **gotcha class**, where a future editor will get it wrong without one:

- An **unexplained magic constant** — `604800`, a threshold, a port — with no name or referent.
- A **workaround** with no link to what it works around (ticket, upstream bug, incident).
- A **breakable invariant** — ordering, locking, units — that nothing in the code enforces or names.

Before suggesting a comment, apply the ethos rule first: **could the code change so the comment isn't needed?** A named constant (`SEVEN_DAYS = 604800`) or a clearer name beats a comment; suggest that form when it works. Any suggested comment meets the same bar as a kept one and stays as focused as its subject permits. Additions are suggestions in the report, never silently applied. If the code reads fine, add nothing.

## 5. Output

Group by file. For each flagged comment give: location, category, and a concrete fix — delete, a tightened rewrite, or a move with its **destination** (the inline line it belongs at, or the PR description / commit message / docs) and the content that moves. Lead with a one-line verdict (e.g. "4 to delete, 2 to tighten, 1 to move, rest fine"). **Hand evicted rationale to the description pass:** when this review runs as part of `/prose`, anything moved out with destination "PR description" is input for the `pr-description-review` pass — diff-backed material for its Why/How, not invention. When asked, apply the edits directly. Keep the report tight.

## 6. Final checks — verify each before reporting

1. `deslop` ran (or you noted why it couldn't); its hits were verified against source before reporting.
2. Every kept comment has a clear audience and adds information the code does not express.
3. No kept comment narrates the code, restates a signature, or tells a story that belongs in the PR/docs — *true and informative* did not excuse *oversized*.
4. **The cross-comment sweep ran and no fact survives in two places.**
5. **The verdict distribution is sane:** a comment-heavy diff with zero deletes can indicate that "tighten" was used as a courtesy verdict; re-check each tighten against deletion.
6. Every **move** names a destination and carries its content — nothing informative was deleted for being badly placed, and nothing evicted was dropped on the floor.
7. Any suggested **addition** is gotcha-class (magic constant, unlinked workaround, breakable invariant) and was checked against the code-change-first rule. Zero additions on code that reads fine.
8. If you wrote these comments in this session, or this is a re-review after pushback, a fresh subagent made the calls — not you.
