# claude-code-cli-cost-tracker

[![ci](https://github.com/Facta-Dev/claude-code-cli-cost-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/Facta-Dev/claude-code-cli-cost-tracker/actions/workflows/ci.yml)

**What does your agent work actually cost?** — Live, in your terminal, in
dollars, while you work. This tracker bills every turn of your Claude Code
sessions from the token usage Claude Code already writes to disk — whatever
backend you use, including **Ollama Cloud-backed Claude Code**, where Claude
Code's own cost figures are unavailable.

Adapted from, and standing on, the open-source **cost-per-turn** project and
**ccusage** ([github.com/ccusage/ccusage](https://github.com/ccusage/ccusage)
by [@ryoppippi](https://github.com/ryoppippi), MIT) — see
[Credits](#credits).

```
📁 cost-lab │ ⏱ 10m 32s │ ▲ +118 -40 │ ◔ 380k/1M ▓▓▓░░░░░ 38% │ $2.98 │ ◆ GLM 5.3 Flash
```

- **Live status line**: session cost computed per turn, incrementally — state
  by session id + byte offsets, never double-bills
- **Reports**: daily / weekly / monthly / session usage tables, JSON output
- **History baseline**: the full analyze-history report (cost-per-turn curve,
  cache-hit rate, spend by repo)
- **Slash command**: `/cccost daily --repo my-project` inside Claude Code
- **Python 3.10+ stdlib only** — no dependencies, nothing leaves your machine

| file | what it is |
| --- | --- |
| `statusline.py` | Live cost meter entry point for Claude Code's status line |
| `cccost.py` | One CLI: `daily` / `weekly` / `monthly` / `session` / `report` / `--list-repos` |
| `cccost/billing.py` | The one pricing seam: usage token classes, model resolution (`:cloud`, `[1m]`, aliases), per-turn cost, off-peak |
| `cccost/transcript.py` | Transcript shape knowledge: per-line extraction, `message.id` dedupe, session discovery, repo naming |
| `cccost/analysis.py` | Discovery-to-rows pipeline shared by every report; CSV writer |
| `cccost/reports.py` | The aggregate tables: daily / weekly / monthly / session |
| `cccost/session_state.py` | The status line's incremental per-session billing store (byte offsets per transcript file) |
| `cccost/report.py` | The analyzer's text report (byte-compat surface) |
| `commands/cccost.md` | `/cccost` slash command for Claude Code (reports from inside a session) |
| `prices.json` | Date-stamped sheet: every priced Ollama Cloud model + all current first-party Claude models, USD per 1M tokens |
| `tests/` | Synthetic fixture + checks: content-block dedupe, TTL split, model switch, unpriced models, subagents, corrupt lines |

## Quickstart

See [QUICKSTART.md](QUICKSTART.md) (3 commands) — or run `./install.sh`,
which runs the tests and does it for you. The full manual is
[INSTALL.md](INSTALL.md).

## Project

- [LICENSE](LICENSE) (MIT) · [CONTRIBUTING.md](CONTRIBUTING.md) ·
  [CHANGELOG.md](CHANGELOG.md) · [install.sh](install.sh) · CI runs the
  test suite on every push (Python 3.10 / 3.12 / 3.13)

## How billing works (the honest-billing rules)

- **The transcript is the source of truth.** Claude Code writes one JSONL
  line per content block of an assistant response, each repeating identical
  `message.usage`; summing lines over-bills 2–6×. Both tools deduplicate on
  `message.id` — the actual unit of billing.
- **Per-turn model pricing.** Sessions switch models mid-run; pricing follows
  the model that actually served each turn (`:cloud` tags and `[1m]` suffixes
  resolve to the bare model in the sheet).
- **Unpriced models are named, never silently dropped.** Missing rows bill
  $0 and are listed in every report; the live meter flags them with `⚠`.
- **`<synthetic>` lines** (locally generated responses) are known-free, not
  "unpriced model" noise.
- **Subagent spend folds into the parent session** (`subagents/*.jsonl`),
  live and in reports.
- **Off-peak: Ollama Cloud half-rate rows** (tagged `off_peak` in the sheet)
  halve via `--off-peak` **per turn by timestamp** — weekends, and weekdays
  outside 12:00–18:00 UTC (undated turns stay off-peak: understatement, never
  a spike). First-party Claude rows never inherit it.
- **Prices move.** The sheet is a snapshot (as of 2026-10-30). Copy, edit,
  `--prices` — never inline rates into code.

## Reports

Same billing core, four views, all behind the `--repo` guardrail:

```bash
cccost daily --repo my-project            # tokens + cost per day
cccost weekly --repo my-project           # ISO weeks
cccost monthly --repo my-project          # calendar months
cccost session --repo my-project          # one row per session
cccost report --repo my-project           # full baseline + CSVs
cccost daily --repo my-project --last 30  # window, not all history
cccost daily --repo my-project --json     # machine-readable
cccost models --repo my-project           # which model burns the budget
```

## Status line

Install once (see INSTALL.md), start a session and the line appears; test
it standalone:

```bash
echo '{"workspace":{"current_dir":"/tmp/demo"},"cost":{"total_cost_usd":2.47},"model":{"display_name":"GLM 5.3 Flash"}}' | python3 statusline.py
```

## Guardrail

`--repo` is required for every report — transcripts mix personal and
work-adjacent sessions, and a cost report is the kind of artifact that gets
pasted somewhere public. Inclusion is always explicit; `--list-repos` shows
repo names + counts only, so you can choose without reading content.

## Caveats

- **Plan credits, not cash**: Ollama Cloud plans (Pro/Max/Team) spend monthly
  usage credits at these token rates — figures track credits consumed. Under
  Claude subscription plans the Claude rows are "equivalent API cost".
- **Peak rates in the live meter** — off-peak halving is `--off-peak` (analyzer) only.
- **Fast mode & Haiku tiers are sheet-driven**: a claude- turn whose usage
  speed is exactly `"fast"` bills the `-fast` row (without one: base rates +
  a note); Haiku 5.5 tiers on billed input via its `tiers` key. New tiers or
  fast variants are sheet edits, not code.
- **Merging machines**: export with `cccost report` on each machine, then
  `cccost merge DIR [DIR...] --out-dir DIR` dedupes on `session_id` /
  `(session_id, turn_index)`, keeping the higher-cost (superset) read.
  Merged CSVs are view-only data — never re-billed, never relaxing `--repo`.
- **Turn = one API request** — one prompt usually costs several turns.

## Credits

Standing on open source — adapted from, and inspired by:

- **[cost-per-turn](https://www.youtube.com/watch?v=I2a0EJ67cVo)** — the origin
  of the transcript-billing data model (per-turn token billing, `message.id`
  dedupe, cache-TTL split, subagent folding, the date-stamped price sheet, and
  the required-`--repo` privacy guardrail). Its status line inspired ours; the
  live meter's self-billing from the transcript is what makes it correct for
  non-Anthropic backends.
- **[ccusage](https://github.com/ccusage/ccusage)** by
  [@ryoppippi](https://github.com/ryoppippi) (MIT) — ccusage's aggregate
  report views (daily / weekly / monthly / session) shaped this project's
  report CLI; ours is a stdlib-native take with the same guardrail and its
  own date-stamped sheet.

Both reference repos sit outside this repository; only the ideas crossed the
boundary — and the boundary is stated here. Both upstreams deserve the
goodwill: try ccusage for its multi-CLI, multi-source reports, and cost-per-turn
for the status line origin story.