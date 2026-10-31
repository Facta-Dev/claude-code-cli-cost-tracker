#!/usr/bin/env python3
"""cccost — cost reports from local Claude Code transcripts.

    cccost daily --repo my-project
    cccost weekly | monthly | session --repo my-project
    cccost report --repo my-project    # full baseline report + CSVs
    cccost --list-repos                # names + session counts only

Every subcommand bills turns per its own model against prices.json
(Ollama Cloud + first-party Claude rates), and every subcommand requires
--repo (repeatable) — the guardrail: transcripts mix personal and
work-adjacent sessions, so inclusion is always explicit.

    --off-peak   half rate on off_peak rows, blanket over the selection
    --last N     keep only turns within the last N days
    --json       machine-readable output

Stdlib only. No network. Nothing leaves the machine.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cccost.analysis import build, full_report, list_repos, load_prices
from cccost.reports import emit, session_report_rows, period_rows

PERIODS = ("daily", "weekly", "monthly")
COMMANDS = PERIODS + ("session", "report")
REPO_GUARDRAIL = (
    "--repo is required. This is a guardrail, not an oversight: transcripts "
    "include work-adjacent sessions, so shipping the wrong sessions into a "
    "report takes a deliberate act."
)
DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    command = argv[0] if argv and argv[0] in COMMANDS else None
    if command:
        argv.pop(0)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--repo", action="append", metavar="NAME")
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    parser.add_argument("--prices", type=Path,
                        default=Path(__file__).resolve().parent / "prices.json")
    parser.add_argument("--off-peak", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--last", type=float)
    parser.add_argument("--list-repos", action="store_true")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--curve-bins", type=int)
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        sys.exit(f"unknown arguments: {unknown}")
    if args.list_repos:
        list_repos(args.projects_dir)
        return 0
    if command not in COMMANDS:
        sys.exit(f"usage: cccost {'|'.join(COMMANDS)} [--repo NAME]... [flags]")
    if not args.projects_dir.is_dir():
        sys.exit(f"no transcripts at {args.projects_dir}")
    if not args.repo:
        sys.exit(REPO_GUARDRAIL)

    proj = args.projects_dir or DEFAULT_PROJECTS_DIR
    if proj and not proj.is_dir():
        sys.exit(f"no transcripts at {proj}")
    if not args.repo:
        sys.exit(REPO_GUARDRAIL)

    prices = load_prices(args.prices)
    prices.off_peak = bool(args.off_peak)

    if command == "report":
        return full_report(proj, args.repo, prices, args.out_dir or Path("out"),
                           args.curve_bins or 12)

    session_rows, turn_rows, _skipped = build(proj, args.repo, prices)
    if not session_rows:
        sys.exit(f"no sessions matched --repo {', '.join(args.repo)}")

    if command == "session":
        rows = session_report_rows(session_rows)
    else:
        rows = period_rows(_filter_last(turn_rows, args.last), command)
    return emit(command, rows, prices, args.json)


def _filter_last(rows: list[dict], days: float | None) -> list[dict]:
    """Turns in the last N days; undated rows stay (never silently dropped)."""
    if not days:
        return list(rows)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept = []
    for row in rows:
        try:
            when = datetime.fromisoformat(str(row.get("timestamp") or "").replace("Z", "+00:00"))
        except ValueError:
            kept.append(row)
        else:
            if when >= cutoff:
                kept.append(row)
    return kept


if __name__ == "__main__":
    raise SystemExit(main())