---
name: "<app> Depguard Guard"
description: "Review import boundaries in <app> for hexagonal soundness; flag every domain.py adapter import, slice-to-slice edge, kernel-only violation, otel import, and dynamic-execution import, and block any relaxation of the import-linter contracts in pyproject.toml."
division: security
---

# <app> Depguard Guard

A reusable import-boundary review workflow for the `<app>` codebase. An agent (e.g. the depguard reviewer role) invokes this skill on any diff that touches `src/app/**/*.py`, `pyproject.toml`, or `tests/**/*.py`. The module invariants are domain.py purity (stdlib + `app.shared` only), no slice-to-slice imports, `app.shared` imports the standard library only, otel is CUT, and dynamic execution (`eval`, `exec`, `compile`, `__import__`, `pickle.loads`) is out of bounds — all encoded as import-linter contracts in `pyproject.toml`; the skill enforces them absolutely and reports any escape hatch.

## When to Activate

- A diff adds or modifies an import in a `domain.py` (`fastapi`, `sqlalchemy`, `asyncpg`, `alembic`, `httpx`, `uvicorn`, another feature's package) — or any transport/persistence import in what claims to be domain code.
- A diff edits the `[tool.importlinter.contracts]` block in `pyproject.toml`, or loosens a forbidden module, or adds a slice to a contract's module list.
- A new dependency is introduced whose adapter surface reaches `<app>` in src code.
- A reviewer asks for a boundary pass before approving a change that touches the import or lint surface.

Do not activate for diffs with no import surface and no `pyproject.toml` contract edit.

## Core Principles

- The contracts are absolute. They are not defaults to relax for a deadline; any edit that weakens an import-linter contract is a BLOCK.
- The import line is the boundary. A `domain.py` that carries `sqlalchemy` inside is an adapter wearing a domain costume; the fix is moving the code across the layer boundary.
- Slices never import each other. A shared shape moves down to `app.shared` through an architect decision, never as a cross-slice edge.
- import-linter is the first reviewer. `make lint` (ruff + `lint-imports`) is the gate this category mirrors; the skill catches what the linter cannot see — contract edits that revoke rules, dependency surfaces, and review-time proposals.
- Cite the invariant, then the alternative. "BLOCK — domain.py purity" is the rule; "move it to the slice's http.py or ports.py" is the review.

## Rules

- Anti-hallucination: do not invent forbidden imports that are not in the diff. Every finding cites a path and line that exists in the tree.
- Every stat needs a source. If you cite the hexagonal dependency rules, name the doc; if you cite the linter's behavior, name the import-linter contract documentation. No unsourced claims.
- Do not emit the final report as a fenced code block when raw line-anchored output is expected — the report is plain text, one finding per line, severity-prefixed.
- Verify by reading the cited file and line before reporting. A finding that cites an import the diff does not contain is a hallucination.
- Zero adapter imports in `src/app/features/*/domain.py` is the floor; the `forbidden` contract in `pyproject.toml` enforces it and `make lint` reports it. The skill enforces the contract edits and dependency surface the linter cannot see.
- otel is CUT from this template (observability = the JSON logger + `/healthz` + `/readyz`): any opentelemetry import in `src/` or `pyproject.toml` is a BLOCK.
- Zero dynamic-execution imports (`eval`, `exec`, `compile`, `__import__`, `pickle.loads`) in src code, and zero slice-to-slice imports, without an architect decision recorded in the change.

## Research References

Provenance table — fill the link column from the primary source before relying on a claim. No claim may appear in a finding without a row here.

| claim                                                       | source                                     | year | link                     |
| ----------------------------------------------------------- | ------------------------------------------ | ---- | ------------------------ |
| import-linter forbids imports by module name and contract    | import-linter documentation                | 2024 | <TODO: primary doc link> |
| domain.py purity is the hexagon's core invariant             | dependency-rules doc / hexagonal docs      | 2024 | <TODO: primary doc link> |
| Slices never import each other (vertical isolation)          | dependency-rules doc                       | 2024 | <TODO: primary doc link> |
| Layer contracts encode "dependencies point inward"           | import-linter documentation, layer type    | 2024 | <TODO: primary doc link> |

## Output Format

A line-anchored report, one finding per line, severity-prefixed, followed by a summary line. Plain text — not a fenced block:

```
BLOCK  src/app/features/widgets/domain.py:9  `import sqlalchemy` — domain.py purity violated; move it to the slice's postgres.py or ports.py.
BLOCK  src/app/features/authsignup/usecase.py:12  `app.features.widgets` — slices never import each other; route the shared shape to app.shared via the architect.
WARN   pyproject.toml:112  the forbidden contract dropped `sqlalchemy` — boundary revoked; route to architect.
PASS   src/app/features/widgets/postgres.py  no forbidden imports; the adapter layer is exactly where sqlalchemy belongs.
```

Summary line: `depguard-guard: N block(s), M warning(s), K pass — verdict: BLOCK | APPROVE`. Any non-zero BLOCK is an automatic BLOCK verdict.
