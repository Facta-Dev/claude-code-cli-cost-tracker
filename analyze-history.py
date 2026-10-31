#!/usr/bin/env python3
"""analyze-history — the full-history baseline report.

Thin alias for `cccost report` — same flags (--repo, --projects-dir,
--prices, --out-dir, --curve-bins, --off-peak, --list-repos), same output.
Kept for muscle memory and existing scripts; new code should call cccost.
"""

from __future__ import annotations

import sys

from cccost import main as cccost_main

if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        raise SystemExit(0)
    raise SystemExit(cccost_main(["report", *argv]))