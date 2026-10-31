#!/usr/bin/env python3
"""analyze-history — the full-history baseline report.

Thin alias for `cccost report` — same flags (--repo, --projects-dir,
--prices, --out-dir, --curve-bins, --off-peak, --list-repos), same output.
Kept for muscle memory and existing scripts; new code should call cccost.
"""

import sys

from cccost.cli import main


def _argv() -> list[str]:
    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        raise SystemExit(0)
    return ["report", *argv]


if __name__ == "__main__":
    raise SystemExit(main(_argv()))