#!/usr/bin/env python3
"""Contract suite: CLI/output surfaces that other things rely on.

    python3 tests/contracts/tests.py
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from _common import *


make_fixture()  # fresh deterministic fixture before anything runs


def test_repo_guardrail():
    """Unlisted repos go nowhere: --list-repos shows names only."""
    proc = run(ROOT / "analyze-history.py", "--list-repos", "--projects-dir", str(PROJECTS))
    assert proc.returncode == 0
    assert REPO_NAME in proc.stdout
    assert "$" not in proc.stdout, "list-repos must not leak costs"


def test_repo_required():
    """Running without --repo is a parser error, not a silent full history."""
    proc = run(ROOT / "analyze-history.py", "--projects-dir", str(PROJECTS))
    assert proc.returncode != 0 and "--repo" in proc.stderr



def test_csv_column_contract():
    """turns.csv/sessions.csv column order is a contract (merge unions on it)."""
    with analyze() as (_proc, out):
        turns = read_csv(Path(out) / "turns.csv")
        sessions = read_csv(Path(out) / "sessions.csv")
    assert list(turns[0]) == [
        "session_id", "repo", "turn_index", "timestamp", "model", "is_sidechain",
        "agent_id", "input_tokens", "output_tokens", "cache_read_tokens",
        "cache_write_5m_tokens", "cache_write_1h_tokens", "context_tokens",
        "cost_usd", "priced", "fast",
    ]
    assert list(sessions[0]) == [
        "session_id", "repo", "project_slug", "started_at", "ended_at",
        "wall_clock_s", "turns", "sidechain_turns", "models", "input_tokens",
        "output_tokens", "cache_read_tokens", "cache_write_5m_tokens",
        "cache_write_1h_tokens", "billed_input_tokens", "cache_hit_rate",
        "cost_usd", "cost_per_turn_usd", "unpriced_turns",
    ]


def test_report_header_contract():
    """The report names its sheet and as-of date — a figure without it is junk."""
    with analyze() as (proc, _out):
        as_of = json.load(open(ROOT / "prices.json"))["as_of"]
        assert proc.stdout.startswith("\n" + "=" * 74 + "\n")
        head = proc.stdout.splitlines()[1:4]
        assert head[1].startswith("  BASELINE")
        assert f"priced against prices.json as of {as_of}" in head[2]


def test_usage_exit_contract():
    """An unknown command exits loud with the usage line."""
    proc = cccost("bogus-command")
    assert proc.returncode != 0, proc.stderr
    assert "usage:" in proc.stderr or "unexpected positional" in proc.stderr

def main() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001 - report and continue
                failures += 1
                print(f"FAIL {name}: {exc}")
    print("ALL GREEN" if not failures else f"{failures} FAILURES")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
