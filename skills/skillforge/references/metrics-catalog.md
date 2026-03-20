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

Measures information density — how much actionable signal the skill delivers
relative to its total size.

**How `score-skill.py` measures this (automated):**

The scorer computes a signal-to-noise density ratio:
- **Signal:** actionable instructions (imperative verbs), real examples,
  WHY-based reasoning, verification commands
- **Noise:** hedging language, filler phrases ("it should be noted that"),
  instructions Claude already knows ("always test your code")
- **Density** = (signal - noise) / total words * 100

This approach rewards **fewer words with more punch** rather than the old
formula which rewarded adding headers and code blocks.

**Red flags (noise indicators):**
- Repeated instructions (same thing said 3 different ways)
- Verbose preambles before actionable content
- Filler phrases: "it is important to note that", "as mentioned above"
- Hedging: "you might want to consider possibly"
- Instructions Claude already knows: "make sure to save your file"

**Green flags (signal indicators):**
- Concise imperative instructions
- Real input/output examples
- WHY-based reasoning (explains rationale, not just rules)
- Executable verification commands
- Explicit scope boundaries

## 6. Composability (weight: 0.10)

Measures how well the skill plays with others.

**How `score-skill.py` measures this (automated, static analysis):**

| Check | Points | What the scorer looks for |
|-------|--------|--------------------------|
| Clear scope boundaries | 20 | Both "use when" AND "do not use for" present |
| No global state assumptions | 20 | No hard-coded global paths, system-wide config |
| Clear input/output contract | 20 | Specifies what input is expected and what output is produced |
| Explicit handoff points | 20 | References to other skills, "then use X", "suggest using Y" |
| No conflicting tool assumptions | 20 | No hard tool requirements without fallbacks |

## 7. Clarity (weight: 0.00 default, 0.05 when --clarity)

Measures instruction clarity — contradictions, ambiguity, and completeness.
Opt-in dimension that doesn't affect the default composite score.

**Automated checks (via `scripts/score-skill.py --clarity`):**

| Check | Points | Criteria |
|-------|--------|----------|
| No contradictions | 30 | No "always X" vs "never X" on same topic |
| No vague references | 25 | "the file" has clear antecedent within 3 lines |
| No ambiguous pronouns | 20 | Sentences don't start with "It/This/That" after empty lines |
| Complete instructions | 25 | Every "Run X" has a concrete command or path |

**Score ranges:**
- 90-100: Crystal clear instructions, no ambiguity
- 70-89: Minor clarity issues, mostly readable
- 50-69: Several vague references or ambiguous sections
- 0-49: Contradictory or incomplete instructions

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

Dimensions that return `-1` (unmeasured) are excluded and the remaining
weights are renormalized. The scorer reports **weight coverage** — the
fraction of total weight actually measured — and warns when coverage is
below 50%.

**Quality tiers (with sufficient coverage):**
- 90+ Excellent — production-ready, community-shareable
- 80-89 Good — reliable for personal/team use
- 70-79 Adequate — works but has clear gaps
- 60-69 Needs work — functional but unreliable
- <60 Poor — significant issues, needs major revision

**Currently automated:** Structure, Triggers (with eval suite), Efficiency,
Composability. **Requires eval loop:** Output Quality, Edge Coverage.
