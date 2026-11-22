---
name: "ship"
description: "Cuts an <app> release: derives the bump from conventional commits, bumps the version in pyproject.toml, prepends CHANGELOG.md, opens one release PR tagged vX.Y.Z — never runs uv add/sync or commits uv.lock from the release context."
division: core
---

# <app> ship skill

> Reusable workflow for cutting an <app> release PR. An agent invokes this
> skill; the agent supplies the role, the skill supplies the workflow.

## When to Activate

Activate this skill when the request is to cut a release for <app>: determine
the version bump from commit history, bump `version` in `pyproject.toml`,
prepend a `CHANGELOG.md` entry, and open the release PR whose head lands the
`vX.Y.Z` tag. Python keeps its version in `pyproject.toml` (`[project]
version`), so that field IS bumped as part of the release — the git tag is
the second half of the same version surface, not a replacement for it.

Do NOT activate this skill when:

- The request is to scaffold a new handler or slice (use `add-handler` /
  `add-module` instead).
- The request is to file an issue or feature spec (use `spec` instead).
- There are no commits since the last version tag (nothing to ship).

## Core Principles

- Preflight before anything else: the working tree must be clean-ish (no
  unrelated unstaged changes), the current branch must not be the default
  branch, and `git log` must be reachable. `git`/`gh` are used ONLY at ship
  time — no new dependency, no publish tooling is introduced.
- The version bump is derived, never guessed: any `BREAKING CHANGE`/`!`
  commit since the last tag (or the full history if there is no tag) forces
  a major bump; any `feat` commit forces minor; otherwise patch.
- Two version surfaces, one value: `pyproject.toml` `[project] version` and
  the `vX.Y.Z` git tag always carry the same number — a release that bumps
  one and not the other is not finished.
- Never run `uv add` / `uv sync` or commit a `uv.lock` from the ship
  context: dependency bumps and resolution are a separate chore commit; the
  release commit only carries the changelog and the version field. (The
  skeleton ships no `uv.lock` — it is gitignored — INV-T3.)
- The changelog entry is derived from real `git log` subjects grouped by
  conventional-commit type; nothing is fabricated.
- One PR per release, titled with the new version, ending in `Closes #<n>`
  when the release closes a tracked issue — never a Co-Authored-By trailer.

## Rules

- Never run destructive git operations: no `--force` push, no history rewrite,
  no skipping hooks.
- Never touch `uv.lock`, `specs/openapi.yaml`, or `migrations/` as part of a
  release commit.
- Never invent changelog entries — every line traces to a real commit subject
  from `git log` since the last tag.
- Never publish a container image from this skill — that is
  `docker-publish.yml`'s job, triggered on its own path filters and gated on
  its own secrets.
- The release commit message is exactly `chore(release): v<X.Y.Z>` with no
  trailer.

## Research References

| Claim                                                    | Source   | Year   | Link   |
| -------------------------------------------------------- | -------- | ------ | ------ |
| (claim placeholder — replace with any external citation) | (source) | (year) | (link) |

## Output Format

Deliver, in order:

1. The determined bump (major/minor/patch) with the commit(s) that justified
   it.
2. The version to set in `pyproject.toml` (`[project] version`) and the tag
   to create: `v<X.Y.Z>` (semver, `v`-prefixed).
3. The prepended `CHANGELOG.md` section: `## v<X.Y.Z> — <date>` with commit
   subjects grouped by type (feat / fix / chore / etc.).
4. The release commit message: `chore(release): v<X.Y.Z>`.
5. The PR title and body: title `chore(release): v<X.Y.Z> — <summary> (Closes
   #<n>)`, body summarizing the changelog section.

Example changelog section:

```
## v0.3.0 — 2026-07-13

### Features
- feat(widgets): add priority column + queries.py projection

### Fixes
- fix(auth): reject expired jti on refresh, not just on mint
```
