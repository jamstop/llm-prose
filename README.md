# llm-prose

A plugin that reviews the **prose layer** of LLM-authored changes — the *comments* in your diff and the *PR description* — not the code's correctness. It does the two cleanup passes that are easy to forget and tedious by hand, and ships a rule that keeps the agent from creating the mess in the first place.

Works in **Cursor** and **Claude Code**, on a GitHub PR (via `gh`) or a plain local/branch diff.

## Ethos

LLMs write code well and write *about* code badly. They leave their working memory in comments, over-document the obvious, and ship PR descriptions that list files instead of explaining a change. This plugin encodes two opinions:

**Comments** should be as short as possible while carrying as much relevant information as possible, and exist only where relevant — never as one giant block. Before keeping one, ask: *"What do I actually care about here — is this for a human, or just the LLM's scratchpad?"* Keep intent, *why* over *what*, trade-offs, constraints, gotchas, links to context, and required public-API docs. Cut narration, notes-to-self (`// as requested`, `// updated to handle X`), commented-out code, and doc dumps.

**Descriptions** should be *composed*, not just de-slopped: a strong lead, a real **Why**, the **How** that isn't obvious from the diff, and any **interface or behavior change** a consumer must notice — in the repo's own template shape when one exists. Two hard lines: the tool **never invents the Why** (if the motivation isn't in the diff, a ticket, or the branch context, it asks or leaves a placeholder), and **never carries a claim the diff doesn't back** (no phantom tests, no overstated scope).

Review is the backstop; the bundled rule does prevention. The plugin holds itself to the same bar — its own files are kept lean.

## Usage

**Slash commands** (run them explicitly):

| Command | When | What it does |
| --- | --- | --- |
| `/prose` | wrapping up a branch or reviewing a PR | both passes, figures out the target itself |
| `/prose-code-comments` | you only care about comments | flags comment bloat, proposes fixes |
| `/prose-pr-description` | you only care about the write-up | verdict + ready-to-paste rewrite |

Targeting is automatic: with no argument it reviews the current branch (or its open PR); name a PR and it reviews that, e.g. `/prose 1242`. Ask it to apply the changes and it edits the comments and updates the PR body directly.

**Or just ask** — the `review-prose` skill auto-activates when the model sees a relevant task, so "review the prose on this branch before I open a PR" or "are these comments bloated?" triggers it without a command.

**Prevention** — in Cursor, the `llm-prose.mdc` rule applies while you edit code files and nudges the agent to write lean comments up front. (Claude Code carries that discipline inside the skill instead.)

## Install

Install it **once through Claude Code's marketplace.** Cursor (both the IDE and the `cursor-agent` CLI) reads `~/.claude/plugins`, so a single Claude install makes the plugin available in **Claude Code, Cursor IDE, and Cursor CLI** — no per-tool setup, no `--plugin-dir`.

```bash
claude plugin marketplace add jamstop/llm-prose   # private repo OK (uses your git auth)
claude plugin install llm-prose@llm-prose
```

Restart/reload each tool once to pick it up.

**Updating — it's tool-specific.** `"autoUpdate": true` (in `~/.claude/plugins/known_marketplaces.json`) is honored **only by Claude Code**, on launch. **Cursor does not auto-update** — it loads whatever version is pinned in `~/.claude/plugins/installed_plugins.json` and never checks the remote itself. So:

- **Claude Code:** with `autoUpdate` on, a new session pulls the latest. Or force it: `claude plugin update llm-prose@llm-prose`.
- **Cursor (IDE or CLI):** run `claude plugin update llm-prose@llm-prose` explicitly, **then restart Cursor**. (Want hands-off? Run that command from a login hook or alias — Cursor won't do it for you.)

> Why this and not a Cursor marketplace: Cursor's own marketplace is public-repo + manual review, and Team Marketplaces are Teams/Enterprise + org-scoped. The Claude plugin layer is the practical cross-tool path for a private repo.

### Ad-hoc / dev, without installing

`cursor-agent` can load the plugin straight from a checkout:

```bash
cursor-agent --plugin-dir /path/to/llm-prose \
  -p "use the comment-bloat-review skill to review the comments on this branch"
```

Or copy `skills/`, `commands/`, `rules/` into a project's `.cursor/` (or `.claude/`) dirs — keep skills alongside commands, since commands delegate to skills by name.

## Contributing & releasing

Changes land via PRs, and the version bumps itself on merge. Claude Code keys the installed plugin cache by **version** (`.../llm-prose/<version>/`), so an un-bumped change never reaches installed users — `claude plugin update` reports "already latest".

1. Branch, then commit with a [conventional](https://www.conventionalcommits.org/) prefix — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `perf:`, `ci:`, `build:`, `style:` (use `feat!:` for breaking). An unrecognized prefix means **no bump and no release** — the merge lands on `main` but never reaches installed users.
2. Open a PR with a conventional **title** (it's the bump signal). Dogfood it: run `/prose` (or `/prose-code-comments`) on the diff.
3. On merge to `main`, `.github/workflows/version-bump.yml` reads the title, bumps all three manifests (`major` for `feat!`, `minor` for `feat`, `patch` for the rest), commits `chore: bump … [skip ci]`, and tags `llm-prose--vX.Y.Z`. Then update per the Install section above.

Out-of-band releases (no PR): run the **auto version bump** workflow manually (Actions → Run workflow) to cut a release off `main` without a code change, or `scripts/release.sh [patch|minor|major|X.Y.Z]` from a clone (its `release:` subject isn't a conventional prefix, so the CI bumper skips it — no double bump).

## Tests

`scripts/validate.sh` (bash + jq, no other deps) checks the structural failure modes that actually break a plugin: valid manifests that agree on the plugin `name`, required frontmatter on every skill/command/rule, skill names matching their directories, and **delegation integrity** (every skill a command delegates to exists). CI runs it on every push and PR.

**Behavioral evals** — LLM smoke tests (they need CLI auth and network, so they're not CI gates):

- `eval/run.sh` drives the real `comment-bloat-review` skill against a sentinel-tagged fixture: `CMT_B*` planted bloat must be flagged for deletion, `CMT_T*` warranted docs must be *tightened* (not deleted), `CMT_K*` keepers must survive. Scores recall, action, and precision. The planted slop is modeled on the real in-the-wild patterns catalogued in [`docs/anti-patterns.md`](docs/anti-patterns.md).
- `eval/run_description.sh` drives `pr-description-review` to rewrite weak drafts against real diffs across five scenarios — **session** (use the available Why, surface the behavior change), **thin-why** (never fabricate a missing Why), **iface** (surface a signature change), **claims** (drop claims the diff doesn't back), **template** (compose inside the repo's PR template, not the skill's own shape). Scoring is on qualities, not exact strings.

```bash
bash eval/run.sh && bash eval/run_description.sh   # RUNS=n to repeat, MODEL=… to pin
```

Add fixtures as you find patterns the skills mishandle.

**Deterministic pre-pass** (`deslop`) — see Components for what it is. Run it and its pytest suite:

```bash
git diff | scripts/deslop --diff
pip install pytest && python -m pytest skills/comment-bloat-review/scripts/tests -q
```

## Components

- **`skills/review-prose`** — context-aware entry point; auto-activates. Detects git/PR context and runs both passes against the right target.
- **`skills/comment-bloat-review`, `skills/pr-description-review`** — the rubrics. `disable-model-invocation`, so they load only when named (by `review-prose` or a command) and don't fire ambiently.
- **`commands/`** — the three slash commands above.
- **`rules/llm-prose.mdc`** — Cursor-only, globbed to code files, not always-on. Write-time comment discipline.
- **`skills/comment-bloat-review/scripts/deslop.py`** — a stdlib-only, language-agnostic deterministic pre-pass bundled *inside* the skill, covering only the two mechanical cases: notes-to-self / LLM residue and commented-out code. Bundled because Cursor exposes no plugin-root path or install hook — a script in the skill's own `scripts/` dir is the one mechanism that reliably runs from any repo, with no model and no install. Anything debatable is left to the skill's judgment. Rules and rationale: [RULES.md](skills/comment-bloat-review/scripts/RULES.md). (On Python-only repos, `eradicate` and `pydoclint`/`docsig` are mature deeper checks; deslop's niche is language-agnostic and always-on.)

## Portability

Skills (`SKILL.md`) and slash commands are a shared format, so Cursor and Claude Code both load them; the two manifests (`.cursor-plugin/`, `.claude-plugin/`) coexist in one repo. The `.mdc` rule is the only Cursor-specific piece. Other tools (Cline, Copilot) lack native plugin parity — copy the Markdown into their conventions.

## Further reading

See [`docs/anti-patterns.md`](docs/anti-patterns.md) for a gallery of real, sourced examples of the bloat this plugin catches — narration, doc dumps, dead code, and the "stately" AI-slop PR description — with the fixes.

The rubrics distill a few canonical sources — read these for the long form:

- **Comments** — [Go Doc Comments](https://go.dev/doc/comment) (the "improve the code so the comment isn't needed" ethos), [TigerBeetle TIGER_STYLE](https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/TIGER_STYLE.md) (comments explain *why*), [Swift API Design Guidelines](https://www.swift.org/documentation/api-design-guidelines/) + [Rust RFC 505](https://rust-lang.github.io/rfcs/0505-api-comment-conventions.html) (summary-first doc comments, structured sections), and GitHub's own [awesome-copilot self-explanatory-code-commenting instructions](https://github.com/github/awesome-copilot/blob/main/instructions/self-explanatory-code-commenting.instructions.md) (a catalog of the exact comment types to avoid).
- **PR descriptions** — [GitHub: how to write the perfect pull request](https://github.blog/developer-skills/github/how-to-write-the-perfect-pull-request/), [opensource.com: anatomy of a perfect PR](https://opensource.com/article/18/6/anatomy-perfect-pull-request) (small, single-purpose PRs), and [Chris Beams: how to write a git commit message](https://cbea.ms/git-commit/).

## Layout

```
llm-prose/
├── .cursor-plugin/plugin.json
├── .claude-plugin/{plugin,marketplace}.json
├── commands/{prose,prose-code-comments,prose-pr-description}.md
├── rules/llm-prose.mdc            # Cursor only
├── docs/anti-patterns.md          # sourced gallery of real bloat + fixes
├── eval/                          # behavioral evals + fixtures (comments & descriptions)
├── scripts/deslop                 # repo-root shim -> the bundled script
└── skills/
    ├── review-prose/SKILL.md
    ├── pr-description-review/SKILL.md
    └── comment-bloat-review/
        ├── SKILL.md
        └── scripts/               # deslop + RULES.md + pytest suite
```
