---
name: pr-description-review
description: Review or rewrite a pull request description so it covers What, Why, and How, and surfaces important code/interface changes. Use when reviewing a PR, writing or improving a PR description or summary, or when the user asks to check or fix a PR write-up.
disable-model-invocation: true
---

# PR Description Review

Judge a PR description against its actual diff, then **compose** one that is genuinely good to read — not just stripped of slop. Two distinct jobs: a short *verdict* (what's weak) and a *crafted rewrite* (what a reviewer would be glad to open). Spend real effort on the rewrite; that's the deliverable.

Two hard constraints up front, because they're the ones most often broken: **the description must answer What, Why, and How and surface interface/behavior changes (section 2) — no length target ever justifies cutting that content**; and **if you wrote the draft in this session, a fresh subagent judges it, not you** (section 7).

## 1. Gather

- Description + metadata: `gh pr view <n> --json title,body,files` (or `gh pr view` on current branch).
- Actual changes: `gh pr diff <n>` (or `git diff <base>...HEAD` locally). The description must match the diff — don't trust it blindly.
- **The repo's PR template** — check `.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE.md`, and `.github/PULL_REQUEST_TEMPLATE/`. Note required headings and fields, then skim 2-3 recently merged PRs (`gh pr list --state merged`) to see which optional scaffolding teams actually keep.
- **The comment pass's harvest**, when running as part of `/prose`: rationale the `comment-bloat-review` pass moved out of oversized comments with destination "PR description" is first-class input here — it's diff-backed Why/How written by the author, not invention. Weave it into the relevant section; don't paste it verbatim if it needs the same tightening as any other prose.

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

The reviewer reads the description to decide where to look, so every paragraph or bullet should route attention or state something a consumer must know. Length follows the change: a migration or breaking API can need substantial context, while a mechanical refactor may need little. When a description feels long, diagnose what the space is spent on. Delete diff echo and narration; link durable design rationale when a separate document is the better home; relocate instructions aimed at another audience. Never cut What/Why/How or interface and behavior callouts merely to hit a number.

Aim for, in priority order:

- **A strong lead.** One or two sentences that state what changed *and* why it matters, before any heading. The reviewer should understand the gist from the first line.
- **Scannable structure.** Short sections and tight bullets beat a wall of prose; prefer real headings (`###`) over bold-line pseudo-headings, which render flat on GitHub. For a behavior-sensitive change, a **"Preserved / behavior change"** callout answers the reviewer's first fear; for interface changes, a small table (symbol → change) reads faster than prose; pull a notable bug-fix onto its own line.
- **Use code formatting when it improves parsing** — especially for symbols, flags, and ambiguous paths. Do not mechanically backtick every technical noun or repeatedly formatted name.
- **Confident, plain voice with real numbers.** "Cuts the hot path to one lookup per minute" beats "improves performance"; "12 new tests, all passing" beats "full coverage". Active voice, present tense. Drop the politeness and difficulty adjectives — `please`, `simply`, `easily`, `just`, "note that" — they add words and, when the step *isn't* easy, condescension (Google's style guide bans them for the same reason). An occasional emoji is fine *if the repo's culture uses them*.

Follow required template structure and fields, while removing authoring instructions and empty optional scaffolding from the finished description. Map the useful content into the template's sections. If repository practice consistently treats a section as optional, omit it when it adds nothing; do not preserve placeholders merely because they exist in the source template. The exemplar below is only for repos with no template.

Template conformance is checkable: preserve required ticket fields and headings with their expected names; fill required fields honestly or mark them not applicable when the repository accepts that; remove authoring comments and empty optional sections. Add a section only when it materially improves review and repository practice permits it.

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

Lead with a one-line **verdict** stated in content terms — which of What/Why/How is missing or weak, what interface/behavior change is buried, which claim the diff doesn't back. Mention length only by naming what the words are spent on (diff echo, inlined design rationale, wrong-audience content), never as a bare word count. Then provide a **ready-to-paste rewrite** with a strong lead, scannable structure, real Why, and relevant behavior/interface callouts in the repository's required shape. Remove authoring placeholders and empty optional sections. If the PR is too large or mixed to review well, say so and suggest a split. When asked, update the PR with `gh pr edit <n> --body`.

## 7. Final checks — verify each before delivering

1. **Content:** What, Why, and How are each answered; the Why is real and cited, or an explicit author-prompt — never invented.
2. **Interface/behavior:** anything a consumer must notice is surfaced, not buried — and nothing in it was cut to make a length number.
3. **Claims:** every sentence is backed by the diff (section 5); test claims verified against actual test files.
4. **Template:** required fields and headings remain; authoring comments and empty optional scaffolding do not.
5. **Length:** proportionate to the change. Any excess was identified by purpose (echo, misplaced rationale, wrong-audience content), not by a fixed word or line count.
6. **Authorship:** if you wrote this draft (or the PR) in the current session — or you're re-judging it after pushback — delegate the judgment — launch a fresh subagent with only this skill and the diff, no conversation history, and apply its verdict. Your context contains the rationale that justified every excess word; a clean reader is the only honest judge. If subagents aren't available, finish with one explicit audit pass: reread the rewrite asking *"what would a skeptical human reviewer still call AI-written or oversized?"* — and fix what you name before delivering.
