# AZUL run-skill-generator NOTES (scratchpad)

Date: 2026-11-16
Platform: Windows 10 Pro, PowerShell 5.1, Node v26.13.1, npx 11.20.0, Playwright 1.65.1 (local)

## Existing state
- `.claude/skills/run-azul/` exists but is EMPTY (no SKILL.md, no driver).
- `tests/smoke.py`, `tests/test_isolation.py`, `tests/conftest.py` exist.
- `instance/tappy.db` exists (49KB) — but app.py uses `sqlite:///azul.db`, so
  tappy.db is a leftover from a different run/config. Not used by default.

## App shape
- Flask app, `python -m client.app` (or `run.ps1`).
- Requires SECRET_KEY env var unless TESTING.
- Templates extend `_base_azul.html`.