# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Schliff, please report it responsibly:

1. **Do not** open a public issue
2. Open a [private security advisory on GitHub](https://github.com/Zandereins/schliff/security/advisories/new)
3. Include: description, reproduction steps, potential impact

We will acknowledge receipt within 48 hours and provide a fix timeline within 7 days.

## Scope

Schliff processes skill files (SKILL.md) and eval suites (JSON). Security considerations:

- **File size limits**: Skill files are capped at 1 MB to prevent resource exhaustion
- **Path traversal**: Reference path resolution blocks `..` sequences
- **Regex safety**: Runtime evaluator uses timeout-protected regex matching
- **No network access**: All scoring is local — no data leaves your machine
- **No code execution**: Schliff reads and scores files, it does not execute skill content

## Supported Versions

| Version | Supported |
|---------|-----------|
| 3.x     | Yes       |
| 2.x     | Security fixes only |
| 1.x     | No        |
