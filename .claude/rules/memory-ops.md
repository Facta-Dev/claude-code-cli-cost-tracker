# Memory-first: codegraph / graphify / repo memories before grep

- STRUCTURAL questions about code in a repo with a `.codegraph/` index: your UserPromptSubmit hook already injects `<codegraph_context>` — treat it as the primary source; if absent or insufficient, run ONE `codegraph explore "<symbols or question>"` (or `codegraph impact` / `affected` for blast radius / test impact) BEFORE grep/find/Read. Do NOT re-read files the context already showed verbatim.
- Architecture, doc, or cross-file-relationship questions in a repo with `graphify-out/graph.json`: query graphify first (`graphify query "<question>" / path / explain / affected`) — see the `/graphify` skill. Grep only the residue.
- Repo operational memories: consult the repo `MEMORY.md` (if present) and `docs/changelog/` before re-deriving history or process facts.
- Keep indexes fresh: after edits the knowledge-sync hook runs `codegraph sync` + `graphify update` in the background — never re-index manually inside a turn; if `codegraph status` reports stale after edits, run `codegraph sync -q` once.
- Planning: for multi-file plans, build context with `codegraph context "<task>"` (plan-shaped tool) instead of reading many files.
