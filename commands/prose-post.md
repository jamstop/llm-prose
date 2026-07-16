---
name: prose-post
description: Run the prose review on a PR and post the results to GitHub — one-click suggestions plus one sticky summary comment; a stacked fix PR only on explicit request.
---

# Post Prose Review to a PR

Load and follow the `post-prose-review` skill against the PR the user named — a number (`/prose-post 1234`, resolved against the current repo) or a full URL (`/prose-post https://github.com/owner/repo/pull/1234`, works from any directory; pass the URL or `--repo owner/repo` to every `gh` call). With no argument, the current branch's open PR.

Unlike `/prose`, this **writes to GitHub** — it leaves a review the PR owner can apply with one click. Nothing is merged and the PR's own branch is never touched.
