# Graph Report - .  (2026-11-22)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 558 nodes · 706 edges · 66 communities (45 shown, 21 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 35 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3120ad3e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- analysis.py
- tests.py
- claude-code-cli-cost-tracker
- session_status.py
- What You Must Do When Invoked
- session_panel.py
- tests.py
- tests.py
- session_state.py
- _common.py
- Install manual
- session-status.ps1
- graphify reference: extra exports and benchmark
- run
- statusline
- tests.py
- main
- <app> API Designer
- <app> Migration Reviewer
- <app> Ownership Reviewer
- <app> Architect Agent
- <app> Build Resolver Agent
- <app> Code Explorer Agent
- <app> Code Reviewer Agent
- <app> Planner Agent
- <app> TDD Guide Agent
- <app> Depguard Reviewer
- <app> Test Author
- <app> Add Handler
- <app> Add Module
- <app> Depguard Guard
- <app> learn skill
- <app> Ownership Author
- <app> plan skill
- <app> review skill
- <app> ship skill
- <app> spec skill
- graphify reference: query, path, explain
- claude-code-cli-cost-tracker — agent instructions
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- guard-bash.sh
- /add-handler
- /add-module
- /depguard-guard
- /learn
- /ownership-author
- /plan
- /review
- /ship
- /spec
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- ccterm
- wezterm.lua
- __init__.py
- CLAUDE.md
- README.md
- extraction-spec.md
- cccost.md
- cc-status-with-cost.sh
- ccpanel
- install.sh script

## God Nodes (most connected - your core abstractions)
1. `Prices` - 15 edges
2. `main()` - 13 edges
3. `usage_tokens()` - 12 edges
4. `What You Must Do When Invoked` - 12 edges
5. `Install manual` - 12 edges
6. `build()` - 11 edges
7. `cccost()` - 11 edges
8. `claude-code-cli-cost-tracker` - 11 edges
9. `run()` - 10 edges
10. `/graphify` - 10 edges

## Surprising Connections (you probably didn't know these)
- `test_discover_skips_dangling_symlinks()` --calls--> `discover()`  [EXTRACTED]
  tests/unit/tests.py → cccost/transcript.py
- `test_wmctrl_rows_and_ancestry()` --calls--> `wmctrl_rows()`  [INFERRED]
  tests/unit/tests.py → hooks/linux/session_panel.py
- `test_wmctrl_rows_and_ancestry()` --calls--> `_ancestors()`  [INFERRED]
  tests/unit/tests.py → hooks/linux/session_panel.py
- `test_off_peak_window_semantics()` --calls--> `in_off_peak_window()`  [EXTRACTED]
  tests/unit/tests.py → cccost/billing.py
- `test_fast_mode_pricing()` --calls--> `usage_tokens()`  [EXTRACTED]
  tests/unit/tests.py → cccost/billing.py

## Import Cycles
- None detected.

## Communities (66 total, 21 thin omitted)

### Community 0 - "analysis.py"
Cohesion: 0.07
Nodes (48): build(), full_report(), list_repos(), load_prices(), Path, Session/turn analysis shared by the analyzer and the report CLI.  build() turns, Price sheet with a loud exit on a broken/undated sheet., Repo names and session counts only — no tokens, no costs, no content. (+40 more)

### Community 1 - "tests.py"
Cohesion: 0.09
Nodes (29): in_off_peak_window(), Prices, datetime, Path, The one pricing seam: usage token classes, model resolution, per-turn cost.  Eve, Ollama Cloud's off-peak: weekends, and weekdays outside 12:00-18:00 UTC., Split a raw usage block into the five separately-priced classes.      cache_crea, A date-stamped price sheet. Rates are never hardcoded in this file. (+21 more)

### Community 2 - "claude-code-cli-cost-tracker"
Cohesion: 0.07
Nodes (24): [0.1.0] — 2026-10-30, Changelog, [Unreleased], Commits, Contributing, How to work here, Invariants (do not break these), Architecture graphics (+16 more)

### Community 3 - "session_status.py"
Cohesion: 0.14
Nodes (28): backend_iterm2(), backend_linux(), backend_osascript(), backend_windows(), clip(), find_tty(), linux_session_status(), load_registry() (+20 more)

### Community 4 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 5 - "session_panel.py"
Cohesion: 0.15
Nodes (24): age(), _ancestors(), build(), claude_procs(), cut(), goto(), load_rows(), main() (+16 more)

### Community 6 - "tests.py"
Cohesion: 0.14
Nodes (17): CompletedProcess, cccost(), daily/weekly/monthly aggregate the same dollars the analyzer bills., The unified hook persists in-flight tools/subagents per session and     prints t, Which model burns the budget: cost-ordered per-model rows., The report subcommand (shared flow) and the --last window filter., Higher cost wins on key conflicts; rows union; output is sorted., merge is CSV plumbing: no --repo, no transcript path, ever. (+9 more)

### Community 7 - "tests.py"
Cohesion: 0.16
Nodes (15): _load_hook(), _load_panel(), Title = emoji + repo + state (+ cost); SessionEnd neutral; unknown events silent, write_tab_title emits an OSC 0 title sequence on the session's own pty., Rows = real claude processes: dead/reused-pid records are dropped, sessions, One block per session: ▶ marks this tab's, cost/state on the row, stale 'working, Click -> pane whose tty matches -> `wezterm cli activate-pane`; outside     WezT, Import hooks/session_status.py with its module-level dirs pointed at a temp cach (+7 more)

### Community 8 - "session_state.py"
Cohesion: 0.20
Nodes (12): bill_new_lines(), load_state(), Path, Per-session incremental billing state for the status line.  The status line rend, Price every line appended to the session's transcript files since     the last r, save_state(), state_path(), bar() (+4 more)

### Community 9 - "_common.py"
Cohesion: 0.20
Nodes (14): analyze(), Shared helpers for all test suites. Not a suite itself.  Sets up sys.path (repo, read_csv(), session_row(), turns.csv/sessions.csv column order is a contract (merge unions on it)., The report names its sheet and as-of date — a figure without it is junk., test_csv_column_contract(), test_report_header_contract() (+6 more)

### Community 10 - "Install manual"
Cohesion: 0.15
Nodes (12): 1 · Get the repo, 2 · Status line — settings.json, 3 · Reports CLI + slash command, 3b · iTerm2 session status: state + cost per session, 3c - cross-platform wiring, 3d · Linux: state in the tab title + a panel of all sessions, 4 · Environment overrides, 5 · Prices (+4 more)

### Community 11 - "session-status.ps1"
Cohesion: 0.31
Nodes (5): Get-RegPath(), Get-RunningItem(), Update-Registry(), Read-Registry(), Write-Registry()

### Community 12 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 13 - "run"
Cohesion: 0.25
Nodes (9): make_fixture(), Path, run(), Unreadable payload, or corrupt-but-valid-JSON lines, never go dark., With no --projects-dir the CLI reads $CLAUDE_CONFIG_DIR/projects (multi-profile, test_default_projects_dir_follows_claude_config_dir(), test_statusline_survives_garbage(), make_fixture() wipes leftovers; a junk session cannot haunt totals. (+1 more)

### Community 14 - "statusline"
Cohesion: 0.22
Nodes (9): statusline(), Payload cost is dead under Ollama; cost comes from the transcript,     re-render, The haiku tier turn flows through the status line too (session B)., When Claude Code provides a real cost figure, show it untouched., A turn from a model missing from the sheet shows as $0.00 ⚠., test_statusline_bills_tier_turns(), test_statusline_flags_unpriced_models(), test_statusline_payload_cost_wins_when_native() (+1 more)

### Community 15 - "tests.py"
Cohesion: 0.25
Nodes (6): Unlisted repos go nowhere: --list-repos shows names only., Running without --repo is a parser error, not a silent full history., An unknown command exits loud with the usage line., test_repo_guardrail(), test_repo_required(), test_usage_exit_contract()

### Community 16 - "main"
Cohesion: 0.46
Nodes (7): assistant(), fast_usage(), line(), main(), Path, A Claude fast-mode usage: speed is exactly the string 'fast'., usage()

### Community 17 - "<app> API Designer"
Cohesion: 0.29
Nodes (6): <app> API Designer, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 18 - "<app> Migration Reviewer"
Cohesion: 0.29
Nodes (6): <app> Migration Reviewer, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 19 - "<app> Ownership Reviewer"
Cohesion: 0.29
Nodes (6): <app> Ownership Reviewer, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 20 - "<app> Architect Agent"
Cohesion: 0.29
Nodes (6): <app> Architect Agent, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 21 - "<app> Build Resolver Agent"
Cohesion: 0.29
Nodes (6): <app> Build Resolver Agent, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 22 - "<app> Code Explorer Agent"
Cohesion: 0.29
Nodes (6): <app> Code Explorer Agent, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 23 - "<app> Code Reviewer Agent"
Cohesion: 0.29
Nodes (6): <app> Code Reviewer Agent, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 24 - "<app> Planner Agent"
Cohesion: 0.29
Nodes (6): <app> Planner Agent, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 25 - "<app> TDD Guide Agent"
Cohesion: 0.29
Nodes (6): <app> TDD Guide Agent, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 26 - "<app> Depguard Reviewer"
Cohesion: 0.29
Nodes (6): <app> Depguard Reviewer, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 27 - "<app> Test Author"
Cohesion: 0.29
Nodes (6): <app> Test Author, Core Mission, Expertise Areas, Guiding Principles, Output Format, Quality Standards

### Community 28 - "<app> Add Handler"
Cohesion: 0.29
Nodes (6): <app> Add Handler, Core Principles, Output Format, Research References, Rules, When to Activate

### Community 29 - "<app> Add Module"
Cohesion: 0.29
Nodes (6): <app> Add Module, Core Principles, Output Format, Research References, Rules, When to Activate

### Community 30 - "<app> Depguard Guard"
Cohesion: 0.29
Nodes (6): <app> Depguard Guard, Core Principles, Output Format, Research References, Rules, When to Activate

### Community 31 - "<app> learn skill"
Cohesion: 0.29
Nodes (6): <app> learn skill, Core Principles, Output Format, Research References, Rules, When to Activate

### Community 32 - "<app> Ownership Author"
Cohesion: 0.29
Nodes (6): <app> Ownership Author, Core Principles, Output Format, Research References, Rules, When to Activate

### Community 33 - "<app> plan skill"
Cohesion: 0.29
Nodes (6): <app> plan skill, Core Principles, Output Format, Research References, Rules, When to Activate

### Community 34 - "<app> review skill"
Cohesion: 0.29
Nodes (6): <app> review skill, Core Principles, Output Format, Research References, Rules, When to Activate

### Community 35 - "<app> ship skill"
Cohesion: 0.29
Nodes (6): <app> ship skill, Core Principles, Output Format, Research References, Rules, When to Activate

### Community 36 - "<app> spec skill"
Cohesion: 0.29
Nodes (6): <app> spec skill, Core Principles, Output Format, Research References, Rules, When to Activate

### Community 37 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 38 - "claude-code-cli-cost-tracker — agent instructions"
Cohesion: 0.50
Nodes (3): claude-code-cli-cost-tracker — agent instructions, graphify, Model routing (Claude Code + Ollama)

### Community 39 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 40 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 41 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 42 - "guard-bash.sh"
Cohesion: 0.83
Nodes (3): has(), has_i(), guard-bash.sh script

## Knowledge Gaps
- **187 isolated node(s):** `cc-status-with-cost.sh script`, `install.sh script`, `graphify`, `.claude — this repo's Claude Code kit`, `Core Mission` (+182 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `test_wmctrl_rows_and_ancestry()` connect `session_panel.py` to `tests.py`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Why does `Prices` connect `tests.py` to `analysis.py`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Why does `discover()` connect `analysis.py` to `tests.py`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **What connects `cccost — shared billing core for the Claude Code cost tracker.  Namespace marker`, `Session/turn analysis shared by the analyzer and the report CLI.  build() turns`, `Return (session rows, turn rows, skipped repo names).` to the rest of the system?**
  _271 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `analysis.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06545879602571596 - nodes in this community are weakly interconnected._
- **Should `tests.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09411764705882353 - nodes in this community are weakly interconnected._
- **Should `claude-code-cli-cost-tracker` be split into smaller, more focused modules?**
  _Cohesion score 0.06896551724137931 - nodes in this community are weakly interconnected._