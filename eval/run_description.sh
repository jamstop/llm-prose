#!/usr/bin/env bash
# Behavioral eval for the pr-description-review skill: drives the real skill
# through the Cursor CLI to rewrite weak PR descriptions, then scores the output.
#
# A description rewrite is generative, so we score qualities, not exact strings.
# Three scenarios exercise different parts of the rubric:
#
#   session   full-context craft: a real Why is available; rewrite must use it,
#             surface the behavior change, and read well (precision/substance/
#             behavior/structure).
#   thin-why  the motivation is NOT discoverable; rewrite must NOT fabricate a
#             Why — it must leave an explicit author-prompt placeholder.
#   iface     a refactor with a real signature change; rewrite must surface the
#             interface change for consumers, not bury it.
#
# Pass = every scenario passes every run. Smoke test (LLM + network), not a CI gate.
#
# Usage:  bash eval/run_description.sh            # default model, 1 run each
#         RUNS=3 bash eval/run_description.sh     # repeat to gauge flakiness
#         MODEL=sonnet-4-thinking bash eval/run_description.sh
set -uo pipefail
cd "$(dirname "$0")" || exit 2

PLUGIN="${PLUGIN_DIR:-$(cd .. && pwd)}"
RUNS="${RUNS:-1}"
MODEL_ARG=(); [ -n "${MODEL:-}" ] && MODEL_ARG=(--model "$MODEL")
command -v cursor-agent >/dev/null || { echo "cursor-agent not found on PATH"; exit 2; }

# Banned AI-filler — content-free phrases. NOT emoji or formatting: per the skill,
# form serves the reader and isn't slop, so we only flag empty phrasing here.
BANNED='several improvements|various other|more seamless|robustness and maintainability|ensure a more'

OUT=""        # current rewrite under test (set per scenario)
sfail=0       # per-scenario failure flag

agent() {
  cursor-agent --plugin-dir "$PLUGIN" ${MODEL_ARG[@]+"${MODEL_ARG[@]}"} \
    --trust --force -p "$1" --output-format text 2>/dev/null
}

has()  { grep -qiE "$1" <<<"$OUT"; }                       # pattern present?
chk()  { if [ "$1" = 1 ]; then echo "    ok   $2"; else echo "    FAIL $2"; sfail=1; fi; }
must()    { has "$1" && chk 1 "$2" || chk 0 "$2"; }        # pass if present
mustnot() { has "$1" && chk 0 "$2" || chk 1 "$2"; }        # pass if absent
precision() { mustnot "$BANNED" "precision — no banned filler"; }
structure() { local n; n=$(grep -cE '^[[:space:]]*(#|- )' <<<"$OUT"); [ "$n" -ge 2 ] && chk 1 "structure — $n heading/bullet lines" || chk 0 "structure — only $n"; }
rewrite()   { echo "    --- rewrite ---"; printf '%s\n' "$OUT" | sed 's/^/    | /'; }

REWRITE_INSTR="Output ONLY the rewritten description markdown — no verdict, no preamble, no code fences around the whole thing."

# --- scenario: full-context craft -------------------------------------------
scn_session() {
  echo "  [session] full-context craft"
  sfail=0
  OUT=$(agent "Use the pr-description-review skill from the loaded plugin to REWRITE the PR description below to its 'beautiful' bar. $REWRITE_INSTR

Current description:
---
$(cat fixtures/pr_description_stately.md)
---

Actual change (unified diff):
\`\`\`diff
$(cat fixtures/pr_description_change.diff)
\`\`\`

Context: ticket SUPPORT-1421 — users on long forms were logged out mid-task because the idle timer was never reset on authenticated requests; this makes session expiry idle-based instead of absolute.")
  precision
  has 'SUPPORT-1421' && has 'idle|last_seen|inactiv' && chk 1 "substance — real Why (ticket + mechanism)" || chk 0 "substance — grounded Why missing"
  must 'behavior change|no api change|no schema|interface|breaking|migration' "behavior — change/interface callout"
  structure
  rewrite
  return $sfail
}

# --- scenario: thin / undiscoverable Why ------------------------------------
scn_thinwhy() {
  echo "  [thin-why] must not fabricate a Why"
  sfail=0
  OUT=$(agent "Use the pr-description-review skill from the loaded plugin to REWRITE the PR description below. $REWRITE_INSTR

Current description:
---
$(cat fixtures/pr_description_nowhy_draft.md)
---

Actual change (unified diff):
\`\`\`diff
$(cat fixtures/pr_description_nowhy.diff)
\`\`\`

Context: no ticket is linked, the branch is 'chore/tune-retries', and the commit message is just 'tune retries'. The motivation is genuinely not recorded anywhere.")
  precision
  # Why must be flagged as needing the author, not invented. Look for a Why
  # label co-occurring with a placeholder / request-for-input signal.
  has 'why' && has "author:|_\(|todo|unknown|not (stated|clear|recorded|in the diff|specified|documented)|could ?n.?t|no (ticket|linked|context|motivation)|needs? (a )?(context|motivation|why)|please (add|provide|fill)" \
    && chk 1 "no-fabrication — Why left as author prompt" || chk 0 "no-fabrication — Why missing/invented"
  structure
  rewrite
  return $sfail
}

# --- scenario: refactor with interface change -------------------------------
scn_iface() {
  echo "  [iface] must surface the signature change"
  sfail=0
  OUT=$(agent "Use the pr-description-review skill from the loaded plugin to REWRITE the PR description below to its 'beautiful' bar. $REWRITE_INSTR

Current description:
---
$(cat fixtures/pr_description_iface_draft.md)
---

Actual change (unified diff):
\`\`\`diff
$(cat fixtures/pr_description_iface.diff)
\`\`\`

Context: consolidating user lookups — the public method is renamed and gains a keyword-only 'include_deleted' flag; callers across the app use it.")
  precision
  has 'fetch_user' && has 'renamed|signature|interface|breaking|callers?|→|->|include_deleted' \
    && chk 1 "interface — signature change surfaced" || chk 0 "interface — change buried"
  structure
  rewrite
  return $sfail
}

# --- driver ------------------------------------------------------------------
total=0 passed=0
for i in $(seq 1 "$RUNS"); do
  echo "=== run $i/$RUNS ==="
  for scn in scn_session scn_thinwhy scn_iface; do
    total=$((total+1))
    if "$scn"; then echo "  -> PASS"; passed=$((passed+1)); else echo "  -> FAIL"; fi
  done
done

echo "------------------------------------------------------------"
echo "passed $passed/$total scenario-run(s)"
[ "$passed" -eq "$total" ] && exit 0 || exit 1
