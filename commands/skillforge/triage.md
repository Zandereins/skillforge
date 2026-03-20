---
name: triage
description: Cluster and triage logged failures, auto-generate eval cases and SKILL.md fixes
---

# /skillforge:triage — Failure Triage

Analyze `.skillforge/failures.jsonl`, cluster failures by pattern, and propose targeted fixes.

## Steps

1. Read `.skillforge/failures.jsonl` from the current project
2. Cluster failures by `skill` + `failure_type` pattern
3. For assertion failures: auto-generate eval-suite.json entries, run `text-gradient.py`
4. For runtime failures: identify failed test cases, propose SKILL.md edits
5. Present prioritized action plan
6. On user confirm: apply top-priority fixes, run single targeted improvement iteration
