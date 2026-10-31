#!/usr/bin/env python3
"""cccost CLI launcher — the implementation lives in cccost/cli.py (same
flags as ever; this file exists so `python3 ~/.claude/cccost.py` keeps
working with a launcher next to the package)."""

from cccost.cli import main

if __name__ == "__main__":
    raise SystemExit(main())