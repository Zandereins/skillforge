# Skill Patterns & Anti-Patterns

Collected from analyzing 100+ Claude Code skills. Use these to identify
improvement opportunities during the SkillForge loop.

## High-Impact Patterns

### 1. Trigger Description Layering

Structure the description with WHAT → WHEN → SYNONYMS → BOUNDARIES.

```yaml
description: >
  Generate database migration scripts from schema changes.
  Use when the user mentions migrations, schema changes, database updates,
  ALTER TABLE, or asks to "update the database". Also triggers for
  "add a column", "change field type", "create index".
  Do NOT use for query optimization or database backups.
```

### 2. Example-Driven Instructions

Replace long explanations with input/output examples.

Bad:
```markdown
When generating commit messages, ensure they follow the conventional
commits specification. The type should be one of feat, fix, chore...
```

Good:
```markdown
## Commit message format
Follow conventional commits. Examples:

Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

### 3. Progressive Disclosure

Keep SKILL.md under 300 lines. Move deep content to references/.

### 4. Verification Commands

Include executable verification steps.

```markdown
After generating the config file:
1. Validate syntax: `yamllint .github/workflows/deploy.yml`
2. Dry run: `act -n -W .github/workflows/deploy.yml`
```

### 5. Explicit Scope Boundaries

State what the skill does NOT do.

## Anti-Patterns to Fix

### Anti-Pattern 1: The Kitchen Sink
**Symptom:** SKILL.md is 1000+ lines with everything inline.
**Fix:** Extract to references/. Keep SKILL.md as an index + core workflow.

### Anti-Pattern 2: The Invisible Skill
**Symptom:** Skill exists but never triggers because description is too narrow.
**Fix:** Add synonyms, rephrase with user language, include concrete trigger phrases.

### Anti-Pattern 3: The Chatty Instructor
**Symptom:** Instructions explain things Claude already knows.
**Fix:** Delete. Focus instructions on what's UNIQUE to this skill.

### Anti-Pattern 4: The Hedger
**Symptom:** Instructions full of "might", "could", "consider", "possibly".
**Fix:** Use imperative voice with WHY-based reasoning.

### Anti-Pattern 5: Missing Failure Mode
**Symptom:** Skill only describes the happy path. No guidance for errors.
**Fix:** Add an explicit "When things go wrong" section.

### Anti-Pattern 6: The Duplicate
**Symptom:** Skill overlaps significantly with another skill's scope.
**Fix:** Either merge, or add explicit boundary markers.

### Anti-Pattern 7: No Examples
**Symptom:** Lots of rules, zero examples.
**Fix:** Add at least 2-3 input/output examples.

## Improvement Priority Matrix

| Issue | Impact | Effort | Priority |
|-------|--------|--------|----------|
| Missing/weak description | HIGH | LOW | Fix FIRST |
| No examples | HIGH | MEDIUM | Fix SECOND |
| Kitchen sink (too long) | MEDIUM | MEDIUM | Fix THIRD |
| Missing edge cases | MEDIUM | LOW | Fix FOURTH |
| Chatty/hedging language | LOW | LOW | Fix when convenient |
| Missing references | LOW | MEDIUM | Fix for large skills |

## Skill Quality Checklist

- [ ] Has YAML frontmatter with name + description
- [ ] Description includes trigger phrases and boundaries
- [ ] SKILL.md is under 500 lines
- [ ] At least 2 input/output examples
- [ ] Uses imperative voice
- [ ] Has error handling guidance
- [ ] References exist for deep content
- [ ] No overlap with existing skills
- [ ] Verification steps are executable
- [ ] Works in both Claude Code and Claude.ai contexts
