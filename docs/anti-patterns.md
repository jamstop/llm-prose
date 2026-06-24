# Anti-pattern gallery

Real examples of the bloat this plugin is built to catch, drawn from what open-source
maintainers and tooling teams actually reported in the wild. Use it to calibrate the
rubrics: if a flagged comment or description doesn't resemble something here, double-check
the call.

Each entry: the **shape**, a **concrete example**, **why it's bloat**, and the **fix**.
Examples marked *(illustrative)* are reconstructed from the cited pattern; quoted lines are
verbatim from the source.

---

## Comments

### Narration — restates the code on the next line
The single most common LLM comment. Well-named identifiers already say this; the comment
only adds reading load and rots first when the code changes.

```javascript
let counter = 0;        // Initialize counter to zero
counter++;              // Increment counter by one
return user.name;       // Return the user's name
```

**Fix:** delete. The names carry it.
Source: GitHub's own [awesome-copilot self-explanatory-code-commenting instructions](https://github.com/github/awesome-copilot/blob/main/instructions/self-explanatory-code-commenting.instructions.md);
[Stop reviewing AI code. Start deleting it.](https://dev.to/krisnamic/stop-reviewing-ai-code-start-deleting-it-o40).

### Doc dump — a doc block longer than the code, restating the signature
> "You write a function called `getUserById` and Copilot immediately wants to add … JSDoc
> comments that are longer than the actual code." — [grizzlypeaksoftware](https://www.grizzlypeaksoftware.com/articles/p/the-annoying-things-copilot-still-inserts-and-how-to-kill-them-permanently-rSK6Ib)

```javascript
/**
 * Gets a user by their ID.
 * @param {string} id - The ID of the user to get.
 * @returns {User} The user with the given ID.
 */
function getUserById(id) { ... }   // (illustrative)
```

**Fix:** for an internal symbol, delete. For a public API, *tighten* — keep a one-line
summary, drop the `@param`/`@returns` the names already cover, keep only what adds
information (errors thrown, invariants, an example).

### Commented-out code — dead code left behind
```javascript
// const oldFunction = () => { ... };
const newFunction = () => { ... };
```
**Fix:** delete. It's in git history.
Source: [awesome-copilot](https://github.com/github/awesome-copilot/blob/main/instructions/self-explanatory-code-commenting.instructions.md).
*(prose-lint catches this deterministically — rule R2.)*

### LLM residue — the model talking to the reviewer
The comment narrates the *edit* or addresses the prompt, not the code.

```python
# This should now correctly handle the null case as requested   (illustrative)
# Updated this per review feedback to also handle the empty list
```
**Fix:** delete. A future reader needs the code's intent, not the chat transcript.
*(prose-lint catches the explicit phrases — rule R1.)*

---

## PR descriptions

The dominant 2026 failure mode maintainers describe is the **"stately description"**: it
looks polished and says nothing.

> "Descriptions are neatly organized into chapters, sometimes including bullet points and
> tables. They even contain emojis. At first glance, they look polite, but they are clearly
> written by AI." — Hono maintainer, [zenn.dev](https://zenn.dev/yusukebe/articles/3fd5bc6ea341c9?locale=en)

> "changes often make no sense, descriptions are extremely verbose, users don't understand
> their own changes." — on Godot AI-slop PRs, [The Register](https://www.theregister.com/software/2026/02/18/godot-maintainers-struggle-with-demoralizing-ai-slop-prs/4206219)

A stately description looks like this *(illustrative, distilled from the pattern)*:

```markdown
## 🚀 Summary
This PR introduces a series of improvements to enhance the robustness and
maintainability of the authentication module. 🎉

## ✨ Changes
- Updated `auth.py` to improve the login flow
- Modified `session.py` for better handling
- Refactored helper functions for clarity
- Various other improvements and cleanups

This change ensures a more seamless and reliable experience for all users.
```

**Why it's bloat:** every line either echoes the diff (the file list) or is content-free
filler ("improvements," "robustness," "seamless experience"). There is **no Why** — no
problem, ticket, or decision — and the reader is no closer to understanding the change.

### Specific tells to flag

- **Filler openers:** "This PR introduces…", "In this pull request…", "This PR makes
  several improvements…". ([deployhq](https://www.deployhq.com/git/writing-pull-request-descriptions-with-ai))
- **Diff echo:** a bullet per changed file that restates the filename.
- **Inflated importance:** marketing adjectives on a minor change. ([deployhq](https://www.deployhq.com/git/writing-pull-request-descriptions-with-ai))
- **Missing / fabricated Why:** the motivation is absent, or invented to sound plausible.
- **Ignores issue context:** describes the change without reference to the issue it claims
  to fix — common in mass-generated PRs. ([zenn.dev](https://zenn.dev/yusukebe/articles/3fd5bc6ea341c9?locale=en))
- **Multi-purpose grab-bag:** unrelated changes bundled so no description can make it
  reviewable.

**Fix:** lead with one or two plain sentences of *what* changed and *why* (the real
motivation — never invented). Add *how* only for non-obvious choices. Surface interface or
breaking changes. Drop the file list; the diff already has it. If it's a grab-bag, split
the PR rather than polish the prose.

The problem is real enough that CI actions now scan for it — e.g.
[`peakoss/anti-slop`](https://github.com/peakoss/anti-slop), adopted in
[langgenius/dify#33193](https://github.com/langgenius/dify/pull/33193).

---

## Fixtures built from these

- `eval/fixtures/sample.py` — comment slop (narration, residue, doc dumps) with sentinel
  tokens, scored by `eval/run.sh`.
- `eval/fixtures/pr_description_stately.md` / `pr_description_good.md` — a "stately" slop
  description and its tightened counterpart, for dogfooding the description pass.
