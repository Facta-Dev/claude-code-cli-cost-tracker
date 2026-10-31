#!/usr/bin/env python3
"""Price the Claude Code transcripts already sitting on this machine.

claude-code-cli-cost-tracker — adapted (with thanks) from the open-source
cost-per-turn project, retargeted for a setup where Claude Code runs on
Ollama Cloud: the transcript records every turn's token usage regardless
of which backend served it, so each turn is priced per its own model
against the date-stamped price sheet (Ollama Cloud + first-party Claude
rates in prices.json). The billing core lives in the shared `cccost`
package; this script owns the CLI, the guardrail and the CSVs.

Claude Code has been writing per-turn token usage to disk for every session
ever run. This reads those transcripts, prices each turn against a date-stamped
price sheet, and emits two CSVs: one row per session, one row per turn.

    ./analyze-history.py --list-repos
    ./analyze-history.py --repo my-project --repo another-repo
    ./analyze-history.py --repo my-project --off-peak

The --repo filter is required, not optional. Transcripts on a working machine
include work-adjacent sessions; only explicitly named repos are ever read into
the output. --list-repos prints repo names and session counts only — no
tokens, no costs, no content.

--off-peak bills Ollama Cloud models at half rate (their off-peak window:
weekends plus weekdays outside 12:00-18:00 UTC). Rows in prices.json without
the off_peak flag — first-party Claude models — are never discounted.

Stdlib only. No network. Nothing leaves the machine.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from cccost.billing import TOKEN_FIELDS, Prices
from cccost.report import report as render_report
from cccost.transcript import discover, iter_turns, parse_ts, repo_of

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_prices(path: Path) -> Prices:
    try:
        return Prices(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo",
        action="append",
        metavar="NAME",
        help="Repo to include. Repeatable. REQUIRED — transcripts include "
        "work-adjacent sessions, so inclusion is always explicit.",
    )
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    parser.add_argument("--prices", type=Path, default=Path(__file__).parent / "prices.json")
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--curve-bins", type=int, default=12)
    parser.add_argument(
        "--off-peak",
        action="store_true",
        help="Bill Ollama Cloud rows (off_peak: true in prices.json) at half "
        "the listed rate — a blanket half rate over the entire selection, no "
        "time-window logic. First-party Claude rows are never discounted.",
    )
    parser.add_argument(
        "--list-repos",
        action="store_true",
        help="Print repo names and session counts, then exit. No tokens, no "
        "costs, no content — safe to run before choosing a filter.",
    )
    args = parser.parse_args(argv)

    if not args.projects_dir.is_dir():
        sys.exit(f"no transcripts at {args.projects_dir}")

    if args.list_repos:
        counts: dict[str, int] = defaultdict(int)
        for (slug, session_id), paths in discover(args.projects_dir).items():
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
        return 0

    if not args.repo:
        parser.error(
            "--repo is required. Run --list-repos to see what is on disk. "
            "This is a guardrail, not an oversight: shipping the wrong "
            "sessions anywhere should take a deliberate act."
        )

    prices = load_prices(args.prices)
    prices.off_peak = bool(args.off_peak)
    session_rows, turn_rows, skipped = build(args.projects_dir, args.repo, prices)

    if not session_rows:
        sys.exit(
            f"no sessions matched --repo {', '.join(args.repo)}. "
            f"On disk: {', '.join(sorted(skipped)) or '(nothing)'}"
        )

    session_csv = args.out_dir / "sessions.csv"
    turn_csv = args.out_dir / "turns.csv"
    write_csv(session_csv, session_rows)
    write_csv(turn_csv, turn_rows)

    render_report(session_rows, turn_rows, prices, max(1, args.curve_bins))
    print(f"   wrote {session_csv}  ({len(session_rows)} rows)")
    print(f"   wrote {turn_csv}  ({len(turn_rows)} rows)")
    if skipped:
        print(f"   excluded by --repo: {', '.join(sorted(skipped))}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())