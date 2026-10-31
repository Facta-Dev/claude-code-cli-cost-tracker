# claude-code-cli-cost-tracker

A live cost meter and a history biller for Claude Code — with one twist:
**Claude Code cannot price turns that run on Ollama Cloud** (its statusline
payload and transcript carry the token usage, but no correct dollar figure for
a non-Anthropic backend). So this tracker bills every turn itself, from the
transcript, against a date-stamped sheet of Ollama Cloud **and** first-party
Claude rates.

Adapted from the open-source [cost-per-turn](https://www.youtube.com/watch?v=I2a0EJ67cVo)
project — same data model, retargeted billing.

| file | what it is |
| --- | --- |
| `statusline.py` | Live cost meter for Claude Code's status line: session cost is computed from the transcript, incrementally, per turn |
| `analyze-history.py` | Prices your entire transcript history against `prices.json` — cost per turn, cache hit rate, spend by repo |
| `prices.json` | Date-stamped price sheet: every priced Ollama Cloud model + first-party Claude models, USD per 1M tokens |
| `tests/` | A synthetic fixture reproducing every awkward transcript shape, plus the billing checks |

Python 3.10+, standard library only, nothing leaves your machine.

## Install the status line

```bash
mkdir -p ~/.claude
cp statusline.py prices.json ~/.claude/
```

Add to `~/.claude/settings.json` (absolute path — `~` is not expanded there):

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /Users/YOU/.claude/statusline.py"
  }
}
```

New session → a line like this:

```
📁 cost-lab │ ⏱ 10m 32s │ ▲ +118 -40 │ ◔ 380k/1000k ▓▓▓░░░░░ 38% │ $2.98 │ ◆ GLM 5.3 Flash
```

Test it without Claude Code:

```bash
echo '{"workspace":{"current_dir":"/tmp/demo"},"cost":{"total_cost_usd":2.47},
"model":{"display_name":"GLM 5.3 Flash"}}' | python3 statusline.py
```

How the meter bills:

- Claude Code's own `cost.total_cost_usd` is **not trusted** — under Ollama
  Cloud it is $0. The meter prices each turn from the session transcript
  (including subagent transcripts, which bill to the parent session).
- When the payload **does** carry a real cost (first-party Claude sessions),
  it wins untouched.
- A model missing from the price sheet marks the cost with `⚠` ($0.00 plus the
  marker) — never a silent zero.
- Subagent turns are real spend on your session and are included.
- Rate-limit segments appear only when the payload provides them.

## The analyzer: price your history

```bash
python3 analyze-history.py --list-repos          # repo names + counts only
python3 analyze-history.py --repo my-project     # required, repeatable
python3 analyze-history.py --repo my-project --off-peak   # bill Ollama rows at half rate
```

The `--repo` filter is required — transcripts mix personal and work-adjacent
sessions, and a cost report is the kind of artifact that gets pasted into
somewhere public. Inclusion must be a deliberate act.

Output: the cost-per-turn curve across your longest session, your real cache
hit rate, spend grouped by repo, and two CSVs in `out/` (`sessions.csv`, one
row per session; `turns.csv`, one row per API request). Both are gitignored.

The sheet carries:

- **Per-model cache-read rates that actually differ now** — not a fixed 0.1×
  input (Fable 5.1 $0.25, Opus 5.5 $0.20, Sonnet 5.5 $0.20 per MTok).
- **Ollama Cloud's off-peak pricing** (`--off-peak`: half rate on weekends and
  weekdays outside 12:00–18:00 UTC) applied only to rows tagged `off_peak`.
- **`:cloud` and `[1m]` model-suffix resolution plus an aliases map** —
  the transcript sometimes records `glm-5.3-flash:cloud`, the sheet is keyed
  by `glm-5.3-flash`.

## What makes these numbers honest

- **One line per content block, one `usage` per response.** Claude Code writes
  the identical `message.usage` on several transcript lines per API response.
  Summing assistant lines over-bills 2–6×. Both tools deduplicate on
  `message.id`, the actual unit of billing.
- **Per-turn model.** Sessions switch models mid-run; pricing follows the
  model that actually served each turn.
- **Unpriced models are named, never dropped.**

## Caveats

- **Plan credits, not cash.** Ollama Cloud plans (Pro/Max/Team) spend monthly
  usage credits at these token rates — figures track credits consumed. Same
  idea for Claude subscription plans ("equivalent API cost"). Say which one
  you mean when publishing.
- **Peak rates in the status line.** Off-peak halving is available to the
  analyzer via `--off-peak`; the live meter always prices at peak rates.
- **`claude-haiku-5-5` tiers beyond 100K** input tokens are slightly
  under-priced by the sheet (noted inside `prices.json`).
- **Machine-scoped.** Merge histories across machines on `session_id`.

## Prices move

The sheet is a snapshot as of 2026-10-30 (Ollama: ollama.com/pricing; Claude:
model table verified 2026-10-06). To reprice, copy `prices.json`, edit it, and
pass `--prices` to the analyzer. Never inline rates into the scripts.

## Tests

```bash
python3 tests/test_billing.py        # plain stdlib runner
pytest tests/test_billing.py         # same, if pytest is installed
```

The fixture (`tests/make_fixture.py`) reproduces on purpose: repeated usage
across content blocks, both cache TTLs, a mid-session model switch, an
unpriced model, a `<synthetic>` line, a nested subagent transcript, and a
malformed line.