"""Usage reports: daily / weekly / monthly / session tables from billed rows.

The aggregate views, grouped from the same priced rows the full report
consumes — one billing core, many views. Timestamps are treated as UTC
(Claude Code writes ISO timestamps; a missing one falls out as "?").
Output is plain monospace tables or JSON; nothing leaves the machine.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime


def bucket_key(command: str, timestamp: str) -> str:
    """Group a turn into the report period named by the subcommand."""
    if not timestamp:
        return "?"
    if command == "daily":
        return timestamp[:10]
    if command == "monthly":
        return timestamp[:7]
    if command == "weekly":
        try:
            d = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return "?"
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return "?"


def period_rows(turn_rows: list[dict], command: str) -> list[dict]:
    """One row per period (daily / weekly / monthly), chronological."""
    buckets: dict[str, dict] = {}
    for turn in turn_rows:
        key = bucket_key(command, turn.get("timestamp") or "")
        b = buckets.setdefault(key, {
            "turns": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0, "by_repo": {},
        })
        b["turns"] += 1
        b["cost_usd"] += float(turn.get("cost_usd") or 0.0)
        b["input_tokens"] += int(turn.get("input_tokens") or 0)
        b["output_tokens"] += int(turn.get("output_tokens") or 0)
        b["cache_read_tokens"] += int(turn.get("cache_read_tokens") or 0)
        b["cache_write_tokens"] += (
            int(turn.get("cache_write_5m_tokens") or 0) + int(turn.get("cache_write_1h_tokens") or 0)
        )
        repo = turn.get("repo") or "?"
        b["by_repo"][repo] = b["by_repo"].get(repo, 0.0) + float(turn.get("cost_usd") or 0.0)
    return [
        {**b, "key": key, "cost_usd": round(b["cost_usd"], 4), "by_repo": b["by_repo"]}
        for key, b in sorted(buckets.items(), key=lambda kv: (kv[0] == "?", kv[0]))
    ]


def session_report_rows(session_rows: list[dict]) -> list[dict]:
    """Per-session rows in start order (oldest first), for the table/json."""
    cols = ("session_id", "repo", "models", "turns", "wall_clock_s", "cache_hit_rate", "cost_usd")
    rows = []
    for r in sorted(session_rows, key=lambda r: r.get("started_at") or ""):
        rows.append({k: r.get(k) for k in cols})
    return rows


def unpriced_note(prices) -> str:
    lines = []
    if prices.unknown:
        lines.append("!  models missing from the price sheet (counted, priced at $0): "
                     + ", ".join(sorted(prices.unknown)))
    if getattr(prices, "fast_fallback", 0):
        lines.append(f"!  fast-mode turns billed at base rates, missing -fast row: "
                     f"{prices.fast_fallback}")
    return "\n".join(lines) + "\n" if lines else ""


def render_period(rows: list[dict], command: str) -> str:
    label = {"daily": "date", "weekly": "week", "monthly": "month"}.get(command, "period")
    lines = [
        f"  {label:<12}{'turns':>6}{'input':>14}{'output':>12}"
        f"{'cache-read':>14}{'cache-write':>14}{'cost':>10}"
    ]
    total_cost = total_turns = 0
    for r in rows:
        total_cost += r["cost_usd"]
        total_turns += r["turns"]
        lines.append(
            f"  {r['key']:<12}{r['turns']:>6}"
            f"{r['input_tokens']:>14,}"
            f"{r['output_tokens']:>12,}"
            f"{r['cache_read_tokens']:>14,}"
            f"{r['cache_write_tokens']:>14,}"
            f"   ${r['cost_usd']:<7.2f}"
        )
    lines.append(f"  {'TOTAL':<12}{total_turns:>6}{'':>50}   ${total_cost:.2f}")
    return "\n".join(lines)


def render_session(rows: list[dict]) -> str:
    lines = [
        f"  {'session':<9}{'repo':<22}{'turns':>6}{'wall':>11}{'$/turn':>9}{'cache':>8}{'cost':>10}"
    ]
    for r in rows:
        turns = r.get("turns") or 0
        wall = r.get("wall_clock_s") or 0
        lines.append(
            f"  {str(r.get('session_id', ''))[:8]:<9}{str(r.get('repo', '?'))[:21]:<22}"
            f"{turns:>6}{wall / 60:>10.0f}m"
            f"{r.get('cost_usd', 0) / max(1, turns):>9.4f}{r.get('cache_hit_rate', 0):>8.1%}"
            f"   ${r.get('cost_usd', 0):<7.2f}"
        )
    return "\n".join(lines)


def model_rows(turn_rows: list[dict]) -> list[dict]:
    """One row per model that served at least one turn, cost-ordered."""
    buckets: dict[str, dict] = {}
    for turn in turn_rows:
        model = turn.get("model") or "?"
        b = buckets.setdefault(model, {"turns": 0, "cost_usd": 0.0, "input_tokens": 0,
                                       "output_tokens": 0, "cache_read_tokens": 0})
        b["turns"] += 1
        b["cost_usd"] += float(turn.get("cost_usd") or 0.0)
        b["input_tokens"] += int(turn.get("input_tokens") or 0)
        b["output_tokens"] += int(turn.get("output_tokens") or 0)
        b["cache_read_tokens"] += int(turn.get("cache_read_tokens") or 0)
    rows = [
        {**b, "model": model, "cost_usd": round(b["cost_usd"], 4)}
        for model, b in buckets.items()
    ]
    rows.sort(key=lambda r: (-r["cost_usd"], r["model"]))
    return rows


def render_models(rows: list[dict]) -> str:
    lines = [
        f"  {'model':<24}{'turns':>6}{'input':>14}{'output':>12}"
        f"{'cache-read':>14}   {'cost':<7}"
    ]
    for r in rows:
        lines.append(
            f"  {r['model'][:23]:<24}{r['turns']:>6}"
            f"{r['input_tokens']:>14,}"
            f"{r['output_tokens']:>12,}"
            f"{r['cache_read_tokens']:>14,}"
            f"   ${r['cost_usd']:<7.2f}"
        )
    lines.append(f"  {'TOTAL':<24}{sum(r['turns'] for r in rows):>6}{'':>40}   ${sum(r['cost_usd'] for r in rows):.2f}")
    return "\n".join(lines)


def emit(command: str, period_or_session_rows: list[dict], prices, want_json: bool) -> int:
    """The subcommand body: render the table or dump JSON."""
    if want_json:
        print(json.dumps({
            "command": command,
            "as_of": prices.as_of,
            "rows": period_or_session_rows,
            "total_cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in period_or_session_rows), 4),
        }, indent=2, default=str))
        return 0
    label = {"daily": "DAILY USAGE", "weekly": "WEEKLY USAGE",
             "monthly": "MONTHLY USAGE", "session": "SESSION USAGE",
             "models": "MODEL USAGE"}[command]
    body = render_period(period_or_session_rows, command) if command in ("daily", "weekly", "monthly") \
        else render_models(period_or_session_rows) if command == "models" \
        else render_session(period_or_session_rows)
    sys.stdout.write(
        f"\n  {label}  ·  {len(period_or_session_rows)} "
        f"{'days' if command == 'daily' else 'weeks' if command == 'weekly' else 'months' if command == 'monthly' else 'models' if command == 'models' else 'sessions'}"
        f"  ·  priced against {prices.path.name} as of {prices.as_of}\n\n"
        + body + "\n"
    )
    if prices.unknown:
        sys.stdout.write("\n" + unpriced_note(prices))
    return 0