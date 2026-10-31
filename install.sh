#!/usr/bin/env bash
# Install the tracker into ~/.claude (idempotent — safe to re-run).
# See INSTALL.md for what lands where and how to uninstall.
set -euo pipefail
cd "$(dirname "$0")"

python3 tests/test_billing.py
mkdir -p ~/.claude/commands
cp -r cccost statusline.py cccost.py prices.json ~/.claude/
rm -rf ~/.claude/cccost/__pycache__   # bytecode cruft doesn't ship
cp commands/cccost.md ~/.claude/commands/

cat <<EOF

Installed. Now add the status line to ~/.claude/settings.json (merge, don't
replace — and read INSTALL.md §2 for the details):

    "statusLine": {
      "type": "command",
      "command": "python3 $HOME/.claude/statusline.py",
      "refreshInterval": 5
    }

The next Claude Code session shows the live meter; /cccost works, too.

For the iTerm2 session-status detail (cost next to the state dot), point
the Stop hook at the wrapper:

    "Stop": [ { "hooks": [ { "type": "command",
      "command": "/Users/YOU/.claude/hooks/cc-status-with-cost.sh" } ] } ]
EOF