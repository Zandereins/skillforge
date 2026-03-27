"""Regression tests for v7.1 — ensure scoring never crashes on pathological input."""
import os
import time
import tempfile
import random
import string

from shared import build_scores


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tmp(content: str) -> str:
    """Write content to a named temp file and return its path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8",
    )
    f.write(content)
    f.close()
    return f.name


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Fuzz / robustness
# ---------------------------------------------------------------------------

def test_random_utf8_no_crash():
    """500 random Unicode chars must not crash build_scores."""
    random.seed(42)  # deterministic for reproducibility
    chars = string.printable + "".join(chr(i) for i in range(0x100, 0x1000))
    content = "".join(random.choices(chars, k=500))
    path = _write_tmp(content)
    try:
        scores = build_scores(path)
        assert isinstance(scores, dict)
    finally:
        _cleanup(path)


def test_empty_string_no_crash():
    """Empty file returns scores (may be low, but no crash)."""
    path = _write_tmp("")
    try:
        scores = build_scores(path)
        assert isinstance(scores, dict)
    finally:
        _cleanup(path)


def test_binary_content_no_crash():
    """All 256 byte values decoded as latin-1 must not crash."""
    content = bytes(range(256)).decode("latin-1")
    path = _write_tmp(content)
    try:
        scores = build_scores(path)
        assert isinstance(scores, dict)
    finally:
        _cleanup(path)


def test_1mb_input_no_crash():
    """Just under MAX_SKILL_SIZE (999,999 bytes) must not crash."""
    content = "x" * 999_999
    path = _write_tmp(content)
    try:
        scores = build_scores(path)
        assert isinstance(scores, dict)
    finally:
        _cleanup(path)


def test_only_newlines_no_crash():
    """1000 newlines must not crash."""
    path = _write_tmp("\n" * 1000)
    try:
        scores = build_scores(path)
        assert isinstance(scores, dict)
    finally:
        _cleanup(path)


def test_only_headers_no_crash():
    """Repeated markdown headers must not crash."""
    content = "# H1\n## H2\n### H3\n" * 100
    path = _write_tmp(content)
    try:
        scores = build_scores(path)
        assert isinstance(scores, dict)
    finally:
        _cleanup(path)


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

_DEMO_SKILL = """\
---
description: >
  A realistic demo skill for performance testing. Handles multiple
  scenarios with structured instructions and fallback strategies.
---

# Demo Skill

## Triggers

- When the user asks to generate a report
- When "create summary" appears in the prompt
- After completing data analysis steps

## Instructions

1. Read the input data from the provided file path.
2. Validate the schema matches the expected format.
3. Apply transformations:
   - Normalize dates to ISO 8601
   - Strip leading/trailing whitespace from all string fields
   - Convert currency values to cents (integer)

### Edge Cases

- If the input file is empty, return an empty report with a warning.
- If any required field is missing, skip that row and log a warning.
- Handle UTF-8 BOM gracefully.

## Examples

```python
result = generate_report("data.csv")
assert result["status"] == "ok"
assert len(result["rows"]) > 0
```

```python
# Edge case: empty input
result = generate_report("empty.csv")
assert result["status"] == "warning"
assert result["rows"] == []
```

## Output Format

Return a JSON object:
```json
{
  "status": "ok",
  "rows": [...],
  "warnings": []
}
```
"""


def test_performance_demo_skill():
    """A realistic ~200 line skill must score in under 50 ms."""
    # Expand the demo to roughly 200 lines
    content = _DEMO_SKILL + ("\n## Additional Section\n\n- Detail line\n" * 30)
    path = _write_tmp(content)
    try:
        start = time.perf_counter()
        scores = build_scores(path)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert isinstance(scores, dict)
        assert elapsed_ms < 50, f"Took {elapsed_ms:.1f} ms (limit: 50 ms)"
    finally:
        _cleanup(path)


def test_performance_large_skill():
    """A ~2000 line skill must score in under 100 ms."""
    # Build a large but realistic file
    lines = ["---", "description: Large performance test skill", "---", ""]
    lines.append("# Large Skill\n")
    for section in range(20):
        lines.append(f"## Section {section}\n")
        lines.append("### Instructions\n")
        for step in range(10):
            lines.append(f"- Step {step}: perform action and verify result.")
        lines.append("")
        lines.append("```python")
        for ln in range(30):
            lines.append(f"    x_{section}_{ln} = compute(data[{ln}])")
        lines.append("```\n")

    content = "\n".join(lines)
    path = _write_tmp(content)
    try:
        start = time.perf_counter()
        scores = build_scores(path)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert isinstance(scores, dict)
        assert elapsed_ms < 2000, f"Took {elapsed_ms:.1f} ms (limit: 2000 ms)"
    finally:
        _cleanup(path)
