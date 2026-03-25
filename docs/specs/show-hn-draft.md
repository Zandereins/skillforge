# Show HN Draft

Status: DRAFT
Created: 2026-03-25

---

## Title

Show HN: Schliff — a linter for Claude Code skills (Python, zero deps)

## URL

https://github.com/Zandereins/schliff

## First Comment (maker story)

Claude Code skills degrade silently. A skill that worked last month misfires today — triggers overlap, instructions contradict, edge cases slip through. You only notice when production breaks. I built Schliff to catch that statically, before your users do.

Skills are markdown instruction files that tell AI coding agents how to behave — like .eslintrc for AI. Schliff is a deterministic linter for these files. No LLM needed — it runs pure static analysis across 7 dimensions (structure, triggers, quality, edges, efficiency, composability, clarity) and outputs a weighted score from 0-100 with a letter grade. Same input, same output, every time. Python 3.9+ stdlib only, zero dependencies. The structural score measures file organization; `--runtime` scoring validates against actual Claude behavior for teams that need that.

What I think is novel: anti-gaming detection. Skills are text files, so it's tempting to stuff keywords or pad sections to inflate scores. Schliff catches all 6 gaming patterns in our benchmark suite — keyword stuffing, empty headers, copy-paste examples, contradictory instructions, bloated preambles, missing scope boundaries.

An external user ran Schliff on agent-review-panel (a multi-agent adversarial code review tool). Their SKILL.md went from 64 [D] to 85.6 [A] across 3 improvement rounds, while shrinking from 1,331 to 340 lines — 75% fewer tokens via references/ extraction. They A/B tested the optimized skill on a 1,132-line document: identical verdict, and the shorter version actually caught 2 additional findings.

Schliff scores itself at 99.0/100 [S]. Same engine, no exceptions. 500+ tests, MIT licensed. Try it: `pip install schliff && schliff demo` — or if you already have Claude Code skills, `schliff doctor` will scan them all and show you what's actually going on.

I'd love feedback on: scoring methodology (are the 7 dimensions right? are the weights reasonable?), dimensions I'm missing, and whether this generalizes beyond Claude Code to other agent instruction formats.

Source: https://github.com/Zandereins/schliff
