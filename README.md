# llm-prose

A plugin that reviews the **prose layer** of LLM-authored changes — the *comments* in your diff and the *PR description* — not the code's correctness. It does the two cleanup passes that are easy to forget and tedious by hand, and ships a rule that keeps the agent from creating the mess in the first place.

Works in **Cursor** and **Claude Code**, on a GitHub PR (via `gh`) or a plain local/branch diff.

## Ethos

LLMs write code well and write *about* code badly. They leave their working memory in comments, over-document the obvious, and ship PR descriptions that list files instead of explaining a change. This plugin encodes two opinions:

**Comments** should be as short as possible while carrying as much relevant information as possible, and exist only where relevant — never as one giant block. Before keeping one, ask: *"What do I actually care about here — is this for a human, or just the LLM's scratchpad?"* Keep intent, *why* over *what*, trade-offs, constraints, gotchas, links to context, and required public-API docs. Cut narration, notes-to-self (`// as requested`, `// updated to handle X`), commented-out code, and doc dumps.

**Descriptions** should answer **What / Why / How** and surface **interface and breaking changes** — the things a reviewer and a future reader actually need. The *Why* is the part LLMs skip and the part that matters most; the tool **never invents it** — if the motivation isn't in the diff, a ticket, or the branch context, it asks or leaves a placeholder rather than fabricating one. De-slopping is the floor: the rewrite is *crafted* to be read — a strong lead, scannable structure, a behavior/interface callout. Structure and formatting serve the reader and are welcome; the sin is decoration over empty content, not headings or bullets.

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

Restart/reload each tool once to pick it up. The `review-prose` skill then auto-activates on relevant tasks, and the `/prose*` commands are available explicitly.

**Updating — read this, it's tool-specific.** `"autoUpdate": true` (in `~/.claude/plugins/known_marketplaces.json`) is honored **only by Claude Code**, on launch. **Cursor does not auto-update** — it loads whatever version is pinned in `~/.claude/plugins/installed_plugins.json` and never checks the remote itself. So:

- **Claude Code:** with `autoUpdate` on, a new session pulls the latest. Or force it: `claude plugin update llm-prose@llm-prose`.
- **Cursor (IDE or CLI):** run `claude plugin update llm-prose@llm-prose` explicitly, **then restart Cursor**. Releases are version-keyed, so a session already running stays on its loaded version until you restart. (Want hands-off? Run that update command from a login hook or alias — Cursor won't do it for you.)

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

Normal flow:

1. Branch, then commit with a [conventional](https://www.conventionalcommits.org/) prefix — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `perf:`, `ci:`, `build:`, `style:` (use `feat!:` for breaking). An unrecognized prefix means **no bump and no release** — the merge lands on `main` but never reaches installed users.
2. Open a PR with a conventional **title** (it's the bump signal). Dogfood it: run `/prose` (or `/prose-code-comments`) on the diff.
3. On merge to `main`, `.github/workflows/version-bump.yml` reads the title/commits, bumps all three manifests (`major` for `feat!`, `minor` for `feat`, `patch` for the rest), validates they agree, commits `chore: bump … [skip ci]`, and tags `llm-prose--vX.Y.Z`.

Then `autoUpdate` refreshes on the next session, or pull it now with `claude plugin update llm-prose@llm-prose` (restart to apply).

Out-of-band releases (no PR):

- From GitHub: run the **auto version bump** workflow manually (Actions → Run workflow) and pick a level — handy for cutting a release off `main` without a code change.
- From a clone: `scripts/release.sh [patch|minor|major|X.Y.Z]` bumps locally. Its commit subject (`release: …`) isn't a conventional prefix, so the CI bumper skips it — no double bump.

## Tests

`scripts/validate.sh` (bash + jq, no other deps) checks the structural failure modes that actually break a plugin:

- manifests are valid JSON and agree on the plugin `name`
- every skill/command/rule has the required frontmatter
- each skill's declared `name` matches its directory
- **delegation integrity** — every `` `skill-name` `` a command delegates to exists as a real skill

Run `bash scripts/validate.sh`. CI (`.github/workflows/validate.yml`) runs it on every push and PR, so the remote can't go broken before you pull it.

**Behavioral eval** (`eval/run.sh`) — drives the real `comment-bloat-review` skill through the Cursor CLI against `eval/fixtures/sample.py`, which has comments tagged with sentinels: `CMT_B*` are planted bloat that must be flagged for deletion, `CMT_T*` are warranted public-API docs that must be flagged for *tightening* (not deleted), and `CMT_K*` are comments that must be kept. It scores recall (all bloat caught), action (tighten vs delete), and precision (no good comments flagged):

```bash
bash eval/run.sh              # one run, default model
RUNS=5 bash eval/run.sh       # repeat to gauge flakiness
MODEL=sonnet-4-thinking bash eval/run.sh
```

The fixture's slop is modeled on real in-the-wild patterns (narration, residue, doc dumps) catalogued in [`docs/anti-patterns.md`](docs/anti-patterns.md).

The description pass has its own behavioral eval (`eval/run_description.sh`) — it drives `pr-description-review` to rewrite weak drafts against real diffs, then scores the output. Three scenarios exercise different parts of the rubric:

- **session** — a real Why is available: the rewrite must use it, surface the behavior change, and read well (precision / substance / behavior / structure). `pr_description_good.md` is the crafted target it should approach.
- **thin-why** — the motivation is genuinely undiscoverable: the rewrite must **not fabricate** a Why, leaving an explicit author-prompt placeholder instead.
- **iface** — a refactor with a real signature change: the rewrite must surface the interface change for consumers, not bury it.
- **claims** — an overclaiming draft (asserts unit tests + a caching layer the diff doesn't contain): the rewrite must verify claims against the diff and **drop the phantom ones**, keeping only what the code backs.
- **template** — the repo has a PR template: the rewrite must compose **inside its headings and furniture** (ticket line, required sections), not impose the skill's own exemplar shape. Found by dogfooding on a real repo where skill-written descriptions looked alien next to template-following ones.

Scoring is on qualities, not exact strings: **precision** (no AI filler survives), **substance** (real Why present, or correctly deferred), **behavior/interface** (the consumer-facing change is surfaced), **claims-verified** (no invented tests/features survive), and **structure** (a lead + scannable sections).

```bash
bash eval/run_description.sh        # one run, default model
RUNS=3 bash eval/run_description.sh # repeat to gauge flakiness
```

This is an LLM eval, so treat it as a smoke test, not a hard gate — it needs CLI auth and network, which is why it's not in CI. Add fixtures as you find comment patterns the skill mishandles.

**Deterministic pre-pass** (`deslop`) — a stdlib-only, single-file script bundled *inside* the `comment-bloat-review` skill (`skills/comment-bloat-review/scripts/deslop.py`). The skill runs it on the diff before applying judgment, so the two unambiguous cases — LLM residue and commented-out code — are caught reproducibly on every review, with no install. It is intentionally narrow: anything debatable (narration, doc-dump tightening, staleness) it leaves to the model.

It's bundled rather than separately installed for a reason: Cursor exposes no plugin-root path or install hook, so a stdlib-only script in the skill's own `scripts/` dir is the one mechanism that reliably runs from any repo. Run it directly with the repo-root shim, and its tests with plain `pytest`:

```bash
git diff | scripts/deslop --diff
pip install pytest && python -m pytest skills/comment-bloat-review/scripts/tests -q
```

Rules and rationale: [skills/comment-bloat-review/scripts/RULES.md](skills/comment-bloat-review/scripts/RULES.md). On Python projects, `eradicate` and `pydoclint`/`docsig` are mature deeper checks for commented-out code and docstrings; `deslop`'s niche is being language-agnostic and always-on.

## Components

- **`skills/review-prose`** — context-aware entry point; auto-activates. Detects git/PR context and runs both passes against the right target.
- **`skills/comment-bloat-review`, `skills/pr-description-review`** — the rubrics. `disable-model-invocation`, so they load only when named (by `review-prose` or a command) and don't fire ambiently.
- **`commands/`** — the three slash commands above.
- **`rules/llm-prose.mdc`** — Cursor-only, globbed to code files, not always-on. Write-time comment discipline.
- **`skills/comment-bloat-review/scripts/deslop.py`** — a stdlib-only, language-agnostic deterministic pre-pass bundled in the skill, covering the two mechanical cases only: notes-to-self / LLM residue and commented-out code. No model, no install, so it's reproducible, CI-gateable, and runs on every review. Rules: [RULES.md](skills/comment-bloat-review/scripts/RULES.md).

## Portability

Skills (`SKILL.md`) and slash commands are a shared format, so Cursor and Claude Code both load them; the two manifests (`.cursor-plugin/`, `.claude-plugin/`) coexist in one repo. The `.mdc` rule is the only Cursor-specific piece. Other tools (Cline, Copilot) lack native plugin parity — copy the Markdown into their conventions.

## Further reading

See [`docs/anti-patterns.md`](docs/anti-patterns.md) for a gallery of real, sourced examples of the bloat this plugin catches — narration, doc dumps, dead code, and the "stately" AI-slop PR description — with the fixes.

The rubrics distill a few canonical sources — read these for the long form:

- **Comments** — [Go Doc Comments](https://go.dev/doc/comment) (the "improve the code so the comment isn't needed" ethos), [TigerBeetle TIGER_STYLE](https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/TIGER_STYLE.md) (comments explain *why*), [Swift API Design Guidelines](https://www.swift.org/documentation/api-design-guidelines/) + [Rust RFC 505](https://rust-lang.github.io/rfcs/0505-api-comment-conventions.html) (summary-first doc comments, structured sections), and GitHub's own [awesome-copilot self-explanatory-code-commenting instructions](https://github.com/github/awesome-copilot/blob/main/instructions/self-explanatory-code-commenting.instructions.md) (a catalog of the exact comment types to avoid).
- **PR descriptions** — [GitHub: how to write the perfect pull request](https://github.blog/developer-skills/github/how-to-write-the-perfect-pull-request/), [opensource.com: anatomy of a perfect PR](https://opensource.com/article/18/6/anatomy-perfect-pull-request) (small, single-purpose PRs), and [Chris Beams: how to write a git commit message](https://cbea.ms/git-commit/).

## Status

Manifests and frontmatter are validated (`scripts/validate.sh`, plus Claude's `plugin validate`). The behavioral eval passes, and the `review-prose` skill has been confirmed loading and self-describing in the Cursor CLI via the Claude install. The `disable-model-invocation` rubric skills surface only when named (by `review-prose` or a `/prose*` command), which is intended.

## Layout

```
llm-prose/
├── .cursor-plugin/plugin.json
├── .claude-plugin/{plugin,marketplace}.json
├── commands/{prose,prose-code-comments,prose-pr-description}.md
├── rules/llm-prose.mdc            # Cursor only
├── docs/anti-patterns.md          # sourced gallery of real bloat + fixes
├── eval/                          # behavioral eval + fixtures (comments & PR descriptions)
├── scripts/deslop                 # repo-root shim -> the bundled script
└── skills/
    ├── review-prose/SKILL.md
    ├── pr-description-review/SKILL.md
    └── comment-bloat-review/
        ├── SKILL.md
        └── scripts/               # deslop: stdlib-only deterministic pre-pass
            ├── deslop.py           # R1 residue + R2 commented-out code, --diff/file
            ├── RULES.md
            └── tests/              # invariants + diff/CLI behavior (pytest)
```
