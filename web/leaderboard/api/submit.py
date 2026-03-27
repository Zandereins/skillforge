from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

MAX_BODY_BYTES = 64 * 1024  # 64 KB

VALID_GRADES = {"S", "A", "B", "C", "D"}
VALID_FORMATS = {"SKILL.md", ".cursorrules", "CLAUDE.md", "AGENTS.md"}
VALID_DIMENSIONS = {
    "structure", "triggers", "quality", "edges", "efficiency",
    "composability", "clarity", "security", "sync",
}

# TODO: Replace with external storage (Vercel KV, Postgres, or Blob)
# for production. /tmp is ephemeral — data is lost between cold starts.
# This works for demo/prototype but NOT for persistent leaderboard data.
DATA_DIR = "/tmp/schliff-leaderboard"
DATA_PATH = os.path.join(DATA_DIR, "submissions.json")

# Seed data path (bundled with deployment, read-only)
SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "submissions.json")

# Control characters that could cause visual spoofing
_CONTROL_CHARS = set(range(0x00, 0x20)) - {0x0A, 0x0D, 0x09}  # allow \n \r \t
_BIDI_CHARS = {0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}


def _has_unsafe_chars(s: str) -> bool:
    """Reject strings with control or bidirectional override characters."""
    return any(ord(c) in _CONTROL_CHARS or ord(c) in _BIDI_CHARS for c in s)


def _validate(body):
    required = ["skill_name", "repo_url", "format", "composite", "grade", "dimensions", "version"]
    for field in required:
        if field not in body:
            return f"missing required field: {field}"

    skill_name = body["skill_name"]
    if not isinstance(skill_name, str) or not (1 <= len(skill_name) <= 200):
        return "skill_name must be a string between 1 and 200 characters"
    if _has_unsafe_chars(skill_name):
        return "skill_name contains invalid characters"

    repo_url = body["repo_url"]
    if not isinstance(repo_url, str):
        return "repo_url must be a valid GitHub repository URL"
    parsed_url = urlparse(repo_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "github.com":
        return "repo_url must be a valid GitHub repository URL"
    if len(parsed_url.path.strip("/").split("/")) < 2:
        return "repo_url must point to a specific repository"

    fmt = body["format"]
    if fmt not in VALID_FORMATS:
        return f"format must be one of: {', '.join(sorted(VALID_FORMATS))}"

    composite = body["composite"]
    if isinstance(composite, bool) or not isinstance(composite, (int, float)) or not (0 <= composite <= 100):
        return "composite must be a number between 0 and 100"

    grade = body["grade"]
    if grade not in VALID_GRADES:
        return f"grade must be one of: {', '.join(sorted(VALID_GRADES))}"

    dimensions = body["dimensions"]
    if not isinstance(dimensions, dict):
        return "dimensions must be an object"
    if set(dimensions.keys()) != VALID_DIMENSIONS:
        return f"dimensions must have exactly these keys: {', '.join(sorted(VALID_DIMENSIONS))}"
    for key, val in dimensions.items():
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not (0 <= val <= 100):
            return f"dimensions.{key} must be a number between 0 and 100"

    version = body["version"]
    if not isinstance(version, str) or not (1 <= len(version) <= 50):
        return "version must be a string between 1 and 50 characters"

    return None


def _load_submissions():
    """Load submissions from /tmp, seeding from bundled data if needed."""
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else []
    # Seed from bundled data on first cold start
    if os.path.exists(SEED_PATH):
        with open(SEED_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else []
    return []


def _save_submissions(entries):
    """Save submissions to /tmp (ephemeral)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    data = json.dumps(entries, indent=2, ensure_ascii=False)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        # CORS handled by vercel.json — no duplicate headers
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        # CORS handled by vercel.json
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length < 0 or content_length > MAX_BODY_BYTES:
                self._send_json(413, {"error": "request body too large"})
                return
            raw = self.rfile.read(content_length)
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._send_json(400, {"error": "invalid JSON body"})
            return

        if not isinstance(body, dict):
            self._send_json(400, {"error": "request body must be a JSON object"})
            return

        error = _validate(body)
        if error:
            self._send_json(400, {"error": error})
            return

        entry = {
            "skill_name": body["skill_name"],
            "repo_url": body["repo_url"],
            "format": body["format"],
            "composite": float(body["composite"]),
            "grade": body["grade"],
            "dimensions": {k: float(v) for k, v in body["dimensions"].items()},
            "version": body["version"],
            "submitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        try:
            entries = _load_submissions()

            # Dedup: update existing entry if repo_url + skill_name match.
            key_repo = entry["repo_url"]
            key_skill = entry["skill_name"]
            updated = False
            for i, existing in enumerate(entries):
                if existing.get("repo_url") == key_repo and existing.get("skill_name") == key_skill:
                    entries[i] = entry
                    updated = True
                    break
            if not updated:
                entries.append(entry)

            _save_submissions(entries)
        except Exception as exc:
            print(f"Storage error: {type(exc).__name__}: {exc}", file=sys.stderr)
            self._send_json(500, {"error": "internal storage error"})
            return

        self._send_json(200, {"ok": True, "updated": updated})
