#!/usr/bin/env bash
# Behavioral eval for the pr-description-review skill: drives the real skill
# through the Cursor CLI to rewrite weak PR descriptions, then scores the output.
#
# A description rewrite is generative, so we score qualities, not exact strings.
# Six scenarios exercise different parts of the rubric:
#
#   session   full-context craft: a real Why is available; rewrite must use it,
#             surface the behavior change, and read well.
#   thin-why  the motivation is NOT discoverable; rewrite must NOT fabricate a
#             Why — it must leave an explicit author-prompt placeholder.
#   iface     a refactor with a real signature change; rewrite must surface the
#             interface change for consumers, not bury it.
#   claims    an overclaiming draft; phantom claims must be dropped.
#   template  the repo has a PR template; its shape must win over the exemplar,
#             with no invented headings.
#   compress  an accurate-but-overlong draft; the rewrite must come back inside
#             the one-minute budget without losing the substance.
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

# --- scenario: overclaiming draft (claims must be verified vs the diff) ------
scn_claims() {
  echo "  [claims] must drop claims the diff doesn't back"
  sfail=0
  OUT=$(agent "Use the pr-description-review skill from the loaded plugin to REWRITE the PR description below to its 'beautiful' bar. $REWRITE_INSTR

Current description:
---
$(cat fixtures/pr_description_overclaim_draft.md)
---

Actual change (unified diff):
\`\`\`diff
$(cat fixtures/pr_description_overclaim.diff)
\`\`\`

Context: none beyond the diff. Verify every claim against the diff before writing.")
  precision
  # The draft claims unit tests + a caching layer; the diff has neither. A correct
  # rewrite drops both phantom claims. Two-step check, because the skill *instructs*
  # honest negations ("No automated tests; verified manually …") which must not
  # fail it: drop negated lines first, then any surviving assertive test claim is
  # phantom. POSIX ERE only: plain groups, and [^.] not [^.\n] — inside a bracket
  # expression \n is the two literal chars backslash+n, which silently excludes
  # the letter n and broke matching on e.g. "adds new tests".
  positive=$(grep -viE '\bno\b[^.]*\btest|without tests?|not (been )?tested' <<<"$OUT")
  if grep -qiE '(added|adds|introduc[a-z]+|comprehensive|includes?)[^.]*\btests?\b|unit tests|test coverage' <<<"$positive"; then
    chk 0 "no-phantom-tests — invented test claim survived"
  else
    chk 1 "no-phantom-tests — invented test claim dropped"
  fi
  mustnot 'cach' "no-phantom-cache — invented caching claim dropped"
  must 'empty|at least one item|\bitems\b' "substance — the real change (empty-order check) is kept"
  structure
  rewrite
  return $sfail
}

# --- scenario: repo with a PR template (template shape must win) -------------
scn_template() {
  echo "  [template] repo template headings must win over the exemplar"
  sfail=0
  OUT=$(agent "Use the pr-description-review skill from the loaded plugin to REWRITE the PR description below to its 'beautiful' bar. $REWRITE_INSTR

This repo has a PR template (.github/pull_request_template.md):
---
$(cat fixtures/pr_description_template.md)
---

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
  # Composed inside the template: its headings + ticket line present...
  has '### Summary' && has '### Changes' && has '### Testing' && has 'Resolves:' \
    && chk 1 "template — repo headings + ticket line used" \
    || chk 0 "template — repo shape missing"
  # ...and the exemplar's no-template shape did NOT leak in: neither its `###`
  # headings nor standalone bold-line pseudo-headings (a bold *label* inside a
  # template section, like `**Behavior change:** text`, is fine — only a bare
  # bold line acting as a heading counts).
  mustnot '^#+ (How|Verify|Behavior change)\b|^\*\*(How|Verify|Preserved|Behavior change):?\*\*[[:space:]]*$' \
    "no-leak — exemplar headings kept out of a templated repo"
  # ...and no headings the template doesn't define were invented (field failure:
  # "What's in it" / "Known trade-off" sections alongside half the template).
  invented=$(grep -E '^#+ ' <<<"$OUT" | grep -viE '^#+ (Summary|Changes|Testing|Screenshots & Videos|Human Notes)[[:space:]]*$')
  [ -z "$invented" ] && chk 1 "no-invention — only template headings used" \
    || chk 0 "no-invention — invented heading(s): $(tr '\n' ';' <<<"$invented")"
  has 'SUPPORT-1421' && chk 1 "substance — real Why carried over" || chk 0 "substance — Why lost"
  rewrite
  return $sfail
}

# --- scenario: accurate-but-overlong draft (must compress) --------------------
scn_compress() {
  echo "  [compress] accurate-but-overlong draft must shrink to the one-minute budget"
  sfail=0
  OUT=$(agent "Use the pr-description-review skill from the loaded plugin to REWRITE the PR description below to its bar. $REWRITE_INSTR

Current description:
---
$(sed '/^<!--/,/-->$/d' fixtures/pr_description_overlong_draft.md)
---

Actual change (unified diff):
\`\`\`diff
$(cat fixtures/pr_description_change.diff)
\`\`\`

Context: ticket SUPPORT-1421 — users on long forms were logged out mid-task; every claim in the draft is accurate, nothing is missing. The draft's only defect is its own length.")
  precision
  # The core assertion: substantially shorter. Draft body is ~380 words; the
  # budget in the skill is ~200-300 for a typical PR, and this change is small.
  draft_words=$(sed '/^<!--/,/-->$/d' fixtures/pr_description_overlong_draft.md | wc -w)
  out_words=$(wc -w <<<"$OUT")
  [ "$out_words" -le $((draft_words * 60 / 100)) ] \
    && chk 1 "budget — $out_words words (draft $draft_words, limit 60%)" \
    || chk 0 "budget — $out_words words vs draft $draft_words (limit 60%)"
  # Bullets are one line: no '- ' line runs past ~200 chars (a wrapped-prose bullet).
  longest=$(grep -E '^[[:space:]]*- ' <<<"$OUT" | awk '{ if (length($0) > m) m = length($0) } END { print m+0 }')
  [ "$longest" -le 200 ] && chk 1 "bullets — longest ${longest} chars" \
    || chk 0 "bullets — a ${longest}-char bullet survived"
  # Substance survives the cut: the Why, the mechanism, and the behavior callout.
  has 'SUPPORT-1421' && has 'idle|last_seen|inactiv' && chk 1 "substance — Why + mechanism kept" || chk 0 "substance — lost in compression"
  must 'no schema|no migration|still expire|behavior' "behavior — preserved/changed callout kept"
  rewrite
  return $sfail
}

# --- driver ------------------------------------------------------------------
total=0 passed=0
for i in $(seq 1 "$RUNS"); do
  echo "=== run $i/$RUNS ==="
  for scn in scn_session scn_thinwhy scn_iface scn_claims scn_template scn_compress; do
    total=$((total+1))
    if "$scn"; then echo "  -> PASS"; passed=$((passed+1)); else echo "  -> FAIL"; fi
  done
done

echo "------------------------------------------------------------"
echo "passed $passed/$total scenario-run(s)"
[ "$passed" -eq "$total" ] && exit 0 || exit 1
