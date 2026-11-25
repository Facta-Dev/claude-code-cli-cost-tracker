---
name: "plan"
description: "Produces a structured docs/plans/<slug>.md for a scoped <app> change: problem, constraints, design, files-to-touch, risks, and test plan."
division: core
---

# <app> plan skill

> Reusable workflow for turning a scoped `<app>` change into a written plan
> before code is touched. An agent invokes this skill; the agent supplies the
> judgment, the skill supplies the document shape.

## When to Activate

Activate this skill when a change is large enough to benefit from a written
plan before implementation: a new slice, a cross-feature refactor, a new
Alembic migration paired with a queries.py change, or any request that asks
to "plan" or "design" work on `<app>` before writing code.

Do NOT activate this skill when:

- The change is a single-file, single-purpose fix with an obvious shape (skip
  straight to implementation).
- The request is project-external, cross-repository, or multi-team
  coordination — this skill produces a project-level plan document only, not
  a cross-division workflow or durable orchestration record.
- A plan for the same slug already exists at `docs/plans/<slug>.md` and
  nothing material has changed — update the existing file instead of
  creating a duplicate.

## Core Principles

- **Project-level only.** The output is a single Markdown file under
  `docs/plans/` in the `<app>` repository. It carries no cross-division
  gating, no phase-doctrine handoff, and no dependency on any external
  orchestration runtime.
- **Six sections, always in order:** problem, constraints, design,
  files-to-touch, risks, test plan. A plan missing any section is incomplete.
- **Problem before design.** State what is broken or missing and why it
  matters before proposing a shape; a design section with no problem
  statement above it is a solution in search of a problem.
- **Files-to-touch is a real list.** Enumerate actual paths under
  `src/app/features/`, `src/app/platform/` and `src/app/bin/` (and
  `migrations/` where relevant), not a vague description of "the API layer".
- **Risks name the invariant.** Where a risk touches a module invariant
  (domain.py purity, slice isolation, an unpaired migration (empty
  `downgrade()`), a stale committed OpenAPI contract), name it explicitly
  rather than describing it generically.
- **Directory created on demand.** `docs/plans/` is not shipped with the
  skeleton; the first `/plan` invocation creates it.

## Rules

- No fabricated data: every files-to-touch entry must correspond to a path
  that either exists or is explicitly marked "new file" — never list a path
  without checking which case applies.
- Every stat needs a source: a constraint cited from an existing invariant
  (e.g. "domain.py purity") must reference where it is declared (the
  import-linter contracts in `pyproject.toml`).
- No code-fenced final output where raw output is expected: the plan
  document itself is committed as a normal Markdown file, not delivered as a
  fenced block in the response.
- One plan per slug: `docs/plans/<slug>.md`, where `<slug>` is a short
  kebab-case name for the change (e.g. `widgets-priority-column`).
- Never include a real secret or connection string in a plan document; use a
  placeholder name for any credential referenced.

## Research References

| Claim                                         | Source                                    | Year     | Link       |
| --------------------------------------------- | ----------------------------------------- | -------- | ---------- |
| `<placeholder claim>`                         | `<source file or doc>`                    | `<year>` | `<link>`   |
| domain.py purity + slice-isolation contracts  | `pyproject.toml` import-linter contracts  | —        | local file |
| Migration pairing convention (real `downgrade()`) | `migrations/versions/*_*.py` Alembic   | —        | local file |

## Output Format

Raw structured prose confirming the file was written, not a code fence:

```
### <app> plan — docs/plans/<slug>.md written

## Problem
<what is broken or missing, and why it matters>

## Constraints
<invariants, deadlines, or boundaries that shape the design>

## Design
<the proposed shape, at the level of features/ports/adapters>

## Files to touch
- <path> (new|modified)

## Risks
<named invariant risks + mitigation>

## Test plan
<how the change will be verified: pytest cases, migration up/down check,
make generate + gen-check diff, make ci>
```
