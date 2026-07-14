---
name: prose-post
description: Run the prose review on a PR and post the results to GitHub — one-click suggestions or a stacked fix PR the owner can merge, plus one sticky summary comment.
---

# Post Prose Review to a PR

Load and follow the `post-prose-review` skill against the PR the user named (`/prose-post 1234`; with no argument, the current branch's open PR).

Unlike `/prose`, this **writes to GitHub** — it leaves a review the PR owner can apply with one click. Nothing is merged and the PR's own branch is never touched.
