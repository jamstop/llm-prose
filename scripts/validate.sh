#!/usr/bin/env bash
# Structural validation for the llm-prose plugin.
# Catches the failure modes that actually break plugins: bad JSON, missing
# frontmatter, skill name/dir mismatch, and broken command->skill delegation.
# Deps: bash + jq only (so it runs the same locally and in CI).
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2
fail=0
err() { echo "FAIL: $*"; fail=1; }
ok()  { echo "ok:   $*"; }

# --- frontmatter helpers ---------------------------------------------------
# Print the YAML frontmatter block (between the first two `---` lines).
frontmatter() { awk 'NR==1&&$0!="---"{exit} NR==1{next} $0=="---"{exit} {print}' "$1"; }
fm_value() { frontmatter "$1" | sed -n "s/^$2:[[:space:]]*//p" | head -1 | tr -d '"'; }
has_fm()   { [ "$(head -1 "$1")" = "---" ] && frontmatter "$1" | grep -q "^$2:"; }

# --- JSON manifests --------------------------------------------------------
for f in .cursor-plugin/plugin.json .claude-plugin/plugin.json .claude-plugin/marketplace.json; do
  if [ ! -f "$f" ]; then err "missing $f"; continue; fi
  if jq empty "$f" 2>/dev/null; then ok "valid JSON: $f"; else err "invalid JSON: $f"; fi
done

cursor_name=$(jq -r '.name // ""' .cursor-plugin/plugin.json 2>/dev/null)
claude_name=$(jq -r '.name // ""' .claude-plugin/plugin.json 2>/dev/null)
[ "$cursor_name" = "$claude_name" ] && [ -n "$cursor_name" ] \
  && ok "manifest names match ($cursor_name)" \
  || err "manifest names differ: cursor='$cursor_name' claude='$claude_name'"
echo "$cursor_name" | grep -qE '^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$' \
  && ok "name is kebab-case" || err "name not kebab-case: '$cursor_name'"

# --- versions agree across all manifests (else `claude plugin update` won't ship)
cver=$(jq -r '.version // ""' .cursor-plugin/plugin.json)
clver=$(jq -r '.version // ""' .claude-plugin/plugin.json)
mver=$(jq -r '[.plugins[].version] | unique | join(",")' .claude-plugin/marketplace.json 2>/dev/null)
if [ -n "$cver" ] && [ "$cver" = "$clver" ] && [ "$cver" = "$mver" ]; then
  ok "versions agree ($cver)"
else
  err "version mismatch: cursor='$cver' claude='$clver' marketplace='$mver'"
fi

# --- skills: frontmatter + name matches directory --------------------------
declare -a skills=()
for d in skills/*/; do
  name=$(basename "$d")
  skills+=("$name")
  s="$d/SKILL.md"
  if [ ! -f "$s" ]; then err "skill '$name' has no SKILL.md"; continue; fi
  has_fm "$s" name && has_fm "$s" description || { err "$s missing name/description frontmatter"; continue; }
  declared=$(fm_value "$s" name)
  [ "$declared" = "$name" ] && ok "skill frontmatter matches dir: $name" \
    || err "skill '$name' declares name '$declared' (must match dir)"
done

# --- commands: frontmatter -------------------------------------------------
for c in commands/*.md; do
  [ -f "$c" ] || continue
  has_fm "$c" name && has_fm "$c" description \
    && ok "command frontmatter ok: $(basename "$c")" \
    || err "$c missing name/description frontmatter"
done

# --- referential integrity: every `skill-name` skill delegated to must exist
# Matches phrases like:  `comment-bloat-review` skill
known=" ${skills[*]} "
while IFS= read -r line; do
  f=${line%%:*}; ref=${line#*:}
  case "$known" in
    *" $ref "*) ok "delegation resolves: $ref ($f)";;
    *) err "$f references unknown skill: '$ref'";;
  esac
done < <(grep -roE '`[a-z][a-z0-9-]*` skill' commands skills 2>/dev/null \
          | sed -E 's/^([^:]+):`([a-z0-9-]+)` skill/\1:\2/' | sort -u)

# --- rule ------------------------------------------------------------------
for r in rules/*.mdc; do
  [ -f "$r" ] || continue
  has_fm "$r" description && ok "rule frontmatter ok: $(basename "$r")" \
    || err "$r missing description frontmatter"
done

# --- marketplace sources exist --------------------------------------------
while IFS= read -r src; do
  [ -z "$src" ] && continue
  [ -e "$src" ] && ok "marketplace source exists: $src" || err "marketplace source missing: $src"
done < <(jq -r '.plugins[].source // empty' .claude-plugin/marketplace.json 2>/dev/null)

echo "------------------------------------------------------------"
[ "$fail" -eq 0 ] && { echo "PASS"; exit 0; } || { echo "VALIDATION FAILED"; exit 1; }
