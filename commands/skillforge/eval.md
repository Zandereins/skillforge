---
name: skillforge:eval
description: >
  Run the evaluation suite against a skill and report results.
  Tests trigger accuracy, output quality, and edge-case handling.
  Use to check skill quality without starting the improvement loop.
---

# /skillforge:eval

Run evaluations against the target skill.

## Instructions

1. Identify the target skill and its eval suite.
   Look for `skillforge-evals.json` in the skill directory.
   If it doesn't exist, offer to generate one from the template.

2. For **trigger evaluation**:
   - Read each trigger test case from the eval suite
   - Analyze whether the skill's description would match the prompt
   - Score: correct matches / total triggers × 100

3. For **output quality evaluation**:
   - For each test case, follow the skill's instructions to complete the task
   - Check each assertion against the output
   - Score: passing assertions / total assertions × 100

4. For **edge-case evaluation**:
   - For each edge case, follow the skill's instructions
   - Check if the response is graceful (no crash, clear guidance)
   - Score: graceful responses / total edge cases × 100

5. Present results:
   ```
   === SkillForge Eval Results ===
   Skill: [name]

   Trigger accuracy:  XX% (Y/Z correct)
   Output quality:    XX% (Y/Z assertions pass)
   Edge coverage:     XX% (Y/Z handled gracefully)

   Failed triggers:
   - [prompt] — expected [trigger/no-trigger], got [opposite]

   Failed assertions:
   - [test-case-id] — [assertion description]

   Failed edge cases:
   - [edge-case-id] — [what went wrong]
   ```

6. Save results to `skillforge-eval-results.json` in the skill directory.
