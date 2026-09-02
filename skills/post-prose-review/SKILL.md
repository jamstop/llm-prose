---
name: post-prose-review
description: Post a prose review to a GitHub PR as apply-able artifacts — one batched review of inline suggestions plus one sticky summary comment; a stacked fix PR only on explicit request. Use only when the user explicitly asks to post, leave, or share a prose review on a PR.
disable-model-invocation: true
---

# Post Prose Review

Run the prose review, then deliver it **on the PR** in a form the owner can apply with one click and ignore without cost. This skill writes to GitHub; everything it posts is opt-in for the owner — never merge anything, never push to the PR's own branch, never edit someone else's PR body.

The PR may be named by number or URL; a URL works from any directory — pass it (or `--repo owner/repo`) to every `gh` call.

## 1. Review first

Produce the findings exactly as the rubric skills define them:

- Comments: follow `comment-bloat-review` on the PR diff (`gh pr diff <n>`). Keep each fix line-anchored: file, line range, and the replacement text (empty = delete).
- Description: follow `pr-description-review` for the verdict and rewrite.

The `deslop` pre-pass reads files from disk, so it needs the PR branch checked out. When the PR isn't from the repo you're in (or you're in no repo at all), don't touch any existing checkout — use a throwaway worktree and clean it up:

```
git -C <local-clone> fetch origin <headRefName>
git -C <local-clone> worktree add -f /tmp/prose-<n> origin/<headRefName>
# run deslop from /tmp/prose-<n>, then:
git -C <local-clone> worktree remove -f /tmp/prose-<n>
```

With no local clone available, skip deslop (the rubric says how) and review on the diff alone.

**Posted findings come from a fresh subagent, always** — not just when you authored the diff. Posting is the loud path, and a long session accumulates bias: prior verdicts, user reactions, rationale you've already committed to. Launch a subagent with no conversation history; its prompt carries the two rubric skill paths, the diff, the deslop output, and — for the description pass — the PR body, the repo template, and a merged-PR sample for house style. Have it tag each finding **high-confidence** or **borderline** (the bar below); you verify anchors and mechanics and post its calls. If subagents aren't available, run the rubrics' own mechanical protocols (one-line drafts, final checks) yourself and tell the *user* which ones ran — the self-audit never goes on the PR.

**Then split by confidence.** Posting to a PR is louder than reporting to the user, so the bar is higher: an inline suggestion or stacked-PR edit must be a finding you'd defend to the author in person — deslop hits and clear rubric cases qualify. Post the high-confidence findings; anything borderline (a tighten that's only mostly sure, a judgment call the author might reasonably reject) goes as a short take-or-leave note in the sticky comment, or nowhere. This is how the established review bots keep their welcome: post few, high-confidence findings rather than everything you noticed.

If there are no findings, say so to the user and post nothing.

## 2. Validate and deliver one batched review

This is the default delivery for comment fixes, whatever their count. Native, zero-setup, one-click per fix, and — unlike a new PR — it creates no extra noise in PR feeds and notification channels. Get the repo/head metadata first: `gh pr view <n> --json headRefName,headRepositoryOwner,isCrossRepository,number,url`.

Do not build suggestion fences directly from model output. Save the fresh review's comment findings as JSON under `comment_findings`, with each finding containing `path`, `start_line`, `end_line`, `action`, `replacement`, `rationale`, and `confidence`. Then run the bundled zero-dependency renderer against the exact diff and checked-out PR head:

```bash
reviewed_head="$(gh pr view <n> --json headRefOid -q .headRefOid)"
test "$(git -C <checked-out-pr-head> rev-parse HEAD)" = "$reviewed_head"
python3 scripts/render.py \
  --result /tmp/prose-findings.json \
  --diff /tmp/prose.diff \
  --source-root <checked-out-pr-head> \
  --commit-id "$reviewed_head" \
  --output /tmp/prose-review.json
test "$(gh pr view <n> --json headRefOid -q .headRefOid)" = "$reviewed_head"
gh api repos/{owner}/{repo}/pulls/<n>/reviews --input /tmp/prose-review.json
```

`scripts/render.py` is relative to this skill directory. It pins the review to the
full head SHA and is the apply-able-edit trust boundary: only high-confidence
edits whose entire range is added, matches the checked-out source, contains
comment text and no executable text, excludes block delimiters and directives,
and has a comment-only replacement become suggestion blocks. A Python docstring
also qualifies when the AST proves the range is exactly one docstring and the
replacement changes nothing but its text. Inline comments, mixed code/comment
ranges, file types outside the known comment grammars (Markdown, JSON, YAML,
Groovy, and anything else unlisted), directives, unsafe block ranges, lines with
non-`\n` line breaks, and unsafe replacements become ordinary review notes with
no replacement text. Malformed or out-of-diff findings are dropped
individually; one bad finding never aborts the rest. Read its stderr diagnostics
before posting.

Post the generated document as one review, not individual comments. Everything
is already inside the JSON document — `gh api` **silently ignores `-f` flags
when `--input` is used**. Confirm the response says `"state": "COMMENTED"`; a
`"state": "PENDING"` means the review is unsubmitted, so submit or delete it
(`gh api --method DELETE .../reviews/<id>`). If either head comparison fails,
stop and regenerate the checkout, diff, findings, and renderer output.

**Stacked fix PR — only on explicit request.** If the user asks for a stacked PR (e.g. "post as a stacked PR"), apply every fix on a branch and let GitHub's diff viewer be the review:

```
gh pr checkout <n>
git checkout -b prose/pr-<n>
# apply all comment edits, then:
git commit -am "prose: comment cleanup for #<n>"
git push -u origin prose/pr-<n>
gh pr create --base <headRefName> --title "prose cleanup for #<n>" --body "..."
```

Base is the **PR's head branch**, so merging it lands the fixes on their branch — nothing touches `main`. On a re-run, push to the same `prose/pr-<n>` branch; the existing stacked PR updates in place. The stacked PR's body should state it's optional and safe to close. Not available on fork PRs (`isCrossRepository: true`) or without push access — fall back to suggestions and tell the user why.

## 3. One sticky comment — the only top-level artifact

Everything else hangs off a single summary comment, **upserted** so re-runs never stack up:

- Find ours: `gh api repos/{owner}/{repo}/issues/<n>/comments --jq '.[] | select(.body | startswith("<!-- prose-review -->")) | .id'`
- Exists → `gh api --method PATCH .../comments/<id> -f body=...`; else → `gh pr comment <n> --body-file ...`

Body shape (lead with the marker line, keep it short — the details fold carries the bulk):

```markdown
<!-- prose-review -->
**prose review** — N comment fixes as suggestions below, description rewrite folded here.

<details><summary>Suggested description</summary>

...ready-to-paste rewrite, in the repo template's shape...

</details>
```

Omit what doesn't apply: no description issues → no fold; stacked PR requested → `[apply via #<n>](url)` replaces "as suggestions below". If the *user* owns the PR and asks, apply the description directly with `gh pr edit <n> --body` instead of folding it.

## 4. Hard rails

- One sticky comment per PR, ever — upsert, never post a second.
- Never `push --force`, never write to the PR's head branch, never merge, never close their PR.
- Never edit the body or code of a PR the user doesn't own; the owner applies or declines.
- Precision beats coverage: post only findings the rubrics are confident in. A noisy bot on someone else's PR costs the tool its welcome.
