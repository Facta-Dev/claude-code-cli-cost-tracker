#!/usr/bin/env python3
"""Price the Claude Code transcripts already sitting on this machine.

claude-code-cli-cost-tracker — adapted (with thanks) from the open-source
cost-per-turn project, retargeted for a setup where Claude Code runs on
Ollama Cloud: the transcript records every turn's token usage regardless
of which backend served it, so each turn is priced per its own model
against the date-stamped price sheet (Ollama Cloud + first-party Claude
rates in prices.json). The billing core lives in the shared `cccost`
package; this script owns the classic report flow.

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
import sys
from pathlib import Path

from cccost.analysis import full_report, list_repos, load_prices

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
REPO_GUARDRAIL = (
    "--repo is required. Run --list-repos to see what is on disk. "
    "This is a guardrail, not an oversight: shipping the wrong "
    "sessions anywhere should take a deliberate act."
)


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
        list_repos(args.projects_dir)
        return 0

    if not args.repo:
        parser.error(REPO_GUARDRAIL)

    prices = load_prices(args.prices)
    prices.off_peak = bool(args.off_peak)
    return full_report(args.projects_dir, args.repo, prices, args.out_dir, args.curve_bins)


if __name__ == "__main__":
    raise SystemExit(main())