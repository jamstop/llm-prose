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
or to the reviewer, or a changelog left in code.

- Triggers: `as requested`, `as you (asked|requested)`, `per (your|the) feedback`,
  `per review`, `I (changed|added|updated|removed|renamed|made)`, `updated to`,
  `note: I`, `for now`, changelog-ish (`vX.Y`, ISO dates).
- Rationale: these never carry information a future reader needs.
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
  the body) and the parameter names. Parse Google-style sections. An `Args`
  entry or the `Returns` text is "redundant" when its content words are a subset
  of (summary words ∪ that entry's own name ∪ stopwords). Flag the docstring
  when at least one section is redundant.
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
