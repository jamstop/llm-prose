---
name: pr-description-review
description: Review or rewrite a pull request description so it covers What, Why, and How, and surfaces important code/interface changes. Use when reviewing a PR, writing or improving a PR description or summary, or when the user asks to check or fix a PR write-up.
disable-model-invocation: true
---

# PR Description Review

Judge a PR description against its actual diff and rewrite it to be useful to a reviewer.

## 1. Gather

- Description + metadata: `gh pr view <n> --json title,body,files` (or `gh pr view` on current branch).
- Actual changes: `gh pr diff <n>` (or `git diff <base>...HEAD` locally). The description must match the diff — don't trust it blindly.

## 2. Required content

A good description answers, in order:

- **What** — what changed, in one or two plain sentences. Not a file list; the diff already lists files.
- **Why** — the motivation: problem, ticket/bug, user impact, or decision being implemented. This is the part LLMs most often omit. **Never invent it.** If the motivation isn't in the diff, a linked ticket, or the branch/commit context, ask the user or leave a `<!-- why: TODO -->` placeholder rather than fabricate one.
- **How** — the approach and any non-obvious design choices or trade-offs. Skip step-by-step narration of the diff.
- **Interface changes** — surface anything a consumer must notice: new/changed/removed public APIs, function signatures, props, endpoints, schema/migrations, config or env vars, breaking changes, feature flags. Call out breaking changes explicitly.

Include when relevant, don't manufacture: test plan / how to verify, screenshots for UI, rollout/migration notes, follow-ups or known gaps.

## 3. Flag these failure modes

- Title or body that just restates the branch name or the commit subject.
- Pure file/change enumeration with no Why.
- LLM filler: "This PR makes several improvements...", marketing adjectives, bullet lists that echo the diff line by line.
- Missing or buried interface/breaking changes.
- Claims not backed by the diff (describes intent that wasn't implemented).
- Sprawling, multi-purpose PR — unrelated changes bundled together. No description makes a grab-bag reviewable; flag it and suggest splitting into single-purpose PRs (a few hundred lines of diff is the usual rule of thumb).

## 4. Output

Give a short verdict on what's missing or weak, then a ready-to-paste rewritten description using the headings above (drop headings that don't apply). Match the repo's PR template if one exists (`.github/PULL_REQUEST_TEMPLATE*`). If the PR is too large or mixed to review well, say so and suggest a split — a tighter description won't fix scope. Keep it tight — a reviewer should grasp the change in seconds. When asked, update the PR with `gh pr edit <n> --body`.
