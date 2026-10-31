---
description: Cost reports from local Claude Code transcripts (cccost CLI)
allowed-tools: Bash(python3 $HOME/.claude/cccost.py *):, Bash(python3 ~/.claude/cccost.py *):
---

# cccost — cost reports

Run the installed tracker CLI with the user's arguments, then present the
output verbatim in a fenced code block. If a run exits non-zero and the
message names the --repo guardrail, first run `--list-repos` (it prints repo
names and session counts only — no tokens, no costs, no content), show the
names, and ask which repos to bill. Never widen the selection yourself.

```
!`python3 $HOME/.claude/cccost.py $ARGUMENTS`
```

When a model is named in the "models missing from the price sheet" note,
say these turns were billed $0 and suggest adding the model's row to
`~/.claude/prices.json` (units: USD per 1M tokens, date-stamped).