#!/usr/bin/env bash
# SkillForge — Structural Skill Analyzer
# Usage: bash analyze-skill.sh /path/to/SKILL.md
# Outputs: JSON score breakdown to stdout
#
# Scoring (100 pts total):
#   Frontmatter present:      10 pts
#   name field:               10 pts
#   description field:        10 pts (7 base + 3 for negative boundaries)
#   Under 500 lines:          10 pts
#   Has real examples:        10 pts (code blocks counted separately)
#   Progressive disclosure:   15 pts
#   Section headers:          10 pts
#   Referenced files exist:   10 pts
#   Imperative voice:          5 pts
#   No dead content:          10 pts (NEW: detects TODO/placeholder/fixme)

set -euo pipefail

SKILL_PATH="${1:?Usage: analyze-skill.sh /path/to/SKILL.md}"
SKILL_DIR="$(dirname "$SKILL_PATH")"
SCORE=0
MAX=100
ISSUES=()

# --- Check 1: File exists ---
if [[ ! -f "$SKILL_PATH" ]]; then
  printf '{"error":"SKILL.md not found","score":0}\n'
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
# Handles both inline and block scalar YAML descriptions:
#   description: inline text here
#   description: >
#     block text here
#   description: |
#     block text here
if echo "$CONTENT" | grep -qE "^description:"; then
  # Extract description block: from 'description:' until next top-level YAML key or end of frontmatter
  DESC_BLOCK=$(echo "$CONTENT" | sed -n '/^description:/,/^[a-zA-Z_-]*:/{ /^description:/p; /^  /p; /^    /p; }' | head -30)
  # Fallback: if block extraction found nothing useful, grab everything until next key
  if [[ -z "$DESC_BLOCK" ]]; then
    DESC_BLOCK=$(echo "$CONTENT" | sed -n '/^description:/,/^[a-z]/p' | head -30)
  fi
  DESC_WORDS=$(echo "$DESC_BLOCK" | wc -w)
  if [[ $DESC_WORDS -ge 15 ]]; then
    SCORE=$((SCORE + 7))
    if echo "$DESC_BLOCK" | grep -qiE "(do not|NOT|don't) use"; then
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

# --- Check 6: Has real examples (10 pts) ---
# Count REAL examples: input/output pairs, "Example N:", "e.g.", numbered examples
# Code blocks are counted separately and weighted lower (they support examples but aren't examples alone)
REAL_EXAMPLES=$(echo "$CONTENT" | grep -ciE '(example\s*[0-9:#]|input.*output|e\.g\.|for instance|for example)' || true)
CODE_BLOCKS=$(echo "$CONTENT" | grep -c '```' || true)
CODE_BLOCK_PAIRS=$((CODE_BLOCKS / 2))
# Real examples count fully, code block pairs count as 1/3 each
EXAM_SCORE=$((REAL_EXAMPLES + CODE_BLOCK_PAIRS / 3))

if [[ $REAL_EXAMPLES -ge 2 ]]; then
  SCORE=$((SCORE + 10))
elif [[ $REAL_EXAMPLES -ge 1 ]] || [[ $EXAM_SCORE -ge 2 ]]; then
  SCORE=$((SCORE + 5))
  ISSUES+=("few_real_examples")
else
  ISSUES+=("no_real_examples")
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
MISSING_REF_LIST=()
while IFS= read -r ref; do
  [[ -z "$ref" ]] && continue
  # Block path traversal attempts
  [[ "$ref" == *".."* ]] && continue
  ref_path="$SKILL_DIR/$ref"
  if [[ ! -f "$ref_path" && ! -d "$ref_path" ]]; then
    MISSING_REFS=$((MISSING_REFS + 1))
    MISSING_REF_LIST+=("$ref")
  fi
done < <(echo "$CONTENT" | grep -oE '(references|scripts|templates)/[a-zA-Z0-9_./-]+' | sort -u)

if [[ $MISSING_REFS -eq 0 ]]; then
  SCORE=$((SCORE + 10))
else
  ISSUES+=("missing_referenced_files:${MISSING_REF_LIST[*]}")
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

# --- Check 11: No dead content (10 pts) ---
TODO_COUNT=$(echo "$CONTENT" | grep -ciE "(TODO|FIXME|HACK|XXX|placeholder)" || true)
EMPTY_SECTION_COUNT=$(echo "$CONTENT" | grep -cE "^##" || true)
EMPTY_SECTIONS=0
# Check for headers followed by only blank lines or next header (empty sections)
while IFS= read -r line_num; do
  [[ -z "$line_num" ]] && continue
  NEXT_CONTENT=$(echo "$CONTENT" | tail -n +"$((line_num + 1))" | head -5 | grep -cvE "^$|^#" || true)
  if [[ $NEXT_CONTENT -eq 0 ]]; then
    EMPTY_SECTIONS=$((EMPTY_SECTIONS + 1))
  fi
done < <(echo "$CONTENT" | grep -nE "^##" | cut -d: -f1)

if [[ $TODO_COUNT -eq 0 ]] && [[ $EMPTY_SECTIONS -eq 0 ]]; then
  SCORE=$((SCORE + 10))
elif [[ $TODO_COUNT -eq 0 ]]; then
  SCORE=$((SCORE + 7))
  ISSUES+=("has_empty_sections:$EMPTY_SECTIONS")
else
  ISSUES+=("has_todo_or_placeholder_text:$TODO_COUNT")
  if [[ $EMPTY_SECTIONS -gt 0 ]]; then
    ISSUES+=("has_empty_sections:$EMPTY_SECTIONS")
  fi
fi

# --- Safe JSON Output (no injection) ---
# Use python3 for safe JSON serialization if available, else careful escaping
if command -v python3 &>/dev/null; then
  # Build issues array as newline-separated for python
  ISSUES_NL=""
  for issue in "${ISSUES[@]+"${ISSUES[@]}"}"; do
    ISSUES_NL="${ISSUES_NL}${issue}"$'\n'
  done

  python3 -c "
import json, sys

skill_path = sys.argv[1]
line_count = int(sys.argv[2])
score = int(sys.argv[3])
max_score = int(sys.argv[4])
real_examples = int(sys.argv[5])
code_block_pairs = int(sys.argv[6])
hdr_count = int(sys.argv[7])
has_frontmatter = sys.argv[8] == 'true'
has_references = sys.argv[9] == 'true'
has_scripts = sys.argv[10] == 'true'
issues_raw = sys.argv[11].strip()
issues = [i for i in issues_raw.split('\n') if i]

print(json.dumps({
    'skill_path': skill_path,
    'line_count': line_count,
    'structure_score': score,
    'max_score': max_score,
    'issues': issues,
    'has_frontmatter': has_frontmatter,
    'has_references': has_references,
    'has_scripts': has_scripts,
    'real_example_count': real_examples,
    'code_block_pairs': code_block_pairs,
    'header_count': hdr_count,
}, indent=2))
" \
    "$SKILL_PATH" \
    "$LINE_COUNT" \
    "$SCORE" \
    "$MAX" \
    "$REAL_EXAMPLES" \
    "$CODE_BLOCK_PAIRS" \
    "$HDR_COUNT" \
    "$(echo "$CONTENT" | head -1 | grep -q "^---" && echo true || echo false)" \
    "$(test -d "$SKILL_DIR/references" && echo true || echo false)" \
    "$(test -d "$SKILL_DIR/scripts" && echo true || echo false)" \
    "$ISSUES_NL"
else
  # Fallback: manual JSON (escape special chars in path)
  SAFE_PATH=$(echo "$SKILL_PATH" | sed 's/\\/\\\\/g; s/"/\\"/g')
  if [[ ${#ISSUES[@]} -gt 0 ]]; then
    ISSUES_JSON=$(printf '"%s",' "${ISSUES[@]}" | sed 's/,$//')
  else
    ISSUES_JSON=""
  fi
  cat <<ENDJSON
{
  "skill_path": "${SAFE_PATH}",
  "line_count": ${LINE_COUNT},
  "structure_score": ${SCORE},
  "max_score": ${MAX},
  "issues": [${ISSUES_JSON:-}],
  "has_frontmatter": $(echo "$CONTENT" | head -1 | grep -q "^---" && echo true || echo false),
  "has_references": $(test -d "$SKILL_DIR/references" && echo true || echo false),
  "has_scripts": $(test -d "$SKILL_DIR/scripts" && echo true || echo false),
  "real_example_count": ${REAL_EXAMPLES},
  "code_block_pairs": ${CODE_BLOCK_PAIRS},
  "header_count": ${HDR_COUNT}
}
ENDJSON
fi
