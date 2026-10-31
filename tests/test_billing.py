#!/usr/bin/env python3
"""Test aggregator — runs the four suites in tests/{unit,contracts,integrations,e2e}.

    python3 tests/test_billing.py            # everything
    python3 tests/test_billing.py unit e2e   # a subset

Each suite is independently runnable (python3 tests/<suite>/tests.py) and
uses the plain-python runner; pytest is deliberately absent from this
project.
"""

import subprocess
import sys
from pathlib import Path

SUITES = ("unit", "contracts", "integrations", "e2e")
HERE = Path(__file__).resolve().parent


def main() -> int:
    wanted = [a for a in sys.argv[1:] if a in SUITES] or list(SUITES)
    if sys.argv[1:] and not wanted:
        print(f"unknown suite; one of {', '.join(SUITES)}")
        return 2
    failures = 0
    for suite in wanted:
        print(f"--- {suite} ".ljust(50, "-"))
        proc = subprocess.run(
            [sys.executable, str(HERE / suite / "tests.py")],
            capture_output=True, text=True,
        )
        print(proc.stdout, end="")
        if proc.stderr:
            print("stderr:", proc.stderr, end="")
        if proc.returncode != 0:
            failures += 1
    print("ALL SUITES GREEN" if not failures else f"{failures} SUITE(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())