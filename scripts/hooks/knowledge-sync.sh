#!/usr/bin/env bash
# knowledge-sync — Claude Code PostToolUse hook (Write|Edit|MultiEdit|
# NotebookEdit): after any edit, refresh the repo's code knowledge in the
# background, never blocking the session:
#   codegraph sync -q <root>   when a .codegraph/ index exists (incremental;
#                              safe alongside the MCP daemon's writer lock)
#   graphify update <root>     when graphify-out/graph.json exists (AST-only,
#                              no LLM; 600s cap — the same budget graphify's
#                              own post-commit hook uses)
# Debounce: 2s settle window, then per-repo flock so a burst of edits
# coalesces into one sync; a sync blocked by a still-running previous one is
# picked up by the next edit (eventual consistency per repo).
# ponytail: per-repo flock file (~/.cache-style hash of the repo root); a
# shared per-repo daemon/queue is the upgrade if cross-repo bursts become hot.
set -u
input=$(cat)
c=$(printf '%s' "$input" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("cwd") or "")
except Exception: pass' 2>/dev/null)
[ -n "$c" ] && [ -d "$c" ] || exit 0
root=$(git -C "$c" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -z "$root" ] && exit 0
(
  nohup flock -n "/tmp/knowledge-sync-$(printf '%s' "$root" | md5sum | cut -d' ' -f1).lock" \
    bash -c 'd="$1"; sleep 2; if [ -d "$d/.codegraph" ]; then timeout 120 codegraph sync -q "$d" >/dev/null 2>&1; fi; if [ -f "$d/graphify-out/graph.json" ]; then timeout 600 graphify update "$d" >/dev/null 2>&1; fi' \
    bash "$root" >/dev/null 2>&1 &
) 2>/dev/null
exit 0
