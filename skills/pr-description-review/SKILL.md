---
name: pr-description-review
description: Review or rewrite a pull request description so it covers What, Why, and How, and surfaces important code/interface changes. Use when reviewing a PR, writing or improving a PR description or summary, or when the user asks to check or fix a PR write-up.
disable-model-invocation: true
---

# PR Description Review

Judge a PR description against its actual diff, then **compose** one that is genuinely good to read — not just stripped of slop. Two distinct jobs: a short *verdict* (what's weak) and a *crafted rewrite* (what a reviewer would be glad to open). Spend real effort on the rewrite; that's the deliverable.

Two hard constraints up front, because they're the ones most often broken: **a reviewer must absorb the description in about a minute** — a bullet is one line, and accuracy does not excuse length; and **if you wrote the draft in this session, a fresh subagent judges it, not you** (section 7).

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

De-slopped is the floor, not the goal. A great description is *crafted* — it respects the reviewer's time and makes the change easy to hold in your head. Form serves the reader and is never the sin; **decoration over empty content** is (adjectives without facts, sections that echo the diff, polish hiding a missing Why). Judge by substance-per-line — and by the reader's clock:

**The one-minute budget.** A description a reviewer can't absorb in about a minute is failing *whatever its accuracy* — dense, true, em-dash-chained prose is the same disease as design-doc comments, and "every clause is informative" is how it defends itself. Concretely: a **bullet is one line** (a second line means it's two bullets or too much detail); the whole body stays around **200-300 words** for a typical PR; design rationale beyond that lives in the code review conversation, a doc, or the commit messages — link, don't inline. When drafting a bullet, write the long version if you must, then keep only the clause a reviewer needs to *route their attention* — they read the description to decide where to look, not to skip reading the diff.

Aim for, in priority order:

- **A strong lead.** One or two sentences that state what changed *and* why it matters, before any heading. The reviewer should understand the gist from the first line.
- **Scannable structure.** Short sections and tight bullets beat a wall of prose; prefer real headings (`###`) over bold-line pseudo-headings, which render flat on GitHub. For a behavior-sensitive change, a **"Preserved / behavior change"** callout answers the reviewer's first fear; for interface changes, a small table (symbol → change) reads faster than prose; pull a notable bug-fix onto its own line.
- **Backtick every symbol, file, and path** — `fetch_user`, `auth.py`, `--include-deleted` — so they pop from prose.
- **Confident, plain voice with real numbers.** "Cuts the hot path to one lookup per minute" beats "improves performance"; "12 new tests, all passing" beats "full coverage". Active voice, present tense. Drop the politeness and difficulty adjectives — `please`, `simply`, `easily`, `just`, "note that" — they add words and, when the step *isn't* easy, condescension (Google's style guide bans them for the same reason). An occasional emoji is fine *if the repo's culture uses them*.

**The repo's template wins — always.** If the repo has a PR template (step 1), compose *inside it*: its exact headings, ticket line, and furniture (admonitions, `Human Notes`-style sections, placeholder comments where you have nothing to add). Map the craft into its sections — lead at the top of `Summary`, Why in or right after it, behavior/interface callouts where changes are described, verification in its testing section. A description in the wrong shape reads as alien next to every other PR in the repo, no matter how good the content. The exemplar below is **only** for repos with no template.

Template conformance is checkable — verify all four: (1) the ticket/`Resolves:` line survives, filled or with its placeholder; (2) every required template heading is present, **with its exact name** — don't rename `### Changes` to "What's in it"; (3) **no invented sections** — extra material folds into the nearest template section (a "known trade-off" is a line in `Summary` or `Changes`, not a new heading); (4) template furniture (comments, admonitions) is preserved where you have nothing to add.

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

## 7. Final checks — verify each before delivering

1. **Length:** readable in about a minute; every bullet is one line; ~200-300 words for a typical PR. If over, cut detail, not sections.
2. **Template:** ticket line present; every required heading present with its exact name; no invented sections; furniture preserved.
3. **Why:** real and cited, or an explicit author-prompt — never invented.
4. **Claims:** every sentence is backed by the diff (section 5); test claims verified against actual test files.
5. **Interface/behavior:** anything a consumer must notice is surfaced, not buried.
6. **Authorship:** if you wrote this draft (or the PR) in the current session, delegate the judgment — launch a fresh subagent with only this skill and the diff, no conversation history, and apply its verdict. Your context contains the rationale that justified every excess word; a clean reader is the only honest judge. If subagents aren't available, finish with one explicit audit pass: reread the rewrite asking *"what would a skeptical human reviewer still call AI-written or oversized?"* — and fix what you name before delivering.
