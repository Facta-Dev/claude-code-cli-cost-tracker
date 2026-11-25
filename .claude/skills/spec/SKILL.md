---
name: "spec"
description: "Interrogates an <app> feature idea into a scoped issue body, fail-closed redaction-scans it, dedupes against open issues, then files it with gh issue create."
division: core
---

# <app> spec skill

> Reusable workflow for turning an <app> feature idea into a well-scoped
> GitHub issue. An agent invokes this skill; the agent supplies the role, the
> skill supplies the workflow.

## When to Activate

Activate this skill when the request is to turn an idea, bug report, or
feature request for <app> into a filed GitHub issue: elicit the problem,
draft the issue body, redact it, dedupe it, and file it.

Do NOT activate this skill when:

- The request already has an open issue number to work against (go straight
  to implementation).
- The request is to cut a release (use `ship` instead).
- The draft would need to include a real secret or credential (a
  `<APP>_DATABASE_URL`, a `<APP>_JWT_SECRET` value) to make sense — stop and
  ask the requester to redact first instead of drafting around it.

## Core Principles

- Interrogate before drafting: elicit the problem statement, motivation, scope
  boundaries, acceptance criteria, and which invariants the change touches —
  draft the issue body locally before any network call.
- Redaction is fail-closed and runs BEFORE any `gh` invocation, on the FULL
  draft (title + body): private-key blocks (`-----BEGIN`), JWT-shaped tokens
  (`eyJ...`), AWS access keys (`AKIA[0-9A-Z]{16}`), `ghp_`/`gho_`/
  `github_pat_` tokens, bearer/authorization header values,
  `password=`/`secret=`/`token=` assignments, email addresses, IPv4
  addresses, and `.env`-style `KEY=value` secrets. Any hit stops the flow,
  prints the offending lines masked, and requires an explicit re-run — never
  an automatic mask-and-continue.
- Dedupe only after redaction: `gh issue list --search` and `gh search issues`
  are built from the already-scanned title only, never from unredacted
  content.
- One issue per idea: if a plausible duplicate is found, show it and stop for
  confirmation rather than filing a near-duplicate.

## Rules

- The redaction scan gates every network-bound `gh` call — it runs strictly
  before both the dedupe search and the create step, with no exceptions.
- Never auto-continue past a redaction hit; the requester must explicitly
  confirm a re-run after fixing the draft.
- Never fabricate acceptance criteria or invariant references the requester
  did not state or the codebase does not support — ask if unclear.
- `gh issue create` uses only the scanned, confirmed title and body.
- No Co-Authored-By trailer or attribution footer in the issue body.

## Research References

| Claim                                                    | Source   | Year   | Link   |
| -------------------------------------------------------- | -------- | ------ | ------ |
| (claim placeholder — replace with any external citation) | (source) | (year) | (link) |

## Output Format

Deliver, in order:

1. The interrogation summary: problem, motivation, scope, acceptance
   criteria, invariants touched.
2. The redaction-scan result: PASS (no hits) or the masked offending lines
   plus a stop-and-confirm prompt.
3. The dedupe result: no candidate found, or the candidate issue link plus a
   stop-and-confirm prompt.
4. The final `gh issue create --title ... --body ...` invocation and the
   resulting issue URL.

Example redaction stop:

```
spec: REDACTION HIT — <APP>_JWT_SECRET=**** on draft line 9. Fix the draft
and re-run explicitly; no auto-continue.
```
