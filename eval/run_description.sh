#!/usr/bin/env bash
# Behavioral eval for the pr-description-review skill: drives the real skill
# through the Cursor CLI to rewrite a weak ("stately") description given the
# actual diff + the real Why, then scores the rewrite on four axes.
#
# Unlike the comment eval (sentinel tokens), a description rewrite is generative,
# so we score qualities, not exact strings:
#   PRECISION  — none of the banned AI-filler phrases survive
#   SUBSTANCE  — the real Why (ticket + mechanism) is present, not invented away
#   BEHAVIOR   — the behavior/interface change is surfaced (the reviewer's #1 fear)
#   STRUCTURE  — scannable: a lead + headings/bullets (the "structured" house style)
# Pass = all four. This is a smoke test (LLM + network), not a CI gate.
#
# Usage:  bash eval/run_description.sh            # default model
#         RUNS=3 bash eval/run_description.sh     # repeat to gauge flakiness
set -uo pipefail
cd "$(dirname "$0")" || exit 2

PLUGIN="${PLUGIN_DIR:-$(cd .. && pwd)}"
STATELY="$(cat fixtures/pr_description_stately.md)"
DIFF="$(cat fixtures/pr_description_change.diff)"
RUNS="${RUNS:-1}"
MODEL_ARG=(); [ -n "${MODEL:-}" ] && MODEL_ARG=(--model "$MODEL")

command -v cursor-agent >/dev/null || { echo "cursor-agent not found on PATH"; exit 2; }

# Banned AI-filler — if any survive the rewrite, precision failed.
BANNED='several improvements|various other|more seamless|robustness and maintainability|ensure a more|🚀|✨|🎉|✅'

PROMPT="Use the pr-description-review skill from the loaded plugin to REWRITE the PR description below to its 'beautiful' bar (strong lead, scannable structure, real Why, behavior callout). Output ONLY the rewritten description markdown — no verdict, no preamble, no code fences around the whole thing.

Current description:
---
$STATELY
---

Actual change (unified diff):
\`\`\`diff
$DIFF
\`\`\`

Context: ticket SUPPORT-1421 — users on long forms were being logged out mid-task because the idle timer was never reset on authenticated requests; this makes session expiry idle-based instead of absolute."

pass_runs=0
for i in $(seq 1 "$RUNS"); do
  echo "=== run $i/$RUNS ==="
  OUT=$(cursor-agent --plugin-dir "$PLUGIN" ${MODEL_ARG[@]+"${MODEL_ARG[@]}"} --trust --force -p "$PROMPT" --output-format text 2>/dev/null)

  fail=0
  if printf '%s' "$OUT" | grep -qiE "$BANNED"; then
    echo "  FAIL precision — banned filler survived"; fail=1
  else
    echo "  ok   precision — no banned filler"
  fi
  if printf '%s' "$OUT" | grep -qE 'SUPPORT-1421' && printf '%s' "$OUT" | grep -qiE 'idle|last_seen|inactiv'; then
    echo "  ok   substance — real Why present (ticket + mechanism)"
  else
    echo "  FAIL substance — grounded Why missing"; fail=1
  fi
  if printf '%s' "$OUT" | grep -qiE 'behavior change|no api change|no schema|interface|breaking|migration'; then
    echo "  ok   behavior  — change/interface callout present"
  else
    echo "  FAIL behavior  — no behavior/interface callout"; fail=1
  fi
  structure=$(printf '%s\n' "$OUT" | grep -cE '^\s*(#|- )')
  if [ "$structure" -ge 2 ]; then
    echo "  ok   structure — $structure heading/bullet lines"
  else
    echo "  FAIL structure — only $structure heading/bullet lines"; fail=1
  fi

  if [ "$fail" -eq 0 ]; then echo "  -> PASS"; pass_runs=$((pass_runs+1)); else echo "  -> FAIL"; fi
  echo "  --- rewrite ---"
  printf '%s\n' "$OUT" | sed 's/^/  | /'
done

echo "------------------------------------------------------------"
echo "passed $pass_runs/$RUNS run(s)"
[ "$pass_runs" -eq "$RUNS" ] && exit 0 || exit 1
