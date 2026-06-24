# prose-lint

Deterministic, AST-based linter for the mechanical half of the `comment-bloat-review`
rubric. No model: given a file, it always returns the same findings. The LLM
skills keep the judgment calls; this is the part that can be a CI gate and a
real, non-flaky score. Rules and rationale: [RULES.md](RULES.md).

## Install

```bash
python3 -m venv tools/prose-lint/.venv
tools/prose-lint/.venv/bin/python -m pip install -e "tools/prose-lint[test]"
```

(`tree-sitter-language-pack` fetches each grammar on first use and caches it.)

## Use

```bash
# Lint whole files
scripts/prose-lint path/to/file.py path/to/other.go

# Lint only the comments added in a diff (tool-agnostic)
git diff | scripts/prose-lint --diff
gh pr diff 42 | scripts/prose-lint --diff

# JSON for machines; --max sets the allowed finding count before non-zero exit
scripts/prose-lint --format json src/
```

## Test (the deterministic score)

```bash
tools/prose-lint/.venv/bin/python -m pytest tools/prose-lint -q
```

`tests/` holds labeled fixtures with hand-specified expected findings; the suite
asserts exact match, so a rule regression fails loudly and reproducibly.
