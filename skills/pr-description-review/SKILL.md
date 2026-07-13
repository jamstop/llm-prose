---
name: pr-description-review
description: Review or rewrite a pull request description so it covers What, Why, and How, and surfaces important code/interface changes. Use when reviewing a PR, writing or improving a PR description or summary, or when the user asks to check or fix a PR write-up.
disable-model-invocation: true
---

# PR Description Review

Judge a PR description against its actual diff, then **compose** one that is genuinely good to read — not just stripped of slop. Two distinct jobs: a short *verdict* (what's weak) and a *crafted rewrite* (what a reviewer would be glad to open). Spend real effort on the rewrite; that's the deliverable.

## 1. Gather

- Description + metadata: `gh pr view <n> --json title,body,files` (or `gh pr view` on current branch).
- Actual changes: `gh pr diff <n>` (or `git diff <base>...HEAD` locally). The description must match the diff — don't trust it blindly.
- **The repo's PR template** — check `.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE.md`, and `.github/PULL_REQUEST_TEMPLATE/`. Note its exact headings and furniture: a ticket line (`Resolves: …`), required sections, admonitions (`> [!NOTE]`), placeholder comments. Also skim 2-3 recently merged PRs (`gh pr list --state merged`) to see the house style in practice.

## 2. Required content

A good description answers, in order:

- **What** — what changed, in one or two plain sentences. Not a file list; the diff already lists files.
- **Why** — the motivation: problem, ticket/bug, user impact, or decision being implemented. This is the part LLMs most often omit. **Never invent it.** If the motivation isn't in the diff, a linked ticket, or the branch/commit context, ask the user — or leave the author-prompt placeholder described in section 4.
- **How** — the approach and any non-obvious design choices or trade-offs. Skip step-by-step narration of the diff.
- **Interface changes** — surface anything a consumer must notice: new/changed/removed public APIs, function signatures, props, endpoints, schema/migrations, config or env vars, breaking changes, feature flags. Call out breaking changes explicitly.

Include when relevant, don't manufacture: test plan / how to verify, screenshots for UI, rollout/migration notes, follow-ups or known gaps.

## 3. Flag these failure modes

- Title or body that just restates the branch name or the commit subject.
- Pure file/change enumeration with no Why.
- LLM filler: "This PR makes several improvements...", marketing adjectives, bullet lists that echo the diff line by line.
- Missing or buried interface/breaking changes.
- Claims not backed by the diff — intent that wasn't implemented, or "added tests" with no test file in the diff (see step 5).
- Sprawling, multi-purpose PR — unrelated changes bundled together. No description makes a grab-bag reviewable; flag it and suggest splitting into single-purpose PRs (a few hundred lines of diff is the usual rule of thumb).

## 4. What a beautiful description looks like

De-slopped is the floor, not the goal. A great description is *crafted* — it respects the reviewer's time and makes the change easy to hold in your head. Form serves the reader and is never the sin; **decoration over empty content** is (adjectives without facts, sections that echo the diff, polish hiding a missing Why). Judge by substance-per-line. Aim for, in priority order:

- **A strong lead.** One or two sentences that state what changed *and* why it matters, before any heading. The reviewer should understand the gist from the first line.
- **Scannable structure.** Short sections and tight bullets beat a wall of prose; prefer real headings (`###`) over bold-line pseudo-headings, which render flat on GitHub. For a behavior-sensitive change, a **"Preserved / behavior change"** callout answers the reviewer's first fear; for interface changes, a small table (symbol → change) reads faster than prose; pull a notable bug-fix onto its own line.
- **Backtick every symbol, file, and path** — `fetch_user`, `auth.py`, `--include-deleted` — so they pop from prose.
- **Confident, plain voice with real numbers.** "Cuts the hot path to one lookup per minute" beats "improves performance"; "12 new tests, all passing" beats "full coverage". An occasional emoji is fine *if the repo's culture uses them*.

**The repo's template wins — always.** If the repo has a PR template (step 1), compose *inside it*: its exact headings, ticket line, and furniture (admonitions, `Human Notes`-style sections, placeholder comments where you have nothing to add). Map the craft into its sections — lead at the top of `Summary`, Why in or right after it, behavior/interface callouts where changes are described, verification in its testing section. A description in the wrong shape reads as alien next to every other PR in the repo, no matter how good the content. The exemplar below is **only** for repos with no template.

**When the Why is genuinely missing**, don't fabricate it and don't dump a bare `TODO`. Mine the branch name and commits first (`git log <base>..HEAD`). If it's still unknown, write a clean, specific prompt to the author — e.g. `**Why:** _(author: what regression/ticket/decision drove this? the diff doesn't say.)_` — so the gap is obvious and easy to fill.

### Exemplar — only for repos with **no** PR template

```markdown
## Cache permission lookups on the auth hot path

Every authenticated request re-queried the permissions table, adding ~40ms p50.
This adds a 60s in-memory cache keyed by (user, resource), so a user's checks hit
the DB at most once a minute instead of once a request.

**Why:** PERF-812 — permission checks were the top span in the auth trace; this
was the cheapest large win.

### How
- `PermissionCache` (TTLCache, 60s) wraps `PermissionStore.check`.
- Invalidated on role change via the existing `role.updated` event — no stale grants.

### Behavior change
- No API change. Permission edits now take up to 60s to propagate (was instant).
  Acceptable per PERF-812; called out for security review.

### Verify
- Load test `/api/*`: p50 40ms → 6ms.
- Change a role, confirm access updates within 60s.
```

Note what makes it good: the lead carries the whole story, the Why is real and cited, the *Behavior change* section surfaces the one thing a reviewer must not miss, and nothing is decorative. In a repo *with* a template, the same content flows into the template's own sections instead — the craft transfers, the headings don't.

## 5. Verify every claim against the diff

Before finalizing, check that the description asserts only what the diff actually does. Asserting changes or tests that aren't there is the most common *and* most damaging agent-PR failure — it tanks reviewer trust, lowers acceptance, and slows merges. For each sentence, ask "is this in the diff?"

- **Test claims are the worst offender.** Never write "added tests for X" unless a test file is actually in the diff — verify with `git diff <base>...HEAD -- '**/*test*' '**/*spec*'`. If none were added, say so plainly: "No automated tests; verified manually by …". Don't invent a test plan.
- **No phantom changes.** Drop any feature, refactor, or fix the diff doesn't contain, however plausible it sounds.
- **No understated scope.** If the diff does *more* than the draft admits — a side effect, a touched public API, a dropped behavior — surface it.
- **Quantify from the diff, not aspiration.** Cite real counts ("3 endpoints", "12 tests") rather than "comprehensive" or "full coverage".

This is the description-side analogue of "never invent the Why": never carry a claim the code doesn't back.

## 6. Output

Lead with a one-line **verdict** (what's missing or weak), then a **ready-to-paste rewrite** crafted to the bar in Section 4 — strong lead, scannable structure, real Why, behavior/interface callouts where relevant, **in the repo template's shape when one exists**. Drop headings that don't apply (in a template, leave its required sections in place with their placeholder comments instead). If the PR is too large or mixed to review well, say so and suggest a split — no description makes a grab-bag reviewable. When asked, update the PR with `gh pr edit <n> --body`.
