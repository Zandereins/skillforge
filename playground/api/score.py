"""Schliff scoring API endpoint for the web playground.

Accepts skill markdown content via POST, runs the schliff scoring engine,
and returns the full score result as JSON.

Rate limiting: handled by Vercel WAF in production — not implemented here.
"""

import json
import os
import re
import tempfile
from http.server import BaseHTTPRequestHandler

MAX_CONTENT_SIZE = 500 * 1024  # 500 KB

# Only alphanumeric, hyphens, underscores, dots — no path separators
_SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+\.md$")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}


def _score_to_grade(score: float) -> str:
    if score >= 95:
        return "S"
    if score >= 85:
        return "A"
    if score >= 75:
        return "B"
    if score >= 65:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def _run_scoring(content: str, filename: str) -> dict:
    """Write content to a temp file, run schliff scoring, return result dict."""
    from skills.schliff.scripts.shared import build_scores
    from skills.schliff.scripts.scoring.composite import compute_composite

    tmp_dir = tempfile.mkdtemp()
    # Use only the basename to prevent path traversal
    safe_name = os.path.basename(filename)
    skill_path = os.path.join(tmp_dir, safe_name)

    try:
        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(content)

        scores = build_scores(skill_path, eval_suite=None, include_runtime=False)
        composite = compute_composite(scores)

        grade = _score_to_grade(composite["score"])

        return {
            "composite_score": composite["score"],
            "grade": grade,
            "dimensions": {dim: scores[dim]["score"] for dim in scores},
            "warnings": composite.get("warnings", []),
            "measured_dimensions": composite.get("measured_dimensions", 0),
            "total_dimensions": composite.get("total_dimensions", 0),
        }
    finally:
        try:
            os.unlink(skill_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, body: dict):
        self.send_response(status)
        for key, value in CORS_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        for key, value in CORS_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()

    def do_GET(self):
        """Return API info for browser visitors."""
        self._send_json(200, {
            "service": "schliff-playground",
            "usage": "POST /api/score with {\"content\": \"...\", \"filename\": \"SKILL.md\"}",
            "max_size_kb": MAX_CONTENT_SIZE // 1024,
        })

    def do_POST(self):
        """Score a skill file and return the result."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_json(400, {"error": "Invalid Content-Length header"})
            return

        if content_length > MAX_CONTENT_SIZE:
            self._send_json(413, {
                "error": "Content too large",
                "detail": f"Maximum size is {MAX_CONTENT_SIZE // 1024} KB",
            })
            return

        if content_length == 0:
            self._send_json(400, {"error": "Empty request body"})
            return

        try:
            raw_body = self.rfile.read(content_length)
            body = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_json(400, {"error": "Invalid JSON", "detail": str(exc)})
            return

        if not isinstance(body, dict):
            self._send_json(400, {"error": "Request body must be a JSON object"})
            return

        content = body.get("content")
        filename = body.get("filename", "SKILL.md")

        if not content or not isinstance(content, str):
            self._send_json(400, {"error": "Missing or invalid 'content' field"})
            return

        if not _SAFE_FILENAME_RE.match(filename):
            self._send_json(400, {
                "error": "Invalid filename",
                "detail": "Must match [a-zA-Z0-9_-]+.md (no path separators)",
            })
            return

        try:
            result = _run_scoring(content, filename)
            self._send_json(200, result)
        except Exception as exc:
            self._send_json(500, {
                "error": "Scoring failed",
                "detail": type(exc).__name__,
            })
