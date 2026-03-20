---
name: log-failure
description: Manually log a skill failure for later triage
---

# /skillforge:log-failure — Log a Failure

Record a skill failure to `.skillforge/failures.jsonl` for later triage.

## Steps

1. Ask the user: Which skill failed? What happened?
2. Create structured failure entry with timestamp, skill, failure_type, description
3. Append to `.skillforge/failures.jsonl` (create if needed)
4. Confirm the entry was logged
5. Suggest running `/skillforge:triage` when 3+ failures accumulate
