# claude-code-cli-cost-tracker — agent instructions

<!-- model-routing:ollama -->
## Model routing (Claude Code + Ollama)

Runbook: `facta-playbook/CLAUDE_CODE_ROUTING_MODELS_OLLAMA.md`.

- Tier aliases resolve through `~/.claude/settings.json`: `opus` = escalation
  (`deepseek-v4-pro:cloud`), `sonnet` = workhorse (`glm-5.3-flash:cloud`),
  `haiku` = cheap digging (`minimax-m3.1-flash:cloud`).
- Consult the `advisor` subagent before locking a plan, when the same error
  reappears twice, and before declaring a task done. Pass concrete context
  (plan, diff, test output) — not the whole repo.
- Escalate with `/model opus` for design decisions or after two failed
  attempts; return to `sonnet` when the task is done.
- All code, comments, tests, specs, and documentation are generated in English.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
