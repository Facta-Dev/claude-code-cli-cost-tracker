# Changelog

Format: Keep a Changelog. The price sheet carries its own `as_of` inside
prices.json — price changes are sheet edits, not code releases.

## [Unreleased]

- Any-terminal session panel on Linux: `session_panel.py` stays clickable
  outside WezTerm — on X11 it raises the window that owns the clicked
  session's pty (tty -> pane shell -> process ancestry, `wmctrl` or `xdotool`;
  window-level, not pane-level, outside WezTerm). Terminator gets a docked
  layout for claude sessions — `install.sh` registers a `ccpanel` profile +
  layout (terminal left, panel right, iTerm2-style) and a `ccpanel` launcher
  that opens a session window (`-e claude` to start claude right away); plain
  terminator windows stay untouched.
  Unit-tested parsers + ancestry walk; live-verified with Terminator +
  xdotool on Xfce/X11.
- Linux per-session status: the unified hook keeps a live record per session
  (`CC_SESSIONS_DIR`) and, with `CC_TAB_TITLE=1`, sets the terminal tab title
  (`🟡 my-repo · working · $2.31`); `hooks/linux/session_panel.py` lists every
  running session and, inside WezTerm, jumps to the clicked one;
  `hooks/linux/wezterm.lua` + `ccterm` give every tab `claude` + the panel.
  `install.sh` copies `hooks/linux/` on Linux. See INSTALL §3d.
- `CLAUDE_CONFIG_DIR` is honored: `cccost` reads `$CLAUDE_CONFIG_DIR/projects`
  by default and `install.sh` installs into it (default `~/.claude` unchanged).
- Fix: a transcript symlink whose target no longer exists (or a directory named
  `*.jsonl`) no longer crashes `--list-repos` and every report.
- Claude fast mode per turn: usage speed exactly "fast" on a claude- model
  bills the `-fast` sheet row (opus-5-5/5/4-8); without one, base rates +
  a report note (fast_fallback). Ollama's numeric speed never counts.
- Haiku-tiered pricing is sheet-driven: per-model `"tiers"` key applies
  past a billed-input threshold; unnamed classes stay at the base row.
- `cccost merge DIR [DIR|CSV...] --out-dir DIR`: cross-machine export
  dedupe (session_id / session_id+turn_index, higher-cost wins), CSV-only
  plumbing — no transcripts, no --repo, view-only output.
- `cccost models`: per-model cost report (which model burns the budget)
- `--off-peak` now bills per turn by timestamp — weekends and weekdays
  outside 12:00–18:00 UTC; undated turns stay off-peak (understatement).
  First-party Claude rows unaffected.
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