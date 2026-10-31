# Install manual

Everything in detail: files, settings, env overrides, updates, uninstall.
Stdlib-only Python 3.10+; no `pip install`; nothing leaves your machine.

## What gets installed where

| Installed to | Where it comes from | What it needs |
| --- | --- | --- |
| `~/.claude/statusline.py` | `statusline.py` | `~/.claude/cccost/` next to it |
| `~/.claude/cccost/` | `cccost/` | `~/.claude/prices.json` (resolved via `CC_COST_PRICES`, else script-adjacent default) |
| `~/.claude/cccost.py` | `cccost.py` | same package + sheet |
| `~/.claude/prices.json` | `prices.json` (repo copy) | the billing sheet; edit rates there |
| `~/.claude/commands/cccost.md` | `commands/cccost.md` | nothing — a prompt file |

## 1 · Get the repo

```bash
git clone https://github.com/Facta-Dev/claude-code-cli-cost-tracker
cd claude-code-cli-cost-tracker
python3 tests/test_billing.py          # smoke: 13 checks, no dependencies

mkdir -p ~/.claude/commands
cp -r cccost statusline.py cccost.py prices.json ~/.claude/
cp commands/cccost.md ~/.claude/commands/
```

## 2 · Status line — settings.json

Add (merge, don't replace):

```json
"statusLine": {
  "type": "command",
  "command": "python3 /Users/YOU/.claude/statusline.py",
  "refreshInterval": 5
}
```

- Use an **absolute** path — `~` is not expanded inside the command string.
- `refreshInterval` re-renders every 5s so cost updates between turns;
  renders also fire on events.
- Python: any 3.10+; the scripts resolve the `cccost` package relative to
  their own directory (`sys.path[0]`), so the copied layout above works.
- Verify standalone before starting a session:

```bash
echo '{"workspace":{"current_dir":"/tmp/demo"},"cost":{"total_cost_usd":2.47},"model":{"display_name":"GLM 5.3 Flash"}}' | python3 ~/.claude/statusline.py
```

## 3 · Reports CLI + slash command

```bash
python3 ~/.claude/cccost.py --list-repos                    # names + counts only
python3 ~/.claude/cccost.py daily --repo my-project
```

Inside Claude Code, `/cccost daily --repo my-project` runs the installed
CLI. The command file pins `allowed-tools` to the installed path — if you
installed elsewhere, edit `commands/cccost.md` accordingly.

## 4 · Environment overrides

| Variable | Default | Meaning |
| --- | --- | --- |
| `CC_COST_PRICES` | `prices.json` next to `statusline.py` | sheet for the live meter; the CLI takes `--prices` |
| `CC_COST_CACHE_DIR` | `~/.cache/claude-cost-tracker/` | per-session billing state for the status line (byte offsets + session cost). Safe to wipe anytime — a lost state file just re-bills a session's transcript from byte 0 (cost, not cumulative identity, is recomputed) |

## 5 · Prices

`prices.json` is a date-stamped snapshot: Ollama Cloud (off-peak tagged rows
halve with `--off-peak`, per turn by timestamp — weekends + weekdays outside
12:00–18:00 UTC) + first-party Claude
models with per-model cache rates. To reprice: copy the sheet, edit rates,
pass `--prices` to any report; verify current rates at
[ollama.com/pricing](https://ollama.com/pricing) and Anthropic's model table.

Models absent from the sheet bill $0 and are **named** in every output —
add a row when a new model appears:

```json
"new-model-id": { "input": 0.15, "output": 0.50, "cache_read": 0.03, "cache_write_5m": 0.15, "cache_write_1h": 0.15 }
```

## 6 · Update

```bash
cd claude-code-cli-cost-tracker && git pull
python3 tests/test_billing.py
cp -r cccost statusline.py cccost.py prices.json ~/.claude/
cp commands/cccost.md ~/.claude/commands/
```

## 7 · Uninstall

Delete the installed files, the state cache, and the settings key:

```bash
rm -rf ~/.claude/cccost ~/.claude/statusline.py ~/.claude/cccost.py \
       ~/.claude/prices.json ~/.claude/commands/cccost.md \
       ~/.cache/claude-cost-tracker
```

…then remove the `statusLine` block from `~/.claude/settings.json`.