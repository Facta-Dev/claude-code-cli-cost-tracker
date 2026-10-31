#!/usr/bin/env python3
"""Integration suite: transcript -> priced rows -> CSVs pipelines.

    python3 tests/integrations/tests.py
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from _common import *


make_fixture()  # fresh deterministic fixture before anything runs


def test_analyzer_billing():
    """Peak rates: dedup, TTL split, per-turn model pricing, fold subagents."""
    with analyze() as (_proc, out):
        sessions = read_csv(Path(out) / "sessions.csv")
        turns = read_csv(Path(out) / "turns.csv")

        assert len(turns) == 11, "dupes and corrupt-usage lines must not bill"
        a = session_row(sessions, "sessA")
        b = session_row(sessions, "sessB")

        # sessA: 1.40 + 1.58 + 0 + 0 + 3.72 (opus fast: 1.6+2.0+0.12)
        assert float(a["cost_usd"]) == 6.70 and int(a["turns"]) == 5
        # sessB: 0.59 + 3.00 (claude) + 2.00 + 2.00 (14:00 peak) + 0.75 + 0.35 (haiku tier)
        assert float(b["cost_usd"]) == 8.69 and int(b["turns"]) == 6
        assert int(b["sidechain_turns"]) == 1, "subagent must fold into parent"
        # cache hit rates on hand-computed splits
        assert float(b["cache_hit_rate"]) == 0.2213  # 8M read of 36.15M billed
        assert float(a["cache_hit_rate"]) == 0.8991


def test_off_peak_discounts_only_ollama():
    """--off-peak halves Ollama rows per turn by timestamp window, and never
    first-party Claude rows. Fixture: Friday 09:0x/09:10/09:15/09:30 UTC are
    off-peak; the 14:00 UTC turn is inside Ollama's peak window."""
    with analyze("--off-peak") as (_proc, out):
        sessions = read_csv(Path(out) / "sessions.csv")
        a = session_row(sessions, "sessA")
        b = session_row(sessions, "sessB")
        assert float(a["cost_usd"]) == 5.21  # 1.49 halved Ollama turns + 3.72 (claude fast, full)
        # 0.59->0.295 | claude 3.00 | 2.00->1.00 | 14:00 stays 2.00 | 0.75->0.375 | haiku 0.35 (claude row)
        assert float(b["cost_usd"]) == 7.02


def test_unpriced_models_named():
    """Models missing from the sheet are counted, $0, and named — not silent."""
    with analyze() as (proc, out):
        assert "unknown-model-x" in proc.stdout, "unpriced model must be named"
        sessions = read_csv(Path(out) / "sessions.csv")
        assert int(session_row(sessions, "sessA")["unpriced_turns"]) == 1



def test_fixture_regenerates_from_nothing():
    """make_fixture() wipes leftovers; a junk session cannot haunt totals."""
    junk = SLUG / "sessZZ.jsonl"
    junk.parent.mkdir(parents=True, exist_ok=True)
    junk.write_text(json.dumps({"type": "assistant", "model": "junk-model"}))
    make_fixture()
    assert not junk.exists() and (SLUG / "sessA.jsonl").exists()

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
