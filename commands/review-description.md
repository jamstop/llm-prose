---
name: review-description
description: Review and rewrite a PR description so it covers What, Why, How, and interface changes.
---

# Review Description

Load and follow the `pr-description-review` skill, applying it to the target PR.

Target: if the user named a PR number or branch, use it (`gh pr view <n> --json title,body,files` + `gh pr diff <n>`). Otherwise use the current branch's PR, or the local branch diff if no PR exists yet.

Give a verdict on what's weak, then a ready-to-paste rewrite. If the user asks, update the PR with `gh pr edit`.
