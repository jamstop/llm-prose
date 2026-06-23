# llm-prose

A plugin for reviewing the **prose layer** of LLM-authored changes — the comments and the PR description — not the code's correctness. It does the two cleanup passes that are easy to forget and tedious by hand:

1. **Comment bloat** — flags redundant narration, LLM-residue comments (the model's notes-to-self), over-documentation, stale/commented-out code, and proposes tighter edits. Keeps only comments that explain intent a human needs.
2. **Description quality** — checks a PR description against the real diff and rewrites it to cover **What / Why / How** and surface **interface/breaking changes**. It never invents the *Why*; if the motivation isn't discoverable it asks or leaves a placeholder.

It also ships a write-time **rule** that nudges the agent to avoid comment bloat in the first place, so review is a backstop rather than the only defense.

Works on a GitHub PR (via `gh`) or a local/branch diff.

## Components

**Skills** (`skills/`, shared by Cursor and Claude Code):

- `review-prose` — context-aware entry point. Auto-activates when you're wrapping up or reviewing a change. Detects whether you're in a git repo and on a working branch / have an open PR, then runs both passes against the right target.
- `comment-bloat-review`, `pr-description-review` — the rubrics it applies. Marked `disable-model-invocation`, so they load only when named (by `review-prose` or the commands) and don't fire ambiently on their own.

**Commands** (`commands/`, slash commands in both tools):

| Command | Does |
| --- | --- |
| `/review-prose` | Both passes, context-aware |
| `/review-pr-comments` | Comment-bloat pass only |
| `/review-pr-description` | Description review + rewrite only |

**Rule** (`rules/llm-prose.mdc`) — **Cursor only.** Globbed to code files (not always-on), it keeps comments lean at authoring time. Claude Code has no `.mdc` rules; the `review-prose` skill carries the same discipline there.

## Install

### Cursor — local (private, any plan)

Team Marketplaces are Teams/Enterprise only, so for a private personal repo, install locally — your machine's git handles the private clone:

```bash
git clone git@github.com:jamstop/llm-prose.git ~/.cursor/plugins/local/llm-prose
# update later: cd ~/.cursor/plugins/local/llm-prose && git pull
```

Restart Cursor. (`.cursor-plugin/plugin.json` is at the repo root.)

### Cursor — team marketplace (Teams/Enterprise)

Dashboard → Settings → Plugins → Team Marketplaces → Import from Repo. Requires the repo under a Teams/Enterprise org with the Cursor GitHub App installed.

### Claude Code

```
/plugin marketplace add jamstop/llm-prose
/plugin install llm-prose@llm-prose
```

(Uses `.claude-plugin/marketplace.json` + `.claude-plugin/plugin.json`. Skills and slash commands work; the `.mdc` rule does not — that discipline lives in the `review-prose` skill.)

### Any project, any tool

Copy `skills/` into `.cursor/skills/` (or `.claude/skills/`) and `commands/` into the tool's commands dir. Copy the skills alongside the commands — the commands delegate to skills by name and won't work without them.

## Portability

The substance is plain Markdown skills/commands, which Cursor and Claude Code both load (the SKILL.md format is shared). The two manifests (`.cursor-plugin/`, `.claude-plugin/`) coexist in one repo. The Cursor `.mdc` rule is the only Cursor-specific piece. Other tools (Cline, Copilot) have no native plugin parity — copy the Markdown into their own conventions.

## Status

Manifests and frontmatter validated. Skill auto-activation and command→skill loading are the standard model-invoked Skills mechanism but haven't been smoke-tested in a live session — run `/review-pr-comments` on a real diff once after install to confirm.

## Layout

```
llm-prose/
├── .cursor-plugin/plugin.json
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── commands/
│   ├── review-prose.md
│   ├── review-pr-comments.md
│   └── review-pr-description.md
├── rules/
│   └── llm-prose.mdc            # Cursor only
└── skills/
    ├── review-prose/SKILL.md
    ├── comment-bloat-review/SKILL.md
    └── pr-description-review/SKILL.md
```
