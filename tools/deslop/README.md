# deslop

Deterministic, AST-based linter for the mechanical half of the `comment-bloat-review`
rubric. No model: given a file, it always returns the same findings. The LLM
skills keep the judgment calls; this is the part that can be a CI gate and a
real, non-flaky score. Rules and rationale: [RULES.md](RULES.md).

> Scope note: `deslop` only covers the *unambiguous, mechanical* cases. For
> Python specifically, mature tools already do most of this — [`eradicate`](https://github.com/wemake-services/flake8-eradicate)
> for commented-out code, [`pydoclint`](https://jsh9.github.io/pydoclint/) /
> [`docsig`](https://github.com/jshwi/docsig) for docstring/signature checks.
> Reach for those on Python projects; `deslop`'s value is being multi-language
> (tree-sitter) and an *anti-redundancy* pre-pass for the skills. The real
> product is the judgment layer in `skills/`.

## Install

```bash
python3 -m venv tools/deslop/.venv
tools/deslop/.venv/bin/python -m pip install -e "tools/deslop[test]"
```

(`tree-sitter-language-pack` fetches each grammar on first use and caches it.)

## Use

```bash
# Lint whole files
scripts/deslop path/to/file.py path/to/other.go

# Lint only the comments added in a diff (tool-agnostic)
git diff | scripts/deslop --diff
gh pr diff 42 | scripts/deslop --diff

# JSON for machines; --max sets the allowed finding count before non-zero exit
scripts/deslop --format json src/
```

## Test (the deterministic score)

```bash
tools/deslop/.venv/bin/python -m pytest tools/deslop -q
```

`tests/` holds labeled fixtures with hand-specified expected findings; the suite
asserts exact match, so a rule regression fails loudly and reproducibly.
