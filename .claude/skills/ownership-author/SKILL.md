---
name: "<app> Ownership Author"
description: "Review aliasing, locking, and async-propagation patterns in <app> modules; produce a line-anchored report of shared-state interleaving, lock placement, and port protocol wiring across the slice before the diff lands."
division: backend
---

# <app> Ownership Author

A reusable review workflow for aliasing and concurrency correctness in the `<app>` Python codebase. An agent (e.g. the ownership reviewer role) invokes this skill on any diff that touches `src/app/features/<slug>/**/*.py` or `src/app/platform/**/*.py`; the skill is the workflow, the agent is the role. The output is a line-anchored report, not a rewrite.

## When to Activate

- A diff modifies a `Deps` field, a use case, a handler in `http.py`, or any protocol wiring in `ports.py`.
- Shared state is introduced or mutated (a hub room registry, an outbox worker, a cache) across concurrent async flows.
- Cancellation is dropped, swallowed, or replaced in the request path, or an async task outlives its request.
- A reviewer asks for an ownership pass before approving a change that crosses the asyncio request concurrency model.

Do not activate for pure formatting, doc-only, or migration-only diffs.

## Core Principles

- Passes mypy is not correct. A slice alias that passes `make vet` and interleaves badly on the second concurrent request is a bug this skill owns.
- The composition root stays thin. `src/app/bin/api.py` wires consumer-defined protocols into `Deps`; logic lives in the use cases.
- Never reach for global mutable singletons (or dynamic-execution tricks) to fix sharing. The fix is a copy, an owned queue, or an explicit lock discipline.
- Cite the failure mode, not the rule. "Shared-state race" is the rule; "races on the second concurrent request because asyncio serves coroutines concurrently on one event loop" is the review.
- Keep critical sections synchronous: no `await` inside a section another request can observe half-mutated; serialize through an owner loop (a single worker/consumer) when ownership must move; `asyncio.gather` only for independent work — never hold a lock across a long I/O wait.

## Rules

- Anti-hallucination: do not fabricate file paths, line numbers, or diagnostics. Every finding must cite a path and line that exists in the diff or the working tree.
- Every stat needs a source. If you claim "races on the second request", cite the asyncio concurrency model; if you cite a compiler or lint check, name it (`mypy --strict`, ruff's `ASYNC` rules, `asyncio.Lock` semantics). No unsourced numbers.
- Do not emit the final review as a fenced code block when raw line-anchored output is expected — the report is plain text with one finding per line, severity-prefixed.
- Verify claims against the tree before reporting: read the cited file and line. A finding that cites a line the diff does not contain is a hallucination.
- `Deps` fields stay use cases and consumer-defined protocols; a field that inlines a service or another slice's type is a BLOCK.
- No dynamic-execution escape hatch (`eval`, `exec`, `compile`, `__import__`) to paper over sharing; src code importing these is a BLOCK. Propose the safe alternative (`copy.deepcopy`, an owned queue, an explicit copy) instead.

## Research References

Provenance table — fill the link column from the primary source before relying on a claim. No claim may appear in a finding without a row here.

| claim                                                                     | source                                | year | link                     |
| ------------------------------------------------------------------------- | ------------------------------------- | ---- | ------------------------ |
| asyncio runs coroutines concurrently on one event loop; awaits interleave | Python asyncio documentation          | 2024 | <TODO: primary doc link> |
| `asyncio.Lock` serializes a critical section; it is not reentrant         | Python asyncio documentation          | 2024 | <TODO: primary doc link> |
| Cancelled tasks raise `asyncio.CancelledError` at the await point        | Python asyncio documentation          | 2024 | <TODO: primary doc link> |
| Objects/lists share references across assignment; a deep copy needs copy | Python copy documentation             | 2024 | <TODO: primary doc link> |

## Output Format

A line-anchored report, one finding per line, severity-prefixed, followed by a summary line. Plain text — not a fenced block:

```
BLOCK  src/app/platform/realtime/hub.py:42  the room registry is mutated from WS callbacks with no ownership boundary — interleaves on the second concurrent connection; serialize through an owner loop or guard the mutation.
WARN   src/app/features/widgets/postgres.py:18  list() returns a shared row list; callers can mutate it — return a copied/frozen variant.
PASS   src/app/features/widgets/usecase.py  the stop event flows from the worker into the long-lived loops.
```

Summary line: `ownership-author: N block(s), M warning(s), K pass — verdict: BLOCK | APPROVE`.
