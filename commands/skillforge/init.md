---
name: skillforge:init
description: >
  Initialize SkillForge tracking for a skill. Auto-generates an eval suite
  by analyzing the SKILL.md, establishes a baseline benchmark, and sets up
  the improvement tracking system. This is the first step before running
  /skillforge to start the improvement loop.
---

# /skillforge:init

Initialize SkillForge improvement tracking for a skill.

## Instructions

1. Ask the user for two pieces of information:
   - **Target skill path**: "What skill do you want to improve? Give me the path to its SKILL.md"
   - **Improvement goal**: "What's the main improvement goal? (e.g., 'better trigger accuracy', 'reduce token usage', 'handle edge cases better')"

2. Validate the path and read the SKILL.md file completely.

3. Auto-generate an eval suite by analyzing the SKILL.md:

   a. **Parse the skill description and scope**:
      - Extract the main purpose from frontmatter + first section
      - Identify what the skill does (positive case) and what it doesn't do (negative case)
      - List any explicit scope boundaries or "when not to use" statements

   b. **Generate 5 positive triggers** (when the skill SHOULD activate):
      - Create realistic user prompts that describe problems the skill solves
      - Each should be 1-2 sentences, specific enough to be unambiguous
      - Base these on the skill's stated purpose and scope

   c. **Generate 3 negative triggers** (when the skill SHOULD NOT activate):
      - Create prompts that sound similar but fall outside the skill's scope
      - These test whether the skill incorrectly triggers on adjacent domains
      - Base these on the skill's stated boundaries

   d. **Create 2-3 test cases with basic assertions**:
      - One happy path: "User gives clear input matching the skill's purpose"
        * Assertions: output contains key terms, follows expected format, no TODOs
      - One with minimal input: "User provides just enough info to trigger"
        * Assertions: skill asks clarifying questions OR proceeds with defaults
      - Optional variation: "User provides rich context"
        * Assertions: output is more detailed, all context is acknowledged

   e. **Create 2 edge cases**:
      - Missing/unclear input: "Skill should ask for clarification or state assumptions"
        * Assertion: response contains a question mark or clarifying statement
      - Partial success: "Skill handles when it can only partially solve the problem"
        * Assertion: response explains what it could/couldn't do and why

4. Save the generated eval suite as JSON:
   ```bash
   python3 scripts/init-skill.py \
     /path/to/SKILL.md \
     --goal "USER'S IMPROVEMENT GOAL" \
     --output /path/to/skill/eval-suite.json
   ```

5. Run the baseline benchmark using the new eval suite:
   ```bash
   python3 scripts/score-skill.py \
     /path/to/SKILL.md \
     --eval-suite /path/to/skill/eval-suite.json \
     --json > /tmp/baseline-score.json
   ```

6. Create the skillforge-results.jsonl file and record experiment #0:
   ```bash
   echo '{"exp": 0, "timestamp": "ISO-8601", "trigger": "init", "composite_score": XX, "pass_rate": X/Y, "scores": {...}}' \
     > /path/to/skill/skillforge-results.jsonl
   ```

7. Create the version history directory:
   ```bash
   mkdir -p /path/to/skill/skillforge-history/
   ```

8. Save a copy of the baseline SKILL.md:
   ```bash
   cp /path/to/SKILL.md /path/to/skill/skillforge-history/exp-000-baseline.md
   ```

9. Present the initialization summary:

   ```
   === SkillForge Initialized ===
   Skill: [skill-name]
   Goal: [user's improvement goal]

   Baseline composite: XX/100 (N/6 dimensions measured)
   Eval suite: M positive triggers, N negative triggers, P test cases, Q edge cases
   Pass rate: X/Y assertions passing

   Setup complete:
   ✓ Eval suite: eval-suite.json
   ✓ Results log: skillforge-results.jsonl
   ✓ History: skillforge-history/exp-000-baseline.md

   Ready to grind. Run /skillforge to start the loop.
   ```

## Notes

- The eval suite is the foundation for improvement tracking. Good triggers and test cases will guide the optimization loop.
- Baseline composite score is a weighted average of all 6 dimensions: structure, triggers, quality, edges, efficiency, and composability.
- Pass rate reflects how many eval assertions pass in the current version vs. the total.
- The skillforge-history directory preserves snapshots of the SKILL.md at each iteration, allowing you to compare versions and revert if needed.
