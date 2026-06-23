# llm-prose

A Cursor plugin for reviewing the **prose layer** of LLM-authored changes — the comments and the PR description — not the code's correctness. It does the two cleanup passes that are easy to forget and tedious by hand:

1. **Comment bloat** — flags redundant narration, LLM-residue comments (the model's notes-to-self), over-documentation, stale/commented-out code, and proposes tighter edits. Keeps only comments that explain intent a human needs.
2. **Description quality** — checks a PR description against the real diff and rewrites it to cover **What / Why / How** and surface **interface/breaking changes**.

It also ships a write-time **rule** that nudges the agent to avoid this bloat in the first place, so review is a backstop rather than the only defense.

Works on a GitHub PR (via `gh`) or a local/branch diff.

## Components

**Skill** (auto-activates when the model judges the task relevant, e.g. finishing a change or reviewing a PR):

- `review-prose` — context-aware entry point. Detects whether you're in a git repo and on a working branch / have an open PR, then runs both passes against the right target.
- `comment-bloat-review`, `pr-description-review` — the underlying rubrics it (and the commands) apply.

**Commands** (explicit, deterministic):

| Command | Does |
| --- | --- |
| `/review-prose` | Both passes, context-aware (delegates to the `review-prose` skill) |
| `/review-pr-comments` | Comment-bloat pass only |
| `/review-pr-description` | Description review + rewrite only |

**Rule:**

- `rules/llm-prose.mdc` — `alwaysApply` guidance to keep comments and descriptions lean at authoring time.

The commands delegate to the skills, so each rubric lives in one place. The `SKILL.md` / `.mdc` files are plain prompts and port cleanly to other agent tools (Claude Code, etc.).

## Install

### Private team marketplace (Teams/Enterprise)

1. Push this repo to a private GitHub repo.
2. In Cursor: **Dashboard → Settings → Plugins → Team Marketplaces → Add Marketplace → Import from Repo**.
3. Select `llm-prose`, set Team Access, optionally enable Auto Refresh, save.
4. Install it from the Plugins panel (user or project scope).

> Private-repo installs clone via your local git. If the install folder under `~/.cursor/plugins/cache/` is empty, make sure your machine has git access to the repo (PAT/`.netrc` or SSH), then reinstall.

### Local (just for you, no marketplace)

```bash
cp -R llm-prose ~/.cursor/plugins/local/llm-prose
```

Restart Cursor. The `.cursor-plugin/plugin.json` must sit at the folder root.

### Or drop pieces straight into a project

Copy `skills/` into `.cursor/skills/`, `commands/` into `.cursor/commands/`, and `rules/` into `.cursor/rules/`. Copy the skills alongside the commands — the commands delegate to skills by name and won't work without them.

## Layout

```
llm-prose/
├── .cursor-plugin/plugin.json
├── commands/
│   ├── review-prose.md
│   ├── review-pr-comments.md
│   └── review-pr-description.md
├── rules/
│   └── llm-prose.mdc
└── skills/
    ├── review-prose/SKILL.md
    ├── comment-bloat-review/SKILL.md
    └── pr-description-review/SKILL.md
```
