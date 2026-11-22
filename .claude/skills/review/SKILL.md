---
name: "review"
description: "Runs the <app> pre-landing review checklist across dynamic-execution justification, error-shadowing discipline, queries.py auditing, and lint cleanliness, producing a severity-ranked gate verdict against `make ci`."
division: core
---

# <app> review skill

> Reusable pre-landing review CHECKLIST for the `<app>` Python codebase. An
> agent invokes this skill; the agent supplies contextual judgment, the skill
> supplies the deterministic procedure.

## When to Activate

Activate this skill before landing any change to `src/app/**/*.py` or
`migrations/`, or whenever a request asks for a "review", "gate check", or
"pre-landing pass" on `<app>`. Also trigger on:

- A pull request touching a handler, repository adapter, or domain module.
- A request to confirm a change is safe to merge against `make ci`.
- A follow-up review after fixes from a prior `/review` pass.

Do NOT activate for documentation-only or dependency-only changes with no
`.py` or `pyproject.toml` edits. This skill COMPLEMENTS the `code-reviewer`
core agent rather than replacing it: the agent reasons freely about a diff's
intent and tradeoffs, while this skill walks the same four stack categories
in the same order every time. Do not restate the agent's prose here — the
two are consulted together, not merged.

## Core Principles

- **Checklist, not judgment.** Four fixed categories, always in this order:
  dynamic-execution justification, error-handling discipline, queries.py
  auditing, lint cleanliness.
- **No dynamic execution in src source.** Every use of `eval`, `exec`,
  `compile`, `__import__`, or `pickle.loads` in the diff needs an inline
  comment naming the invariant it upholds; an unjustified dynamic-execution
  call is a BLOCK regardless of what the tooling allows.
- **No swallowed errors in library paths.** `src/app/shared/`,
  `src/app/platform/` and `src/app/features/*/usecase.py` must raise errors
  that wrap a stable `Code` and propagate; a swallowed exception (a bare
  `except:`, an `except ValueError: pass`, an ignored `await` result) is
  acceptable only in `tests/`, in `src/app/bin/worker.py` shutdown paths, or
  with an inline comment proving the invariant that makes ignoring it safe.
- **queries.py auditing.** Every statement added or changed in a slice's
  `queries.py` is checked against the migration it targets: column names and
  nullability must match the paired revision's `upgrade()`; a hand-built
  runtime SQL string (an f-string interpolating a value into the statement)
  bypassing the committed `queries.py` is flagged.
- **lint cleanliness.** The diff must not introduce a blanket `# noqa` that
  silences a ruff or import-linter rule without an inline justification
  comment; `make lint` (ruff + `lint-imports`) is the gate this category
  mirrors.

## Rules

- No fabricated data: do not invent file paths, line numbers, or query
  invocations. If a file was not read this session, list it under "not
  reviewed" instead of guessing its contents.
- Every stat needs a source: a claim like "the adapter ignores the scan error
  at line 40" needs the file/line actually read, or an explicit "unverified"
  tag.
- No code-fenced final output where raw output is expected: the verdict in
  Output Format below is raw structured prose, never a fenced block.
- Read each touched file before reporting on it; unread files are listed
  separately as "not reviewed (not read)".
- BLOCK only on a real finding: an unjustified dynamic-execution call, a
  library-path swallowed exception with no inline proof, a queries.py entry
  whose SQL interpolates values or whose columns do not match the migration,
  or a blanket `# noqa` with no justification.
- WARN on style-grade issues (a justification comment that is thin but
  present, a runtime query that could become a queries.py entry but is not
  itself unsound).
- APPROVE only when all four categories show no BLOCK-level finding.

## Research References

Provenance table — fill claim/source year, link from primary sources actually
read this session. Leave the placeholder row if a claim is unverified.

| Claim                                                   | Source                              | Year     | Link       |
| ------------------------------------------------------- | ----------------------------------- | -------- | ---------- |
| `<placeholder claim>`                                   | `<source file or doc>`              | `<year>` | `<link>`   |
| forbidden/layers/independence contracts                  | `pyproject.toml` import-linter      | —        | local file |
| Migration pairing convention (real `downgrade()`)       | `migrations/versions/*_*.py` Alembic | —        | local file |

## Output Format

Raw structured prose (not a code fence when rendered as the final verdict):

```
### <app> review — pre-landing checklist

Gate: make ci = ruff format:check + mypy strict + ruff + import-linter + gen-check + pytest

Findings:
- [BLOCK|WARN] dynamic-execution @ <file>:<line> — <what> | fix: <suggestion>
- [BLOCK|WARN] error-discipline @ <file>:<line> — <what> | fix: <suggestion>
- [BLOCK|WARN] query-audit @ <file>:<line> — <what> | fix: <suggestion>
- [BLOCK|WARN] lint @ <file>:<line> — <what> | fix: <suggestion>

Not reviewed (not read):
- <file>

Verdict: APPROVE | WARN | BLOCK
```
