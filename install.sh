#!/usr/bin/env bash
# Install the tracker into ~/.claude (idempotent — safe to re-run).
# Runs the test suite first, then lays out the files, then prints the exact
# JSON blocks to merge into ~/.claude/settings.json. See INSTALL.md.
set -euo pipefail
cd "$(dirname "$0")"

python3 tests/test_billing.py
mkdir -p ~/.claude/commands ~/.claude/hooks
cp -r cccost statusline.py cccost.py prices.json ~/.claude/
rm -rf ~/.claude/cccost/__pycache__   # bytecode cruft doesn't ship
cp commands/cccost.md ~/.claude/commands/
cp hooks/session_status.py hooks/session-status.ps1 ~/.claude/hooks/

cat <<EOF

Installed. Now merge (don't replace) into ~/.claude/settings.json:

    "statusLine": {
      "type": "command",
      "command": "python3 $HOME/.claude/statusline.py",
      "refreshInterval": 5
    },

    "hooks": {
      "PreToolUse":        [ { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/session_status.py" } ] } ],
      "PostToolUse":       [ { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/session_status.py" } ] } ],
      "Notification":      [ { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/session_status.py" } ] } ],
      "PermissionRequest": [ { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/session_status.py" } ] } ],
      "SessionStart":      [ ... the same single hook ... note: keep any other
      "SessionEnd":        ... SessionStart hooks (e.g. model router) in their own entry ... ],
      "Stop":              [ { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/session_status.py" } ] } ],
      "StopFailure":       [ { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/session_status.py" } ] } ],
      "SubagentStop":      [ { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/session_status.py" } ] } ],
      "UserPromptSubmit":  [ { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/session_status.py" } ] } ]
    }

One hook serves every event on every platform: macOS shows the iTerm2 state
dot + detail (osascript if iTerm2 is closed), Linux fires notify-send on
waiting/done, Windows toasts (session-status.ps1). A new session shows the
live meter; /cccost reports.
EOF