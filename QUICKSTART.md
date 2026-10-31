# Quickstart

Three commands and you have a live cost meter, reports, and a slash command.
Nothing leaves your machine; stdlib-only Python 3.10+.

## 1 · Install

```bash
git clone https://github.com/Facta-Dev/claude-code-cli-cost-tracker
cd claude-code-cli-cost-tracker
python3 tests/test_billing.py        # 13 checks, no dependencies needed
mkdir -p ~/.claude/commands
cp -r cccost statusline.py cccost.py prices.json ~/.claude/
cp commands/cccost.md ~/.claude/commands/
```

## 2 · Turn on the status line

Add to `~/.claude/settings.json` (absolute path — `~` is not expanded there):

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /Users/YOU/.claude/statusline.py",
    "refreshInterval": 5
  }
}
```

Merge into your existing settings — don't replace the file. Start (the next)
Claude Code session and the line appears:

```
📁 cost-lab │ ⏱ 10m 32s │ ▲ +118 -40 │ ◔ 380k/1M ▓▓▓░░░░░ 38% │ $2.98 │ ◆ GLM 5.3 Flash
```

## 3 · Reports

```bash
cccost --list-repos                     # repo names + session counts only
python3 ~/.claude/cccost.py daily --repo my-project
```

Or from inside Claude Code:

```
/cccost daily --repo my-project
```

First run prints repo names + session counts only — no tokens, no costs, no
content — to choose what to bill. All reports take `--repo` (repeatable);
`--last N` window; `--json`; `--off-peak` (Ollama Cloud rows only).

## 45 seconds, really

```bash
echo '{"workspace":{"current_dir":"/tmp/demo"},"cost":{"total_cost_usd":2.47},"model":{"display_name":"GLM 5.3 Flash"}}' | python3 statusline.py
```

prints the line standalone; `python3 ~/.claude/cccost.py --list-repos` lists
what's on disk. A model missing from the sheet bills $0, is named in every
report, and flags the status line — add its row to `~/.claude/prices.json`
(units: USD per 1M tokens; snapshot as of 2026-10-30).