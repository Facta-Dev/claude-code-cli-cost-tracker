---
name: "learn"
description: "Appends a one-line lesson to <app>'s project-local .claude/learnings.jsonl and shows how to consult prior entries before repeating similar work."
division: core
---

# <app> learn skill

> Reusable workflow for capturing a durable, project-local lesson learned
> while working on `<app>`. An agent invokes this skill; the agent supplies
> the lesson, the skill supplies the append + consult procedure.

## When to Activate

Activate this skill when a session surfaces a lesson worth remembering for
`<app>`: a recurring pitfall, a pattern that worked, or a team preference
discovered mid-task. Typical triggers:

- A bug traced to a root cause that will recur if unrecorded (e.g. a migration
  shipped with an empty `downgrade()` — no paired rollback).
- A workaround that should become the default approach next time.
- A stated preference from a reviewer or the requester that should persist
  beyond this session.

Do NOT activate this skill for one-off facts with no future recurrence value,
or to record anything resembling a secret, credential, or `<APP>_DATABASE_URL`
value — the log is committed to the project and is not a secret store.

## Core Principles

- **Append-only.** `.claude/learnings.jsonl` is never rewritten or
  reordered; each `/learn` invocation adds exactly one line at the end.
  Never parse-and-rewrite prior lines.
- **Consult before you repeat.** Before starting work that resembles a past
  pitfall class (a migration, an import-boundary edge, an auth flow), grep
  `.claude/learnings.jsonl` for the relevant `kind` first.
- **Deliberately independent of any cross-project runtime.** This log is
  local to the generated `<app>` project only — it does not sync to, read
  from, or depend on any external multi-tenant orchestration store; a fresh
  clone of `<app>` starts with no learnings until the first `/learn` call.
- **One lesson, one line.** A JSONL entry is a single fact, not a running
  narrative; if a session produces three lessons, append three lines.
- **Created on first use, not shipped.** The skeleton ships no
  `.claude/learnings.jsonl`; the file is created by the first successful
  append.

## Rules

- No fabricated data: only append a lesson actually observed this session —
  never invent a plausible-sounding pitfall to pad the log.
- Every stat needs a source: the `refs` array must cite a real `file:line`,
  issue number, or URL from this session; an empty `refs` array is acceptable
  only when no such reference exists (a pure preference statement).
- No code-fenced final output where raw output is expected: report the
  appended line as raw text, not inside a fenced block, so it is easy to
  copy-verify against the file.
- Append via pure bash, no `jq`: use
  `printf '%s\n' "{...}" >> .claude/learnings.jsonl`. Never pipe through a
  JSON-mutating tool that could reformat or reorder prior lines.
- Escape embedded double quotes in `note` before appending
  (`\"` inside the JSON string), or the line will not parse as valid JSON.
- Never append a line containing a password, token, key, or connection
  string value — reference the file/line where the issue lives instead.

## Research References

| Claim                                       | Source                 | Year     | Link                  |
| ------------------------------------------- | ---------------------- | -------- | --------------------- |
| `<placeholder claim>`                       | `<source file or doc>` | `<year>` | `<link>`              |
| JSON Lines format (one JSON value per line) | jsonlines.org          | 2024     | https://jsonlines.org |

## Output Format

Raw structured prose, not a code fence:

```
### <app> learn — entry appended

File: .claude/learnings.jsonl
Line: {"ts":"<ISO-8601 UTC>","kind":"pattern|pitfall|preference","note":"<one-line lesson>","refs":["<file:line | issue# | url>"]}

Consult-first reminder: grep '"kind":"<kind>"' .claude/learnings.jsonl before
starting similar work.
```
