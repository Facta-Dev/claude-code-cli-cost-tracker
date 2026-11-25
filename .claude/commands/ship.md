---
name: ship
description: "Cut an <app> release: version bump + CHANGELOG + release PR (no image publish)."
division: core
---

# /ship

## Delegate

Delegate to the **ship** skill. Activate when the request is to cut a release for <app> — determine the version bump from conventional commits, set `version` in `pyproject.toml`, prepend the `CHANGELOG.md` section, and open the release PR. Publishing the container image to GHCR is a separate, path-triggered `docker-publish.yml` run this command never triggers.
