#!/usr/bin/env bash
# cost-sync — Claude Code Stop hook: persist this repo's per-model token sums.
#
# Runs after every response (Stop), beside knowledge-sync.sh, which refreshes
# the CodeGraph and Graphify indexes for the same repo. Billing reuses the
# claude-code-cli-cost-tracker package installed at ~/.claude (transcript is
# the source of truth; message.id dedupe; per-turn model pricing), so the
# numbers match `cccost models --repo <name>` — including advisor, subagent
# and Workflow turns, whose transcripts live under <session>/subagents/**.
#
# Output: <repo>/.claude/costs.json
#   models.<model> = {turns, input_tokens, output_tokens, cache_read_tokens,
#                     cache_write_tokens, total_tokens, cost_usd}  (repo sum)
#   sessions.<session-id>.models = the same shape for one session
#
# Fail-open: no cccost install, no transcript, unreadable state, any error ->
# exit 0 and the session continues. Local only (gitignored by configure-repo).
set -u
input=$(cat)
cwd=$(printf '%s' "$input" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("cwd") or "")
except Exception: pass' 2>/dev/null)
[ -n "$cwd" ] && [ -d "$cwd" ] || exit 0
root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -z "$root" ] && exit 0
CLAUDE_STOP_PAYLOAD="$input" python3 - "$root" <<'PY' || true
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
try:
    payload = json.loads(os.environ.get("CLAUDE_STOP_PAYLOAD") or "{}")
except Exception:
    sys.exit(0)

transcript = payload.get("transcript_path") or ""
session_id = payload.get("session_id") or (Path(transcript).stem if transcript else "")
main = Path(transcript) if transcript else None
if not session_id or main is None or not main.is_file():
    sys.exit(0)

sys.path.insert(0, os.path.expanduser("~/.claude"))
try:
    from cccost.analysis import load_prices
    from cccost.transcript import iter_turns
except Exception:
    sys.exit(0)

prices_path = Path(os.path.expanduser("~/.claude/prices.json"))
if not prices_path.is_file():
    sys.exit(0)
try:
    prices = load_prices(prices_path)
except SystemExit:
    sys.exit(0)

# The main transcript plus every subagent transcript under the session dir —
# rglob covers subagents/workflows/<wf>/agent-*.jsonl (Workflow agents).
files = [main]
subagents = main.parent / main.stem / "subagents"
if subagents.is_dir():
    files.extend(sorted(subagents.rglob("*.jsonl")))

FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")


def empty():
    return {"turns": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
            "total_tokens": 0, "cost_usd": 0.0}


models = {}
for path in files:
    try:
        turns = list(iter_turns(path))
    except Exception:
        continue
    for turn in turns:
        model = turn.get("model") or "?"
        entry = models.setdefault(model, empty())
        entry["turns"] += 1
        entry["input_tokens"] += turn["tokens"].get("input", 0)
        entry["output_tokens"] += turn["tokens"].get("output", 0)
        entry["cache_read_tokens"] += turn["tokens"].get("cache_read", 0)
        entry["cache_write_tokens"] += (
            turn["tokens"].get("cache_write_5m", 0) + turn["tokens"].get("cache_write_1h", 0)
        )
        entry["total_tokens"] = (
            entry["input_tokens"] + entry["output_tokens"]
            + entry["cache_read_tokens"] + entry["cache_write_tokens"]
        )
        try:
            cost = prices.cost(model, turn["tokens"], turn.get("timestamp"),
                               fast=bool(turn.get("fast")))
        except Exception:
            cost = None
        if cost is not None:
            entry["cost_usd"] += cost

if not models:
    sys.exit(0)

for entry in models.values():
    entry["cost_usd"] = round(entry["cost_usd"], 6)

out = root / ".claude" / "costs.json"
state = {}
if out.is_file():
    try:
        state = json.loads(out.read_text())
    except Exception:
        state = {}
sessions = state.get("sessions") if isinstance(state.get("sessions"), dict) else {}

now = datetime.now(timezone.utc).isoformat(timespec="seconds")
sessions[session_id] = {"updated_at": now, "models": models}

# Repo totals = sum of every session's models; recomputed each run so a
# re-read of one transcript can never double-bill another session.
aggregate = {}
for session in sessions.values():
    for model, entry in (session.get("models") or {}).items():
        total = aggregate.setdefault(model, empty())
        total["turns"] += int(entry.get("turns") or 0)
        for field in FIELDS:
            total[field] += int(entry.get(field) or 0)
        total["cost_usd"] += float(entry.get("cost_usd") or 0.0)
for entry in aggregate.values():
    entry["total_tokens"] = sum(entry[field] for field in FIELDS)
    entry["cost_usd"] = round(entry["cost_usd"], 6)

state = {
    "updated_at": now,
    "repo": root.name,
    "currency": "USD",
    "models": aggregate,
    "total_tokens": sum(e["total_tokens"] for e in aggregate.values()),
    "total_cost_usd": round(sum(e["cost_usd"] for e in aggregate.values()), 6),
    "sessions": sessions,
}
out.parent.mkdir(parents=True, exist_ok=True)
tmp = out.with_name(".costs.json.tmp")
tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
os.replace(tmp, out)
PY
exit 0
