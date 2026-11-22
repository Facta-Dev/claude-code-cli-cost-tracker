#!/usr/bin/env bash
# guard-bash.sh — PreToolUse tripwire for Bash tool calls.
#
# Reads the Claude Code hook JSON on stdin, pattern-matches the raw
# JSON-escaped command string, and:
#   BLOCK (exit 2, reason on stderr): destructive commands with no
#     legitimate use inside a generated project.
#   WARN  (note on stderr, exit 0): suspicious-but-sometimes-legitimate
#     commands.
#
# This is a tripwire, not a security boundary: complex quoting can evade
# it and quoted prose can over-match. Parse failure or a non-Bash payload
# exits 0 (fail-open) so the hook can never wedge normal tool use.
#
# The extracted command keeps its JSON escaping and trailing JSON syntax,
# so every terminator class accepts a double quote as end-of-command.
#
# Constraints honored by design:
#   - pure bash + POSIX-class grep/sed only (no jq, no node, no awk)
#   - rename-inert: contains no template placeholder literals
#   - bash -n clean; invoked via `bash <path>` (no exec bit required)

set -u

input=$(cat 2>/dev/null) || exit 0
[ -n "${input:-}" ] || exit 0

# Only guard Bash tool calls; anything else passes through.
printf '%s' "$input" | grep -q '"tool_name"[[:space:]]*:[[:space:]]*"Bash"' || exit 0

# Best-effort extraction: everything after the first "command":" key
# (still JSON-escaped, includes the trailing JSON — see terminator note).
cmd=$(printf '%s' "$input" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)/\1/p')
[ -n "${cmd:-}" ] || exit 0

has() { printf '%s' "$cmd" | grep -Eq -- "$1"; }
has_i() { printf '%s' "$cmd" | grep -Eiq -- "$1"; }

# rm with combined -rf/-fr style flags (any single token containing r and f)
RM_RF='rm[[:space:]]+-[A-Za-z]*([rR][A-Za-z]*f|f[A-Za-z]*[rR])[A-Za-z]*[[:space:]]+'
# end-of-token: whitespace, JSON-escaped newline, a quote, ':', or end
T='([[:space:]]|\\n|"|:|$)'
# optional JSON-escaped quote hugging a quoted target
Q='(\\")?'

# --- BLOCK rules (exit 2) ---------------------------------------------------

# rm -rf on filesystem root, home dirs, ~, $HOME, or core system directories.
if has "${RM_RF}${Q}"'(/(etc|usr|var|bin|lib|opt|boot|dev|home)(/[^[:space:]"]*)?|/+|~|\$HOME)'"${Q}${T}"; then
  echo "guard-bash: BLOCKED — rm -rf targeting a system root, /home, ~, or \$HOME." >&2
  exit 2
fi

# git push --force / -f to main or master (--force-with-lease is only a warn).
if has 'git[[:space:]]+push[[:space:]]' && has "(main|master)${T}" \
   && has "(\\-\\-force${T}|[[:space:]]-f${T})" \
   && ! has '\-\-force-with-lease'; then
  echo "guard-bash: BLOCKED — force-push to main/master violates the append-only history rule." >&2
  exit 2
fi

# chmod -R 777
if has 'chmod[[:space:]]+-R[[:space:]]+777'; then
  echo "guard-bash: BLOCKED — chmod -R 777 (world-writable recursive) is never acceptable." >&2
  exit 2
fi

# dd writing straight to a device node
if has 'dd[[:space:]][^|;]*of=/dev/'; then
  echo "guard-bash: BLOCKED — dd of=/dev/* overwrites a raw device." >&2
  exit 2
fi

# --- WARN rules (stderr note, exit 0) ----------------------------------------

# rm -rf on an absolute path outside /tmp (project-relative rm is untouched;
# system roots were already blocked above).
if has "${RM_RF}${Q}/" && ! has "${RM_RF}${Q}"'/tmp(/|[[:space:]]|"|$)'; then
  echo "guard-bash: WARN — rm -rf on an absolute path outside /tmp; double-check the target." >&2
fi

# Any force-with-lease push: safer than --force but still rewrites history.
if has 'git[[:space:]]+push[[:space:]]' && has '\-\-force-with-lease'; then
  echo "guard-bash: WARN — --force-with-lease rewrites remote history; confirm the branch is yours alone." >&2
fi

# Destructive SQL outside migrations/tests context.
if has_i '(drop[[:space:]]+table|truncate)' && ! has '(migrations/|tests/)'; then
  echo "guard-bash: WARN — DROP TABLE/TRUNCATE outside a migrations/ or tests/ path." >&2
fi

exit 0