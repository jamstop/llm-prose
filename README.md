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
| `/review-prose` | wrapping up a branch or reviewing a PR | both passes, figures out the target itself |
| `/review-pr-comments` | you only care about comments | flags comment bloat, proposes fixes |
| `/review-pr-description` | you only care about the write-up | verdict + ready-to-paste rewrite |

Targeting is automatic: with no argument it reviews the current branch (or its open PR); name a PR and it reviews that, e.g. `/review-prose 1242`. Ask it to apply the changes and it edits the comments and updates the PR body directly.

**Or just ask** — the `review-prose` skill auto-activates when the model sees a relevant task, so "review the prose on this branch before I open a PR" or "are these comments bloated?" triggers it without a command.

**Prevention** — in Cursor, the `llm-prose.mdc` rule applies while you edit code files and nudges the agent to write lean comments up front. (Claude Code carries that discipline inside the skill instead.)

## Install

### Cursor — local (private repo, any plan)

Team Marketplaces are Teams/Enterprise only, so for a private personal repo install locally — your machine's git handles the private clone:

```bash
git clone git@github.com:jamstop/llm-prose.git ~/.cursor/plugins/local/llm-prose
# update later: cd ~/.cursor/plugins/local/llm-prose && git pull
```

Restart Cursor.

### Cursor — team marketplace (Teams/Enterprise)

Dashboard → Settings → Plugins → Team Marketplaces → Import from Repo. Requires the repo under a Teams/Enterprise org with the Cursor GitHub App installed.

### Claude Code

```
/plugin marketplace add jamstop/llm-prose
/plugin install llm-prose@llm-prose
```

### Any project, any tool

Copy `skills/` and `commands/` into the tool's directories (`.cursor/`, `.claude/`, …). Copy the skills alongside the commands — the commands delegate to skills by name.

## Components

- **`skills/review-prose`** — context-aware entry point; auto-activates. Detects git/PR context and runs both passes against the right target.
- **`skills/comment-bloat-review`, `skills/pr-description-review`** — the rubrics. `disable-model-invocation`, so they load only when named (by `review-prose` or a command) and don't fire ambiently.
- **`commands/`** — the three slash commands above.
- **`rules/llm-prose.mdc`** — Cursor-only, globbed to code files, not always-on. Write-time comment discipline.

## Portability

Skills (`SKILL.md`) and slash commands are a shared format, so Cursor and Claude Code both load them; the two manifests (`.cursor-plugin/`, `.claude-plugin/`) coexist in one repo. The `.mdc` rule is the only Cursor-specific piece. Other tools (Cline, Copilot) lack native plugin parity — copy the Markdown into their conventions.

## Status

Manifests and frontmatter are validated. Skill auto-activation and command→skill loading use the standard model-invoked Skills mechanism but haven't been smoke-tested live — run `/review-pr-comments` on a real diff once after install to confirm.

## Layout

```
llm-prose/
├── .cursor-plugin/plugin.json
├── .claude-plugin/{plugin,marketplace}.json
├── commands/{review-prose,review-pr-comments,review-pr-description}.md
├── rules/llm-prose.mdc            # Cursor only
└── skills/
    ├── review-prose/SKILL.md
    ├── comment-bloat-review/SKILL.md
    └── pr-description-review/SKILL.md
```
