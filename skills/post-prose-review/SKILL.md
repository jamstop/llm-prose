---
name: post-prose-review
description: Post a prose review to a GitHub PR as apply-able artifacts — inline suggestions for a few fixes, a stacked fix PR for many — plus one sticky summary comment. Use only when the user explicitly asks to post, leave, or share a prose review on a PR.
disable-model-invocation: true
---

# Post Prose Review

Run the prose review, then deliver it **on the PR** in a form the owner can apply with one click and ignore without cost. This skill writes to GitHub; everything it posts is opt-in for the owner — never merge anything, never push to the PR's own branch, never edit someone else's PR body.

## 1. Review first

Produce the findings exactly as the rubric skills define them:

- Comments: follow `comment-bloat-review` on the PR diff (`gh pr diff <n>`). Keep each fix line-anchored: file, line range, and the replacement text (empty = delete).
- Description: follow `pr-description-review` for the verdict and rewrite.

**Then filter by confidence.** Posting to a PR is louder than reporting to the user, so the bar is higher: an inline suggestion or stacked-PR edit must be a finding you'd defend to the author in person — deslop hits and clear rubric cases qualify. Anything borderline (a tighten you're only mostly sure about, a judgment call the author might reasonably reject) goes as a short take-or-leave note in the sticky comment, or nowhere. This is how the established review bots keep their welcome: post few, high-confidence findings rather than everything you noticed.

If there are no findings, say so to the user and post nothing.

## 2. Choose the delivery

Get the head branch and whether it's a fork: `gh pr view <n> --json headRefName,headRepositoryOwner,isCrossRepository,number,url`.

- **A few comment fixes (≤ 3) → one batched review of inline suggestions.** Native, zero-setup, one-click per fix. Post a single review (not individual comments). Everything goes in one JSON document — `gh api` **silently ignores `-f` flags when `--input` is used**, so `event` must be inside the JSON or the review is created PENDING (invisible to the owner, and it blocks your later reviews):

  ```
  jq -n '{event: "COMMENT",
          body: "prose review — apply any of these with \"Commit suggestion\"",
          comments: [{path: "src/x.py", line: 12, side: "RIGHT",
                      body: "```suggestion\n<replacement>\n```"}]}' \
    | gh api repos/{owner}/{repo}/pulls/<n>/reviews --input -
  ```

  Confirm the response says `"state": "COMMENTED"` — a `"state": "PENDING"` means the review is unsubmitted; submit or delete it (`gh api --method DELETE .../reviews/<id>`). A deletion is an empty suggestion block. A multi-line fix uses `start_line` + `line`. Suggestions can only attach to lines present in the diff — which prose findings always are, since the review scopes to added lines.

- **More than that → a stacked fix PR.** Apply every fix on a branch and let GitHub's diff viewer be the review:

  ```
  gh pr checkout <n>
  git checkout -b prose/pr-<n>
  # apply all comment edits, then:
  git commit -am "prose: comment cleanup for #<n>"
  git push -u origin prose/pr-<n>
  gh pr create --base <headRefName> --title "prose cleanup for #<n>" --body "..."
  ```

  Base is the **PR's head branch**, so merging it lands the fixes on their branch — nothing touches `main`. On a re-run, push to the same `prose/pr-<n>` branch; the existing stacked PR updates in place. The stacked PR's body should state it's optional and safe to close.

- **Fork PR (`isCrossRepository: true`) or no push access → suggestions only**, regardless of count. You can't stack a PR onto a branch you can't reach. If the fix count makes that unwieldy, put the full unified diff in the sticky comment inside `<details>` with a note that `gh pr diff --patch`-style application is manual.

## 3. One sticky comment — the only top-level artifact

Everything else hangs off a single summary comment, **upserted** so re-runs never stack up:

- Find ours: `gh api repos/{owner}/{repo}/issues/<n>/comments --jq '.[] | select(.body | startswith("<!-- prose-review -->")) | .id'`
- Exists → `gh api --method PATCH .../comments/<id> -f body=...`; else → `gh pr comment <n> --body-file ...`

Body shape (lead with the marker line, keep it short — the details fold carries the bulk):

```markdown
<!-- prose-review -->
**prose review** — N comment fixes ([apply via #<stacked>](url) / as suggestions below), description rewrite folded here.

<details><summary>Suggested description</summary>

...ready-to-paste rewrite, in the repo template's shape...

</details>
```

Omit what doesn't apply: no description issues → no fold; suggestions-only → no stacked-PR line. If the *user* owns the PR and asks, apply the description directly with `gh pr edit <n> --body` instead of folding it.

## 4. Hard rails

- One sticky comment per PR, ever — upsert, never post a second.
- Never `push --force`, never write to the PR's head branch, never merge, never close their PR.
- Never edit the body or code of a PR the user doesn't own; the owner applies or declines.
- Precision beats coverage: post only findings the rubrics are confident in. A noisy bot on someone else's PR costs the tool its welcome.
