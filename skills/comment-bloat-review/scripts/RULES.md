# deslop rule catalog

`deslop` is the deterministic pre-pass for `comment-bloat-review`. It is stdlib-
only, single-file, and bundled in this skill so it runs on every review with no
install. It covers **only** the two patterns a regex / stdlib parser can decide
without judgment. Everything ambiguous — narration vs. why, doc-dump tightening,
staleness, intent — is left to the skill. Precision over recall: when a case is
debatable, deslop stays silent and the model decides.

## How it sees comments

A small character scanner walks the source once, skipping string and triple-
quoted literals so a `#` or `//` inside a string never registers as a comment.
Line comments (`#`, `//`, `--`) and block comments (`/* … */`) are recognized per
language by file extension. The `'` character is handled per language: a real
string delimiter (Python, Ruby, JS/TS, shell, SQL), a char/rune literal validated
by pattern (Rust, Go, C/C++, Java — so a bare lifetime tick `'a` is *not* mistaken
for a string and doesn't swallow a trailing `//`), or absent entirely (Swift).
In `--diff` mode the real file on disk is linted and findings are filtered to the
added line numbers, so diffs keep full-file context.

Requires Python 3.8+ (stdlib only; no third-party packages).

### R1 — notes-to-self / LLM residue  (action: delete)

A comment whose text matches a curated phrase set: the model talking to itself
or to the reviewer.

- Triggers (matched anywhere): `as requested`, `as you (asked|requested)`,
  `per (your|the) feedback`, `per review`, `note: I`, `as a reminder`.
- Triggers (only when they *lead* the comment): `I (changed|added|updated|
  removed|renamed|refactored|made|fixed) …`, `updated to …`. Anchored to the
  start because the same verbs mid-sentence ("the digest I compute") are
  ordinary descriptive prose.
- Deliberately *not* triggered: bare version (`vX.Y`) or ISO-date mentions —
  they false-positive on legitimate why-comments that cite an API version or a
  deprecation date, exactly the prose we want to keep.
- Language scope: all (operates on comment text).

### R2 — commented-out code  (action: delete)

A comment whose body reads as code rather than prose.

- Python: the stripped body is parsed with the stdlib `ast`; it's code if the
  parse succeeds and yields an assignment, import, loop/branch, or a call
  expression. This is exact — prose like "round half-up because refunds bite us"
  raises `SyntaxError` and is left alone.
- Other languages: a conservative heuristic — an assignment (`x = …`, `int n = …`,
  `const x = …`; never `==`/`<=`/etc.) or a bare call statement (`doRefund(c, a);`).
  Less precise than a real parser, but tuned to flag the common commented-out
  patterns without catching sentences. The assignment RHS must carry a code
  signal (operator, call/index, member access, quote, number) — `default = usd`
  is prose, not code.
- Never triggered (precision exemptions, all found by dogfooding):
  - Lines leading with `TODO`/`FIXME`/`NOTE`/`HACK`/`XXX`/`WARNING` — intentional markers.
  - Tool directives / pragmas: `shellcheck disable=…`, `noqa`, `type: ignore`,
    `eslint-disable-*`, `@ts-expect-error`, `pylint:`/`mypy:`/`ruff:` etc.
  - Prose sentences that merely happen to contain `=` and a parenthetical —
    natural-language tells (a sentence boundary, a trailing period, a `, not …`
    clause) gate the heuristic, so `Pass = every run. Smoke test (LLM + network).`
    stays silent.
  - Env-var-prefixed usage examples (`MODEL=foo bash run.sh`) — documentation, not
    dead code. A real `NAME = value` config line with no trailing command still fires.

## What deslop deliberately does NOT do

- **Doc-dump / docstring-restates-signature** is *not* a deslop rule. It needs
  judgment (is the doc warranted? is the summary substantive?) and, on Python,
  is already covered more thoroughly by `pydoclint` / `docsig`. The skill judges
  it; deslop stays out.
- Anything requiring intent, taste, or whole-PR context.

## Testing

`tests/` holds the invariants one-per-test (including the false-positive
boundaries) plus the diff/CLI behavior. Stdlib-only tool, so the only dev
dependency is `pytest`:

```bash
pip install pytest
python -m pytest skills/comment-bloat-review/scripts/tests -q
```
