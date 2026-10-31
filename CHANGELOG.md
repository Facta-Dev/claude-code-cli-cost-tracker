# Changelog

Format: Keep a Changelog. The price sheet carries its own `as_of` inside
prices.json — price changes are sheet edits, not code releases.

## [Unreleased]

- cccost reports CLI: `daily` / `weekly` / `monthly` / `session` / `report`,
  `--list-repos`, `--json`, `--last N`, gatekept by the `--repo` guardrail
- `/cccost` slash command (`commands/cccost.md`)
- `cccost/` package extracted: `billing` (single pricing seam, resolver fix
  for `:cloud`/alias/`[1m]` compounds), `transcript` (shape knowledge), 
  `session_state` (status line incremental state),
  `analysis` (shared pipeline), `report` (byte-compat text surface)

## [0.1.0] — 2026-10-30

- Initial public version: `statusline.py` (self-billing live meter for
  Ollama Cloud-backed Claude Code), `analyze-history.py` (history baseline:
  cost-per-turn curve, cache hit rate, spend by repo), date-stamped
  `prices.json` (Ollama Cloud + first-party Claude rates), 13 tests
  (stdlib runner, no dependencies)