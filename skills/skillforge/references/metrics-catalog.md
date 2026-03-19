# Metrics Catalog — Skill Quality Scoring Rubrics

Each dimension is scored 0-100. This document defines what each score range means
and how to measure it mechanically.

## 1. Structure (weight: 0.15)

Measures whether the skill follows best practices for file organization
and progressive disclosure.

**Automated checks (via `scripts/analyze-skill.sh`):**

| Check | Points | Criteria |
|-------|--------|----------|
| Frontmatter present | 10 | Has `---` delimited YAML block |
| `name` field | 10 | Non-empty, lowercase, kebab-case |
| `description` field | 10 | Non-empty, 30-200 words, has negative boundaries |
| SKILL.md under 500 lines | 10 | Keeps context window manageable |
| Has examples | 10 | At least one input/output example |
| Progressive disclosure | 15 | References/ dir exists if SKILL.md > 200 lines |
| Clear section headers | 10 | Uses ## headings to organize content |
| No dead links | 10 | All referenced files exist |
| Consistent formatting | 10 | No mixed indent styles, clean markdown |
| Action-oriented | 5 | Uses imperative voice ("Do X", not "You should X") |

**Score ranges:**
- 90-100: Production-ready structure, follows all conventions
- 70-89: Good structure, minor gaps
- 50-69: Functional but disorganized
- 0-49: Missing critical elements (no frontmatter, no examples)

## 2. Trigger Accuracy (weight: 0.25)

Measures whether the skill activates for the right prompts and stays silent
for unrelated ones.

**Eval method:**
Create a test suite with:
- 10+ **positive triggers** — prompts that SHOULD activate the skill
- 5+ **negative triggers** — prompts that should NOT activate it
- 5+ **edge triggers** — ambiguous prompts near the boundary

```
trigger_score = (correct_activations / total_test_prompts) × 100
```

**Common trigger failures:**
- Description too narrow → misses valid use cases (false negatives)
- Description too broad → activates for unrelated tasks (false positives)
- Missing synonyms → user says "deploy" but description only says "release"
- No negative boundaries → activates for similar-but-wrong tasks

## 3. Output Quality (weight: 0.25)

Measures whether following the skill's instructions produces correct results.

**Assertion types:**

| Type | Example |
|------|---------|
| Contains | Output includes "## Summary" heading |
| Format | Output is valid YAML/JSON/Markdown |
| Length | Output is between 50-500 words |
| File created | Produces a file at expected path |
| Command succeeds | `npm test` exits with code 0 |
| Pattern match | Output matches regex |
| Excludes | Output does NOT contain "TODO" or placeholder text |

```
quality_score = (passing_assertions / total_assertions) × 100
```

## 4. Edge Coverage (weight: 0.15)

Measures how well the skill handles unusual inputs, missing context,
or unexpected scenarios.

**Edge case categories:**

| Category | Example |
|----------|---------|
| Empty input | User provides no context or files |
| Malformed input | Broken YAML, invalid paths, corrupt files |
| Missing dependencies | Required tool not available |
| Ambiguous intent | Prompt could mean multiple things |
| Scale extremes | Very large files, very small inputs |
| Permission issues | Read-only directories, missing write access |
| Conflicting instructions | User says X but skill assumes Y |

```
edge_score = (graceful_handling_count / total_edge_cases) × 100
```

## 5. Token Efficiency (weight: 0.10)

Measures instruction density — maximum capability per token consumed.

**Red flags:**
- Repeated instructions (same thing said 3 different ways)
- Verbose preambles before actionable content
- Long explanations where a short example would suffice
- Unnecessary hedging
- Instructions that Claude already knows

**Green flags:**
- Concise imperative instructions
- Examples that replace explanations
- Progressive disclosure (details in references, not SKILL.md)
- WHY-based reasoning (explains rationale, not just rules)

## 6. Composability (weight: 0.10)

Measures how well the skill plays with others.

| Check | Points |
|-------|--------|
| No global state pollution | 20 |
| Clear input/output contract | 20 |
| No conflicting tool assumptions | 20 |
| Explicit handoff points | 20 |
| No overlapping scope | 20 |

## Composite Score Calculation

```python
total = (
    structure     * 0.15 +
    triggers      * 0.25 +
    quality       * 0.25 +
    edges         * 0.15 +
    efficiency    * 0.10 +
    composability * 0.10
)
```

**Quality tiers:**
- 90+ Excellent — production-ready, community-shareable
- 80-89 Good — reliable for personal/team use
- 70-79 Adequate — works but has clear gaps
- 60-69 Needs work — functional but unreliable
- <60 Poor — significant issues, needs major revision
