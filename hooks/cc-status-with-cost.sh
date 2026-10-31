#!/usr/bin/env bash
# Feed Claude Code hook events to iTerm2's cc-status (unchanged behavior),
# then add the session's live cost — from the cccost tracker state cache —
# as the status DETAIL next to the state dot. The status display must never
# break over this: every cost step is best-effort.

# Hook environments run a restricted PATH; it2 lives inside the iTerm app.
IT2="/Applications/iTerm.app/Contents/Resources/utilities/it2"
[ -x "$IT2" ] || IT2="/opt/homebrew/bin/it2"
[ -x "$IT2" ] || IT2="$(command -v it2 2>/dev/null)" || IT2=""

stdin_file=$(mktemp)
cat > "$stdin_file"
"$HOME/.config/iterm2/cc-status" < "$stdin_file"

sid=$(python3 -c '
import json, re, sys
try:
    j = json.load(open(sys.argv[1]))
    print(re.sub(r"[^A-Za-z0-9_-]", "", str(j.get("session_id") or "")))
except Exception:
    pass' "$stdin_file" 2>/dev/null)

if [ -n "$sid" ]; then
    state="$HOME/.cache/claude-cost-tracker/$sid.json"
    cost=$(python3 -c "
import json, sys
try:
    print(f\"{float(json.load(open(sys.argv[1])).get('cost') or 0):.2f}\")
except Exception:
    pass" "$state" 2>/dev/null)
    if [ -n "$cost" ]; then
        # Target THE session that fired the hook (ITERM_SESSION_ID is set in
        # every iTerm2 pane); fall back to the active session otherwise.
        if [ -n "${ITERM_SESSION_ID:-}" ]; then
            "$IT2" session set-status --session "$ITERM_SESSION_ID" --detail "💰 \$$cost" || true
        else
            "$IT2" session set-status --detail "💰 \$$cost" || true
        fi
    fi
fi
rm -f "$stdin_file"