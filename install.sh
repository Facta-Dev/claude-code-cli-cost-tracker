#!/usr/bin/env bash
# Install the tracker into the Claude Code config dir — $CLAUDE_CONFIG_DIR when set
# (multi-profile setups), else ~/.claude. Idempotent — safe to re-run.
# Runs the test suite first, then lays out the files, then prints the exact
# JSON blocks to merge into <config dir>/settings.json. See INSTALL.md.
set -euo pipefail
cd "$(dirname "$0")"

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

python3 tests/test_billing.py
mkdir -p "$CLAUDE_DIR/commands" "$CLAUDE_DIR/hooks"
cp -r cccost statusline.py cccost.py prices.json "$CLAUDE_DIR/"
rm -rf "$CLAUDE_DIR/cccost/__pycache__"   # bytecode cruft doesn't ship
if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
  # the slash command pins the install path: point it at the custom config dir
  sed -e "s#\$HOME/\.claude#$CLAUDE_DIR#g" -e "s#~/\.claude#$CLAUDE_DIR#g" \
    commands/cccost.md > "$CLAUDE_DIR/commands/cccost.md"
else
  cp commands/cccost.md "$CLAUDE_DIR/commands/"
fi
cp hooks/session_status.py hooks/session-status.ps1 "$CLAUDE_DIR/hooks/"
if [ "$(uname -s)" = "Linux" ]; then
  mkdir -p "$CLAUDE_DIR/hooks/linux"
  cp hooks/linux/session_panel.py hooks/linux/wezterm.lua hooks/linux/ccterm "$CLAUDE_DIR/hooks/linux/"
fi

cat <<EOF

Installed into $CLAUDE_DIR. Now merge (don't replace) into $CLAUDE_DIR/settings.json:

    "statusLine": {
      "type": "command",
      "command": "python3 $CLAUDE_DIR/statusline.py",
      "refreshInterval": 5
    },

    "hooks": {
      "PreToolUse":        [ { "hooks": [ { "type": "command", "command": "python3 $CLAUDE_DIR/hooks/session_status.py" } ] } ],
      "PostToolUse":       [ { "hooks": [ { "type": "command", "command": "python3 $CLAUDE_DIR/hooks/session_status.py" } ] } ],
      "Notification":      [ { "hooks": [ { "type": "command", "command": "python3 $CLAUDE_DIR/hooks/session_status.py" } ] } ],
      "PermissionRequest": [ { "hooks": [ { "type": "command", "command": "python3 $CLAUDE_DIR/hooks/session_status.py" } ] } ],
      "SessionStart":      [ ... the same single hook ... note: keep any other
      "SessionEnd":        ... SessionStart hooks (e.g. model router) in their own entry ... ],
      "Stop":              [ { "hooks": [ { "type": "command", "command": "python3 $CLAUDE_DIR/hooks/session_status.py" } ] } ],
      "StopFailure":       [ { "hooks": [ { "type": "command", "command": "python3 $CLAUDE_DIR/hooks/session_status.py" } ] } ],
      "SubagentStop":      [ { "hooks": [ { "type": "command", "command": "python3 $CLAUDE_DIR/hooks/session_status.py" } ] } ],
      "UserPromptSubmit":  [ { "hooks": [ { "type": "command", "command": "python3 $CLAUDE_DIR/hooks/session_status.py" } ] } ]
    }

One hook serves every event on every platform: macOS shows the iTerm2 state
dot + detail (osascript if iTerm2 is closed), Linux fires notify-send on
waiting/done, Windows toasts (session-status.ps1). A new session shows the
live meter; /cccost reports.
EOF

if [ "$(uname -s)" = "Linux" ]; then
cat <<EOF

Linux, optional — per-session state inside the terminal (INSTALL.md 3d):
  * tab title:  add CC_TAB_TITLE=1 to the hook command and set
                CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1 in settings.json "env"
  * panel of all sessions, click to jump (WezTerm):  $CLAUDE_DIR/hooks/linux/ccterm
EOF
fi
