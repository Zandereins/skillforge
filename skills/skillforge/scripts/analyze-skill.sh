#!/usr/bin/env bash
# SkillForge — Structural Skill Analyzer
# Usage: bash analyze-skill.sh /path/to/SKILL.md
# Outputs: JSON score breakdown to stdout

set -euo pipefail

SKILL_PATH="${1:?Usage: analyze-skill.sh /path/to/SKILL.md}"
SKILL_DIR="$(dirname "$SKILL_PATH")"
SCORE=0
MAX=100
ISSUES=()

# --- Check 1: File exists ---
if [[ ! -f "$SKILL_PATH" ]]; then
  echo '{"error": "SKILL.md not found", "score": 0}'
  exit 1
fi

CONTENT=$(cat "$SKILL_PATH")
LINE_COUNT=$(wc -l < "$SKILL_PATH")

# --- Check 2: Frontmatter present (10 pts) ---
if echo "$CONTENT" | head -1 | grep -q "^---"; then
  CLOSING=$(echo "$CONTENT" | tail -n +2 | grep -n "^---" | head -1)
  if [[ -n "$CLOSING" ]]; then
    SCORE=$((SCORE + 10))
  else
    SCORE=$((SCORE + 5))
    ISSUES+=("frontmatter_not_closed")
  fi
else
  ISSUES+=("missing_frontmatter")
fi

# --- Check 3: name field (10 pts) ---
if echo "$CONTENT" | grep -qE "^name:\s*\S+"; then
  SCORE=$((SCORE + 10))
else
  ISSUES+=("missing_name_field")
fi

# --- Check 4: description field (10 pts) ---
if echo "$CONTENT" | grep -qE "^description:"; then
  DESC_BLOCK=$(echo "$CONTENT" | sed -n '/^description:/,/^[a-z]/p' | head -30)
  DESC_WORDS=$(echo "$DESC_BLOCK" | wc -w)
  if [[ $DESC_WORDS -ge 15 ]]; then
    SCORE=$((SCORE + 7))
    if echo "$DESC_BLOCK" | grep -qiE "(do not|NOT) use"; then
      SCORE=$((SCORE + 3))
    else
      ISSUES+=("description_missing_negative_boundaries")
      SCORE=$((SCORE + 1))
    fi
  else
    ISSUES+=("description_too_short")
    SCORE=$((SCORE + 5))
  fi
else
  ISSUES+=("missing_description_field")
fi

# --- Check 5: SKILL.md under 500 lines (10 pts) ---
if [[ $LINE_COUNT -le 500 ]]; then
  SCORE=$((SCORE + 10))
elif [[ $LINE_COUNT -le 700 ]]; then
  SCORE=$((SCORE + 5))
  ISSUES+=("skill_md_long")
else
  ISSUES+=("skill_md_very_long")
fi

# --- Check 6: Has examples (10 pts) ---
EXAM_COUNT=$(echo "$CONTENT" | grep -ciE 'example|```' || true)
if [[ $EXAM_COUNT -ge 3 ]]; then
  SCORE=$((SCORE + 10))
elif [[ $EXAM_COUNT -ge 1 ]]; then
  SCORE=$((SCORE + 5))
  ISSUES+=("few_examples")
else
  ISSUES+=("no_examples")
fi

# --- Check 7: Progressive disclosure (15 pts) ---
if [[ -d "$SKILL_DIR/references" ]]; then
  REF_COUNT=$(find "$SKILL_DIR/references" -name "*.md" | wc -l)
  if [[ $REF_COUNT -ge 1 ]]; then
    SCORE=$((SCORE + 15))
  fi
elif [[ $LINE_COUNT -le 200 ]]; then
  SCORE=$((SCORE + 15))
else
  ISSUES+=("no_references_dir_for_large_skill")
  SCORE=$((SCORE + 5))
fi

# --- Check 8: Section headers (10 pts) ---
HDR_COUNT=$(echo "$CONTENT" | grep -c "^##" || true)
if [[ $HDR_COUNT -ge 3 ]]; then
  SCORE=$((SCORE + 10))
elif [[ $HDR_COUNT -ge 1 ]]; then
  SCORE=$((SCORE + 5))
  ISSUES+=("few_headers")
else
  ISSUES+=("no_section_headers")
fi

# --- Check 9: Referenced files exist (10 pts) ---
MISSING_REFS=0
while IFS= read -r ref; do
  ref_path="$SKILL_DIR/$ref"
  if [[ ! -f "$ref_path" && ! -d "$ref_path" ]]; then
    MISSING_REFS=$((MISSING_REFS + 1))
  fi
done < <(echo "$CONTENT" | grep -oE '(references|scripts|templates)/[a-zA-Z0-9_./-]+' | sort -u)

if [[ $MISSING_REFS -eq 0 ]]; then
  SCORE=$((SCORE + 10))
else
  ISSUES+=("missing_referenced_files")
  SCORE=$((SCORE + 5))
fi

# --- Check 10: Imperative voice (5 pts) ---
HEDGE_COUNT=$(echo "$CONTENT" | grep -ciE "you (might|could|should|may) (want to|consider|possibly)" || true)
if [[ $HEDGE_COUNT -eq 0 ]]; then
  SCORE=$((SCORE + 5))
elif [[ $HEDGE_COUNT -le 2 ]]; then
  SCORE=$((SCORE + 3))
  ISSUES+=("minor_hedging")
else
  ISSUES+=("excessive_hedging")
fi

# --- Output ---
if [[ ${#ISSUES[@]} -gt 0 ]]; then
  ISSUES_JSON=$(printf '"%s",' "${ISSUES[@]}" | sed 's/,$//')
else
  ISSUES_JSON=""
fi
cat <<EOF
{
  "skill_path": "$SKILL_PATH",
  "line_count": $LINE_COUNT,
  "structure_score": $SCORE,
  "max_score": $MAX,
  "issues": [${ISSUES_JSON:-}],
  "has_frontmatter": $(echo "$CONTENT" | head -1 | grep -q "^---" && echo true || echo false),
  "has_references": $(test -d "$SKILL_DIR/references" && echo true || echo false),
  "has_scripts": $(test -d "$SKILL_DIR/scripts" && echo true || echo false),
  "example_count": $EXAM_COUNT,
  "header_count": $HDR_COUNT
}
EOF
