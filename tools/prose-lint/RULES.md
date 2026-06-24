# prose-lint rule catalog

The deterministic half of the `comment-bloat-review` rubric. Each rule here is a
mechanical, reproducible check run over an AST — no model, no judgment. Anything
that needs judgment stays with the LLM skill and is listed under "Not linted".

Substrate: `tree-sitter-language-pack` (one Rust core, 300+ grammars). Comments
are `(comment)` nodes; line/column and text come from byte offsets into the
source. "Commented-out code" is detected by *re-parsing* the comment body with
the same grammar — the trick a regex can't do reliably.

## Rules

### R1 — notes-to-self / LLM residue  (action: delete)
A comment whose text matches a curated phrase set: the model talking to itself
or to the reviewer.

- Triggers (matched anywhere): `as requested`, `as you (asked|requested)`,
  `per (your|the) feedback`, `per review`, `note: I`, `as a reminder`.
- Triggers (only when they *lead* the comment): `I (changed|added|updated|
  removed|renamed|refactored|made|fixed) …`, `updated to …`. Anchored to the
  start because the same verbs mid-sentence ("the digest I compute") are
  ordinary descriptive prose.
- Deliberately *not* triggered: bare version (`vX.Y`) or ISO-date mentions.
  They false-positive on legitimate why-comments that cite an API version or a
  deprecation date, which is exactly the prose we want to keep.
- Rationale: precision over recall — R1's value is being deterministic *and*
  trustworthy, so anything ambiguous is left to the LLM skill.
- Language scope: all (operates on comment text).

### R2 — commented-out code  (action: delete)
A comment whose body, with the marker stripped, parses as real code in the
file's own language.

- Mechanism: strip the comment marker, wrap in a minimal language scaffold if
  the grammar requires it (e.g. Go needs a func), re-parse. Flag when the parse
  has no ERROR node and contains an assignment or a call (the dominant shapes of
  commented-out code — deliberately narrow to keep false positives near zero).
- Skipped: comments starting with a prose marker (`TODO`, `FIXME`, `NOTE`,
  `HACK`, `XXX`, `WARNING`) — those are intentional notes, not dead code.
- Language scope: all (Python, JS/TS as-is; Go/Java/C wrapped).

### R3 — docstring restates the signature  (action: tighten)
A Python docstring whose `Args:`/`Returns:` sections add nothing over the
one-line summary and the parameter names.

- Mechanism: from the `function_definition`, read the docstring (first string in
  the body). Parse Google-style sections. An `Args` entry is "redundant" when its
  content words are a subset of (summary words ∪ that entry's own name ∪
  stopwords); the `Returns:` block is judged as a whole the same way. Flag the
  docstring when at least one section is redundant. A bare `Returns:` header
  (description wrapped onto the next line) is never redundant on its own — the
  wrapped text is collected and judged as a block, so a substantive multi-line
  return is left alone.
- Action is *tighten*, not delete: keep the summary (and any genuinely
  non-obvious note), cut the boilerplate sections. This is the 0.3.0 nuance.
- Language scope: Python first (docstrings); comment-style doc blocks for other
  languages are a later extension.

## Not linted (LLM judgment only)
- Narration that restates nearby code in prose ("increment the counter").
- Whether a comment's *intent* is worth keeping (why-over-what).
- Tighten-vs-delete as a judgment call beyond R3's mechanical case.
- Stale / contradictory comments (needs semantic understanding of the change).
- Everything about PR descriptions.

These remain the job of `skills/comment-bloat-review` and `skills/pr-description-review`.
