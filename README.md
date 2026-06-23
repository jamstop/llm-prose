# llm-prose

A plugin that reviews the **prose layer** of LLM-authored changes — the *comments* in your diff and the *PR description* — not the code's correctness. It does the two cleanup passes that are easy to forget and tedious by hand, and ships a rule that keeps the agent from creating the mess in the first place.

Works in **Cursor** and **Claude Code**, on a GitHub PR (via `gh`) or a plain local/branch diff.

## Ethos

LLMs write code well and write *about* code badly. They leave their working memory in comments, over-document the obvious, and ship PR descriptions that list files instead of explaining a change. This plugin encodes two opinions:

**Comments** should be as short as possible while carrying as much relevant information as possible, and exist only where relevant — never as one giant block. Before keeping one, ask: *"What do I actually care about here — is this for a human, or just the LLM's scratchpad?"* Keep intent, *why* over *what*, trade-offs, constraints, gotchas, links to context, and required public-API docs. Cut narration, notes-to-self (`// as requested`, `// updated to handle X`), commented-out code, and doc dumps.

**Descriptions** should answer **What / Why / How** and surface **interface and breaking changes** — the things a reviewer and a future reader actually need. The *Why* is the part LLMs skip and the part that matters most; the tool **never invents it** — if the motivation isn't in the diff, a ticket, or the branch context, it asks or leaves a placeholder rather than fabricating one.

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

Restart/reload each tool once to pick it up. The `review-prose` skill then auto-activates on relevant tasks, and the `/prose*` commands are available explicitly. Updates: set `"autoUpdate": true` on the marketplace in `~/.claude/plugins/known_marketplaces.json` (tracks the remote), or run `claude plugin update llm-prose@llm-prose`.

> Why this and not a Cursor marketplace: Cursor's own marketplace is public-repo + manual review, and Team Marketplaces are Teams/Enterprise + org-scoped. The Claude plugin layer is the practical cross-tool path for a private repo.

### Ad-hoc / dev, without installing

`cursor-agent` can load the plugin straight from a checkout:

```bash
cursor-agent --plugin-dir /path/to/llm-prose \
  -p "use the comment-bloat-review skill to review the comments on this branch"
```

Or copy `skills/`, `commands/`, `rules/` into a project's `.cursor/` (or `.claude/`) dirs — keep skills alongside commands, since commands delegate to skills by name.

## Releasing & updating

Claude Code keys the installed plugin cache by **version** (`.../llm-prose/<version>/`). Pushing commits *without bumping the version does not reach installed users* — `claude plugin update` will report "already latest". So ship changes with a version bump.

Cut a release with the helper (bumps the version in all three manifests, validates that they agree, commits, tags, pushes):

```bash
scripts/release.sh            # patch
scripts/release.sh minor      # or: major / an explicit 1.2.3
```

Then pull it into an install: `claude plugin update llm-prose@llm-prose` (restart to apply), or rely on `autoUpdate` to refresh on the next session. The validator enforces that the version matches across `.cursor-plugin/plugin.json`, `.claude-plugin/plugin.json`, and `.claude-plugin/marketplace.json`.

## Tests

`scripts/validate.sh` (bash + jq, no other deps) checks the structural failure modes that actually break a plugin:

- manifests are valid JSON and agree on the plugin `name`
- every skill/command/rule has the required frontmatter
- each skill's declared `name` matches its directory
- **delegation integrity** — every `` `skill-name` `` a command delegates to exists as a real skill

Run `bash scripts/validate.sh`. CI (`.github/workflows/validate.yml`) runs it on every push and PR, so the remote can't go broken before you pull it.

**Behavioral eval** (`eval/run.sh`) — drives the real `comment-bloat-review` skill through the Cursor CLI against `eval/fixtures/sample.py`, which has comments tagged with sentinels: `CMT_B*` are planted bloat that must be flagged, `CMT_K*` are comments that must be kept. It scores recall (all bloat caught) and precision (no good comments flagged):

```bash
bash eval/run.sh              # one run, default model
RUNS=5 bash eval/run.sh       # repeat to gauge flakiness
MODEL=sonnet-4-thinking bash eval/run.sh
```

This is an LLM eval, so treat it as a smoke test, not a hard gate — it needs CLI auth and network, which is why it's not in CI. Add fixtures as you find comment patterns the skill mishandles.

## Components

- **`skills/review-prose`** — context-aware entry point; auto-activates. Detects git/PR context and runs both passes against the right target.
- **`skills/comment-bloat-review`, `skills/pr-description-review`** — the rubrics. `disable-model-invocation`, so they load only when named (by `review-prose` or a command) and don't fire ambiently.
- **`commands/`** — the three slash commands above.
- **`rules/llm-prose.mdc`** — Cursor-only, globbed to code files, not always-on. Write-time comment discipline.

## Portability

Skills (`SKILL.md`) and slash commands are a shared format, so Cursor and Claude Code both load them; the two manifests (`.cursor-plugin/`, `.claude-plugin/`) coexist in one repo. The `.mdc` rule is the only Cursor-specific piece. Other tools (Cline, Copilot) lack native plugin parity — copy the Markdown into their conventions.

## Status

Manifests and frontmatter are validated (`scripts/validate.sh`, plus Claude's `plugin validate`). The behavioral eval passes, and the `review-prose` skill has been confirmed loading and self-describing in the Cursor CLI via the Claude install. The `disable-model-invocation` rubric skills surface only when named (by `review-prose` or a `/prose*` command), which is intended.

## Layout

```
llm-prose/
├── .cursor-plugin/plugin.json
├── .claude-plugin/{plugin,marketplace}.json
├── commands/{prose,prose-code-comments,prose-pr-description}.md
├── rules/llm-prose.mdc            # Cursor only
└── skills/
    ├── review-prose/SKILL.md
    ├── comment-bloat-review/SKILL.md
    └── pr-description-review/SKILL.md
```
