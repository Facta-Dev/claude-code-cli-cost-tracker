---
name: "<app> Add Module"
description: "Scaffold a new feature slice (src/app/features/<slug>) in <app>: ports.py consumer-owned protocols, usecase.py, module.py register(), Deps wiring in src/app/bin/api.py, hexagonal direction, and the fake-backed test gate, as one change."
division: backend
---

# <app> Add Module

A reusable scaffolding workflow for adding a new feature slice to the `<app>` codebase. An agent (e.g. the API designer or ownership reviewer role) invokes this skill to produce the slice declaration, the dependency wiring, the module doc, and the boundary check together — so a new slice never lands without its registration and its boundary discipline. The output is a wiring sketch plus a boundary checklist.

## When to Activate

- A new vertical slice (`src/app/features/<slug>/`) is requested.
- An existing slice needs a new dependency on `app.platform` or `app.shared`.
- The hexagonal dependency direction must be verified after a wiring change (adapters must not depend on use cases; the kernel must not depend on anything internal).
- A reviewer asks for the module + wiring bundle before approving an internal-structure change.

Do not activate for in-slice refactors that add no new slice and no new cross-feature dependency.

## Core Principles

- The slice is the unit of reuse. A new slice is a new `src/app/features/<slug>/` directory with domain.py / ports.py / usecase.py / http.py / postgres.py / module.py / queries.py — together.
- Hexagonal direction is invariant. `app.shared` (kernel) imports only the standard library; `app.platform` imports shared + third-party drivers; features import shared + platform-declared ports; `src/app/bin` depends on all. A wire that reverses this is a BLOCK.
- Ports are consumer-defined. `ports.py` declares the `typing.Protocol` interfaces the slice's use cases need (defined BY the consumer); `postgres.py` is the production adapter (SQLAlchemy over the slice's `queries.py` statements); the fake lives in `tests/fakes.py`.
- The module doc is the contract. The slice's files open with a docstring stating what the slice owns and what it depends on.
- Slices never import each other. A shared shape moves down to `app.shared` through an architect decision, never as a cross-slice import edge.

## Rules

- Anti-hallucination: do not invent import paths or import edges that are not in the tree. Every wiring step cites a file that exists or is being added.
- Every stat needs a source. If you cite the hexagonal architecture, cite the dependency-rules doc; if you cite the import-linter contract semantics, cite the import-linter documentation. No unsourced claims.
- Do not emit the final sketch as a fenced code block when raw output is expected — the sketch is plain text with labelled sections (slice / deps / module.py / direction / checklist).
- Verify the cited files exist before reporting; a wiring step that cites a `Deps` field that is not being added is a hallucination.
- A new slice must appear in `src/app/features/` AND be wired via `register(app, service)` in `src/app/bin/api.py`; one without the other is a REVISE.
- `app.shared` must not depend on any other internal feature; `app.platform` must depend only on shared. A reverse edge is a BLOCK.
- Adapter code lives only in `postgres.py` (SQLAlchemy) and `http.py` (FastAPI); `domain.py` stays pure (stdlib + `app.shared` only) or the import-linter forbidden contract breaks the build.

## Research References

Provenance table — fill the link column from the primary source before relying on a claim. No claim may appear in a finding without a row here.

| claim                                                                | source                                    | year | link                     |
| -------------------------------------------------------------------- | ----------------------------------------- | ---- | ------------------------ |
| Hexagonal architecture: ports are consumer-defined interfaces        | dependency-rules doc / hexagonal docs    | 2024 | <TODO: primary doc link> |
| import-linter encodes layer, forbidden and independence contracts    | import-linter documentation               | 2024 | <TODO: primary doc link> |
| `typing.Protocol` is the structural-typing port idiom in Python      | Python typing documentation               | 2024 | <TODO: primary doc link> |
| `uv sync` resolves pyproject.toml post-rename (no lockfile ships)    | uv documentation                          | 2024 | <TODO: primary doc link> |

## Output Format

A wiring sketch plus a boundary checklist, anchored to the module root `pyproject.toml`. Plain text — not a fenced block:

```
MODULE  src/app/features/<slug>

  files:
    domain.py    -> pure domain types (stdlib + app.shared imports only)
    ports.py     -> consumer-owned protocols (DB, clock, idgen, publisher)
    usecase.py   -> orchestration over the ports
    http.py      -> build_router(service) + pydantic v2 models
    postgres.py  -> SQLAlchemy adapter over the slice's queries.py
    module.py    -> register(app, service) route mounting
    queries.py   -> sqlalchemy.text() statements with named parameters

  deps:
    pyproject.toml       -> any new dependency declared once
    src/app/bin/api.py   -> construct the adapter, pass it in the slice's service
    module.py            -> register(app, service) joined to the shared app

  direction:
    app.shared   <- (nothing internal)
    app.platform <- app.shared + drivers
    app.features.<slug> <- app.shared + its declared ports   (OK: inward)

CHECKLIST
  [ ] slice declared under src/app/features/<slug>/ with the file set above
  [ ] Deps wired once in src/app/bin/api.py; register(app, service) mounted
  [ ] ports are consumer-defined; exactly one production adapter + one fake
  [ ] dependency direction is inward (app.shared imports stdlib only)
  [ ] fakes live in tests/fakes.py (never imported from src/app)
  [ ] make lint green (import-linter contracts); make ci green
```

Summary line: `add-module: N module(s) added, M wiring step(s) — verdict: APPROVE | REVISE`.
