"""Session/turn analysis shared by the analyzer and the report CLI.

build() turns discovered transcripts into priced turn rows and per-session
summary rows; the report renderer and the cccost CLI both consume those
rows. Discovery, shape knowledge and pricing live in their own modules —
this one only aggregates and emits CSVs.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from cccost.billing import TOKEN_FIELDS, Prices
from cccost.transcript import discover, iter_turns, parse_ts, repo_of


def build(projects_dir: Path, repos: list[str] | None, prices: Prices):
    """Return (session rows, turn rows, skipped repo names)."""
    session_rows, turn_rows = [], []
    skipped: set[str] = set()
    wanted = {r.lower() for r in repos} if repos else None

    for (slug, session_id), paths in sorted(discover(projects_dir).items()):
        turns = []
        for path in sorted(paths):
            turns.extend(iter_turns(path))
        if not turns:
            continue

        turns.sort(key=lambda t: (t["timestamp"] or "", t["message_id"]))
        cwds = [t["cwd"] for t in turns if t["cwd"]]
        # Fall back to the slug's last dash-separated token when a session
        # recorded no cwd at all: two unrelated sessions can then collide on
        # one generic name — that is why --repo is still required.
        repo = repo_of(
            max(set(cwds), key=cwds.count) if cwds else None,
            slug,
        )
        if wanted is not None and repo.lower() not in wanted:
            skipped.add(repo)
            continue

        totals = dict.fromkeys(TOKEN_FIELDS, 0)
        cost_total = 0.0
        unpriced = 0
        models: dict[str, int] = defaultdict(int)
        stamps = []

        for index, turn in enumerate(turns, start=1):
            tok = turn["tokens"]
            cost = prices.cost(turn["model"], tok)
            if cost is None:
                unpriced += 1
                cost = 0.0
            cost_total += cost
            models[turn["model"]] += 1
            for field in TOKEN_FIELDS:
                totals[field] += tok[field]
            ts = parse_ts(turn["timestamp"])
            if ts:
                stamps.append(ts)

            billed_in = tok["input"] + tok["cache_read"] + tok["cache_write_5m"] + tok["cache_write_1h"]
            turn_rows.append(
                {
                    "session_id": session_id,
                    "repo": repo,
                    "turn_index": index,
                    "timestamp": turn["timestamp"] or "",
                    "model": turn["model"],
                    "is_sidechain": int(turn["is_sidechain"]),
                    "agent_id": turn["agent_id"],
                    "input_tokens": tok["input"],
                    "output_tokens": tok["output"],
                    "cache_read_tokens": tok["cache_read"],
                    "cache_write_5m_tokens": tok["cache_write_5m"],
                    "cache_write_1h_tokens": tok["cache_write_1h"],
                    "context_tokens": billed_in,
                    "cost_usd": round(cost, 6),
                    "priced": int(prices.resolve(turn["model"]) in prices.models),
                }
            )

        billed_input = (
            totals["input"] + totals["cache_read"] + totals["cache_write_5m"] + totals["cache_write_1h"]
        )
        wall = (
            (max(stamps) - min(stamps)).total_seconds() if len(stamps) > 1 else 0.0
        )
        session_rows.append(
            {
                "session_id": session_id,
                "repo": repo,
                "project_slug": slug,
                "started_at": min(stamps).isoformat() if stamps else "",
                "ended_at": max(stamps).isoformat() if stamps else "",
                "wall_clock_s": round(wall, 1),
                "turns": len(turns),
                "sidechain_turns": sum(1 for t in turns if t["is_sidechain"]),
                "models": ";".join(sorted(models)),
                "input_tokens": totals["input"],
                "output_tokens": totals["output"],
                "cache_read_tokens": totals["cache_read"],
                "cache_write_5m_tokens": totals["cache_write_5m"],
                "cache_write_1h_tokens": totals["cache_write_1h"],
                "billed_input_tokens": billed_input,
                "cache_hit_rate": round(totals["cache_read"] / billed_input, 4)
                if billed_input
                else 0.0,
                "cost_usd": round(cost_total, 4),
                "cost_per_turn_usd": round(cost_total / len(turns), 4),
                "unpriced_turns": unpriced,
            }
        )

    return session_rows, turn_rows, skipped

def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

def load_prices(path: Path) -> Prices:
    """Price sheet with a loud exit on a broken/undated sheet."""
    try:
        return Prices(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(str(exc))


def list_repos(projects_dir: Path) -> None:
    """Repo names and session counts only — no tokens, no costs, no content."""
    counts: dict[str, int] = defaultdict(int)
    for (slug, _session_id), paths in discover(projects_dir).items():
        cwd = None
        for path in paths:
            for turn in iter_turns(path):
                if turn["cwd"]:
                    cwd = turn["cwd"]
                    break
            if cwd:
                break
        counts[repo_of(cwd, slug)] += 1
    print(f"{'repo':<28}sessions")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"{name:<28}{n}")
    print("\nPass the ones you want with --repo. Nothing is read into the CSVs until you do.")


def full_report(projects_dir: Path, repos: list[str], prices, out_dir: Path, curve_bins: int) -> int:
    """analyze-history's whole flow: build, CSVs, text report, summary."""
    from cccost.report import report as render_report

    session_rows, turn_rows, skipped = build(projects_dir, repos, prices)
    if not session_rows:
        sys.exit(
            f"no sessions matched --repo {', '.join(repos)}. "
            f"On disk: {', '.join(sorted(skipped)) or '(nothing)'}"
        )
    session_csv = Path(out_dir) / "sessions.csv"
    turn_csv = Path(out_dir) / "turns.csv"
    write_csv(session_csv, session_rows)
    write_csv(turn_csv, turn_rows)
    render_report(session_rows, turn_rows, prices, curve_bins)
    print(f"   wrote {session_csv}  ({len(session_rows)} rows)")
    print(f"   wrote {turn_csv}  ({len(turn_rows)} rows)")
    if skipped:
        print(f"   excluded by --repo: {', '.join(sorted(skipped))}")
    print()
    return 0
