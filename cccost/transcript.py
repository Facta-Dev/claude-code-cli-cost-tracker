"""Transcript shape knowledge: what one JSONL line says about one turn.

Claude Code writes assistant responses as one JSONL line per content block
(thinking, text, each tool_use) — each repeating the identical
message.usage of the API response that produced it. Everything that knows
that shape lives here; the two walkers stay separate because their dedup
state models are opposite (full-file set vs persisted byte offsets).
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from cccost.billing import usage_tokens


def repo_of(cwd: str | None, slug: str) -> str:
    """Best-effort repo name for a session.

    Prefer the working directory recorded on the line; fall back to the
    slugified-cwd directory name Claude Code uses for the project folder.
    A cwd of ~/repos/glutenornot.com/mobile belongs to repo glutenornot.com.
    """
    if cwd:
        parts = Path(cwd).parts
        for anchor in ("repos", "demos", "Documents"):
            if anchor in parts:
                i = parts.index(anchor)
                if i + 1 < len(parts):
                    return parts[i + 1]
                return anchor
        return Path(cwd).name
    name = slug.lstrip("-").replace("Users-", "", 1)
    return name.rsplit("-", 1)[-1] or slug


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def turn_from_obj(obj: object) -> dict | None:
    """Per-line extract: one assistant-usage line -> one turn record, or None.

    Non-assistant lines, lines without usage, and JSONL lines that are not
    objects (a bare JSON array is legal JSON) all fall out here — no walker
    ever needs to know the shape itself.
    """
    if not isinstance(obj, dict) or obj.get("type") != "assistant":
        return None
    message = obj.get("message") or {}
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None  # a truthy but non-dict usage (hand-edit, partial write) is not billable
    mid = message.get("id")
    return {
        "message_id": mid or "",
        "model": message.get("model") or "",
        "timestamp": obj.get("timestamp"),
        "cwd": obj.get("cwd"),
        "is_sidechain": bool(obj.get("isSidechain")),
        "agent_id": obj.get("agentId") or "",
        "version": obj.get("version") or "",
        "tokens": usage_tokens(usage),
    }


def iter_turns(path: Path):
    """Yield one record per *API request*, deduplicated on message.id.

    Summing assistant lines over-counts real spend (the identical usage is
    repeated per content block); message.id is the actual unit of billing.
    """
    seen: set[str] = set()
    with path.open(errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            turn = turn_from_obj(obj)
            if turn is None:
                continue
            mid = turn["message_id"]
            if mid:
                if mid in seen:
                    continue
                seen.add(mid)
            yield turn


def discover(projects_dir: Path) -> dict[tuple[str, str], list[Path]]:
    """Map session id -> (project slug, [transcript paths]).

    Subagent transcripts live at <project>/<session-id>/subagents/*.jsonl
    and carry the parent session's id. They are real spend on the parent
    session, so they are folded in rather than treated as their own.
    """
    sessions: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for path in sorted(projects_dir.rglob("*.jsonl")):
        rel = path.relative_to(projects_dir)
        slug = rel.parts[0]
        if len(rel.parts) == 2:
            session_id = path.stem
        elif len(rel.parts) >= 3:
            session_id = rel.parts[1]  # <project>/<session-id>/subagents/agent-*.jsonl
        else:
            continue
        sessions[(slug, session_id)].append(path)
    return sessions