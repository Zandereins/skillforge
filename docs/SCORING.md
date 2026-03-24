# Schliff Scoring System

How Schliff measures skill quality — and what the numbers actually mean.

---

## Two-Tier Model: Structural vs Runtime

Schliff scoring operates on two tiers:

**Structural (default)** — Static analysis of the skill file and eval suite. Measures file organization, keyword coverage, assertion breadth, and information density. Runs instantly, requires no LLM invocation. This is a **lint score**, not a quality score. A skill with 99/100 structure can still fail at runtime.

**Runtime (opt-in)** — Invokes Claude with test prompts from the eval suite and checks `response_*` assertions against actual output. This is the true quality gate. Enable with `--runtime` or run `/schliff:eval` with runtime assertions. Requires `claude` CLI.

When runtime data is available, the composite score blends both tiers. When it is not, the score is purely structural and labeled as such.

---

## The 7 Dimensions

| Dimension | Weight | What It Measures | What It Does NOT Measure |
|-----------|--------|-----------------|-------------------------|
| **Structure** | 15% | Frontmatter (name, description), headers, examples, progressive disclosure, file length, dead content (TODO/FIXME), referenced file existence | Whether instructions are correct or effective |
| **Trigger Accuracy** | 20% | TF-IDF keyword overlap between skill description and eval suite prompts, with stemming, synonym expansion, domain signal detection, and negation boundary handling | Actual Claude triggering behavior — that requires runtime evaluation |
| **Eval Coverage (Quality)** | 20% | Assertion breadth (type diversity: contains, pattern, excludes, format), feature coverage (analyze, improve, report), assertion descriptions, instruction-assertion coherence | Whether following the skill produces correct output |
| **Edge Coverage** | 15% | Edge case definitions in eval suite, category diversity (minimal input, invalid path, scale extreme, malformed input, missing deps, unicode), expected behaviors, edge assertions | Whether the skill handles edge cases correctly at runtime |
| **Token Efficiency** | 10% | Information density (signal-to-noise ratio), actionable instructions, real examples, WHY-based reasoning, verification commands vs hedging, filler phrases, obvious instructions | Whether the content is actually useful to Claude |
| **Composability** | 10% | 10 sub-checks: scope boundaries, global state, I/O contracts, handoff points, tool flexibility, error behavior, idempotency, dependency declarations, namespace isolation, version compatibility | Whether the skill works correctly alongside other skills |
| **Clarity** | 5% *(default)* | Contradictions (always X vs never X), vague references ("the file" without antecedent), ambiguous pronouns (It/This/That without referent), instruction completeness (every "Run X" has a concrete command). Opt-out via `--no-clarity`. | Whether instructions are clear to Claude in practice |
| **Runtime** *(opt-in)* | 10% | **Actual Claude behavior** — invokes Claude with test prompts, checks `response_contains`, `response_matches`, `response_excludes` assertions against real output | — |

---

## Grade Thresholds

| Grade | Threshold | Meaning |
|-------|-----------|---------|
| **S** | >= 95 | Exceptional — near-perfect on measured dimensions |
| **A** | >= 85 | Strong — minor polish opportunities remain |
| **B** | >= 75 | Good — clear improvement paths exist |
| **C** | >= 65 | Adequate — significant gaps in multiple dimensions |
| **D** | >= 50 | Weak — fundamental issues need attention |
| **F** | < 50 | Failing — major structural problems |

Grades apply to both the composite score and each individual dimension. Dashboard and reports show color-coded grade badges.

---

## Composite Score Calculation

The composite score is a **weighted average of all measured dimensions**, excluding any dimension that returns `-1` (not applicable / not measured).

```
composite = sum(score[dim] * weight[dim] for dim in measured) / sum(weight[dim] for dim in measured)
```

Key behaviors:

1. **Skip unmeasured dimensions** — If a dimension returns `-1` (e.g., runtime not enabled, no eval suite), its weight is excluded from the denominator. The remaining weights are renormalized.
2. **Weight coverage** — The scorer reports how many dimensions were actually measured and what fraction of total weight they represent. Low coverage triggers a warning.
3. **Confidence indicator** — When only 2 or fewer dimensions are measured, the score is flagged as unreliable.

### Clarity Dimension (Default)

Clarity is enabled by default since v6.0. It gets a weight of `0.05` (5%). The other dimension weights are scaled down proportionally so the total still sums to 1.0. Opt-out with `--no-clarity`.

### Coherence Bonus

The coherence check cross-references imperative instructions in the skill body against assertion values in the eval suite's test cases. It computes topic overlap using stemmed keywords. The result is a bonus of 0–10 points added to the Quality dimension score (capped at 100).

This catches disconnects between what a skill instructs and what the eval suite actually tests.

---

## Weight Defaults

```
structure:      0.15  (15%)
triggers:       0.20  (20%)
quality:        0.20  (20%)
edges:          0.15  (15%)
efficiency:     0.10  (10%)
composability:  0.10  (10%)
runtime:        0.10  (10%)  — only counted when enabled
```

---

## Auto-Calibration from Runtime Data

When runtime evaluation data exists, Schliff can auto-calibrate weights based on which dimensions correlate most with runtime success.

Calibrated weights are stored at `~/.schliff/meta/calibrated-weights.json`. The loader validates that all values are numeric before applying them. Calibrated weights take second priority — they are used when no custom weights are provided via `--weights`.

Priority order:
1. `--weights` CLI flag (highest)
2. `~/.schliff/meta/calibrated-weights.json` (auto-calibrated)
3. Built-in defaults (lowest)

---

## Weight Override Syntax

Override dimension weights via the `--weights` flag:

```bash
python score-skill.py SKILL.md --weights "triggers=0.4,structure=0.3"
```

- Key-value pairs separated by commas
- Values are normalized to sum to 1.0 automatically
- Only specified dimensions are included — omitted dimensions get zero weight
- Invalid values cause an immediate error with a clear message

Examples:

```bash
# Focus on trigger accuracy and structure only
--weights "triggers=0.6,structure=0.4"

# Equal weight across all dimensions
--weights "structure=1,triggers=1,quality=1,edges=1,efficiency=1,composability=1"

# Heavy runtime focus
--weights "runtime=0.5,triggers=0.3,quality=0.2"
```

---

## Dimension Details

### Structure (15%)

Checks file organization via inline Python analysis:

- Frontmatter presence and fields (name, description): 30 pts
- File length (<=500 lines ideal): 10 pts
- Real examples (input/output pairs, code blocks): 10 pts
- Headers (>=3 sections): 10 pts
- Progressive disclosure (references dir or short file): 15 pts
- Imperative voice (no hedging language): 5 pts
- Referenced files exist: 10 pts
- No dead content (TODO/FIXME/placeholder, empty sections): 10 pts

### Trigger Accuracy (20%)

Uses TF-IDF-inspired scoring instead of naive word overlap:

1. Extracts meaningful terms (4+ chars, stopwords removed)
2. Applies suffix-stripping stemmer for morphological variants
3. Expands via synonym table for non-morphological matches
4. Weights rare terms higher via IDF (terms appearing in fewer triggers are more discriminative)
5. Applies domain signal multiplier (skill context vs generic code)
6. Handles negation boundaries from description ("do NOT use for X")
7. Penalizes creation patterns ("from scratch", "brand new") as anti-signals for improvement tools

### Eval Coverage / Quality (20%)

Static analysis of test case quality:

- 3+ well-formed test cases (type + value present): 30 pts
- Multiple assertion types covered (contains, pattern, excludes, format): 25 pts
- Different skill features tested (analyze, improve, report): 25 pts
- All assertions have descriptions: 20 pts
- Coherence bonus: instruction-assertion topic overlap: up to +10 pts

### Edge Coverage (15%)

- 5+ edge cases defined: 30 pts
- Multiple categories covered (minimal, invalid, scale, malformed, missing, unicode): 30 pts
- All edge cases have expected_behavior: 20 pts
- All edge cases have assertions: 20 pts

### Token Efficiency (10%)

Measures information density as signal per 100 words:

- **Signal**: actionable instructions (x3), real examples (x5), WHY-reasoning (x2), verification commands (x2)
- **Noise**: hedging language (x3), filler phrases (x2), obvious instructions (x2)
- Density mapped via sqrt curve: 0→40, 5→79, 10→95 (no step-function cliffs)
- Actionable lines are deduplicated (near-duplicate instructions count once)
- Penalties for excessive length without signal, too much whitespace
- Bonuses for scope boundaries (+3) and conciseness under 300 lines (+5)

### Composability (10%)

Ten sub-checks at 10 pts each:

1. Clear scope boundaries (positive + negative triggers)
2. No global state assumptions
3. Input/output contract clarity
4. Explicit handoff points to other skills
5. No hard tool requirements without fallbacks
6. Error/failure behavior described
7. Idempotency/safety statement
8. Dependency declarations
9. Namespace/prefix isolation
10. Version/compatibility notes

### Clarity (5%, default)

Starts at 100 pts, deducts for issues:

- Contradictions (always X vs never X): up to -30 pts
- Vague references without antecedent: up to -25 pts
- Ambiguous pronouns at sentence start: up to -20 pts
- Incomplete instructions (Run X without concrete command): up to -25 pts

Code blocks are stripped before analysis to avoid false positives from examples.

### Runtime (15%, opt-in)

- Runs up to 3 test cases with `response_*` assertions
- Invokes `claude -p` with skill content prepended to test prompt
- Checks `response_contains`, `response_matches`, `response_excludes`
- Score = pass rate as percentage
- Gracefully degrades to `-1` (skipped) if `claude` CLI is unavailable
