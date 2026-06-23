# pr-review

A Cursor plugin for reviewing LLM-authored PRs. It does the two cleanup passes that are easy to forget and tedious to do by hand:

1. **Comment bloat** — flags redundant narration, LLM-residue comments (the model's notes-to-self), over-documentation, stale/commented-out code, and proposes tighter edits. Keeps only comments that explain intent a human actually needs.
2. **Description quality** — checks a PR description against the real diff and rewrites it to cover **What / Why / How** and surface **interface/breaking changes**.

Works on a GitHub PR (via `gh`) or a local/branch diff.

## Components

**Commands** (explicit, deterministic):

| Command | Does |
| --- | --- |
| `/review-comments` | Comment-bloat pass only |
| `/review-description` | Description review + rewrite only |
| `/review-pr` | Both, in one pass |

**Skills** (auto-activate when the model judges the task relevant, e.g. during a code review):

- `comment-bloat-review`
- `pr-description-review`

The commands delegate to the skills, so the rubric lives in one place. The `SKILL.md` files are plain prompts and port cleanly to other agent tools (Claude Code, etc.).

## Install

### Private team marketplace (Teams/Enterprise)

1. Push this repo to a private GitHub repo.
2. In Cursor: **Dashboard → Settings → Plugins → Team Marketplaces → Add Marketplace → Import from Repo**.
3. Select `pr-review`, set Team Access, optionally enable Auto Refresh, save.
4. Install it from the Plugins panel (user or project scope).

> Private-repo installs clone via your local git. If the install folder under `~/.cursor/plugins/cache/` is empty, make sure your machine has git access to the repo (PAT/`.netrc` or SSH), then reinstall.

### Local (just for you, no marketplace)

```bash
cp -R pr-review ~/.cursor/plugins/local/pr-review
```

Restart Cursor. The `.cursor-plugin/plugin.json` must sit at the folder root.

### Or drop it straight into a project

Copy `skills/` into the repo's `.cursor/skills/` and `commands/` into `.cursor/commands/` to use it without the plugin system.

## Layout

```
pr-review/
├── .cursor-plugin/plugin.json
├── commands/
│   ├── review-comments.md
│   ├── review-description.md
│   └── review-pr.md
└── skills/
    ├── comment-bloat-review/SKILL.md
    └── pr-description-review/SKILL.md
```
