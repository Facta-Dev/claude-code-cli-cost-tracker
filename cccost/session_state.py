"""Per-session incremental billing state for the status line.

The status line renders every few seconds; it must not re-price history it
has already billed. One state file per session remembers, per transcript
file, the byte offset already consumed — each render bills only the lines
that appeared since. A compacted/rewritten (shrunk) transcript re-reads
from scratch rather than silently under-billing.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

from cccost.transcript import turn_from_obj

CACHE_DIR = os.environ.get("CC_COST_CACHE_DIR") or os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
    "claude-cost-tracker",
)


def state_path(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
    return Path(CACHE_DIR) / f"{safe}.json"


def load_state(session_id: str) -> dict:
    try:
        with open(state_path(session_id), encoding="utf-8") as fh:
            state = json.load(fh)
        return state if isinstance(state, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def reset_state(transcript_path: str) -> dict:
    return {"path": transcript_path, "files": {}, "cost": 0.0, "billed": [], "unpriced": []}


def save_state(session_id: str, state: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    target = state_path(session_id)
    # pid-suffixed temp: overlapping renders never publish each other's
    # half-written file (a fixed .tmp name could), and os.replace is atomic.
    tmp = f"{target}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, target)
    except OSError:
        pass  # a failed cache write must never break the status line


def bill_new_lines(state: dict, transcript_path: str, prices) -> None:
    """Price every line appended to the session's transcript files since
    the last render, storing byte offsets so nothing is billed twice."""
    files: dict[str, int] = dict(state.get("files") or {})
    files[transcript_path] = files.get(transcript_path, 0)

    # Subagent transcripts live next to the main file and bill to the same
    # session: <slug>/<session-id>/subagents/*.jsonl
    sid_dir = Path(transcript_path).parent / Path(transcript_path).stem / "subagents"
    for sub in sorted(glob.glob(str(sid_dir / "*.jsonl"))):
        files.setdefault(sub, 0)

    billed: list[str] = list(state.get("billed") or [])
    unpriced = list(state.get("unpriced") or [])
    cost = float(state.get("cost") or 0.0)

    for path in sorted(files):
        offset = files[path]
        try:
            size = os.path.getsize(path)
        except OSError:
            files.pop(path, None)
            continue
        offset = min(offset, size)  # compacted/rewritten -> re-read from scratch
        with open(path, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
        if not chunk:
            continue
        cut = chunk.rfind(b"\n")  # never bill a half-written last line
        if cut == -1:
            continue
        for line in chunk[:cut].split(b"\n"):
            try:
                turn = turn_from_obj(json.loads(line.decode("utf-8", "replace")))
            except json.JSONDecodeError:  # decode("replace") above cannot raise UnicodeDecodeError
                continue
            if turn is None:
                continue  # non-assistant or usage-less line — no spend
            mid = turn["message_id"]
            if mid and mid in billed:
                continue  # one line per content block repeats identical usage
            c = prices.cost(turn["model"], turn["tokens"], turn["timestamp"], fast=turn["fast"])
            if c is None:
                if turn["model"] and turn["model"] not in unpriced:
                    unpriced.append(turn["model"])
            else:
                cost += c
            if mid:
                billed.append(mid)
        files[path] = offset + cut + 1

    state["files"] = files
    # Keep the newest ids; insertion order, not lexicographic — the oldest
    # can never re-bill after a re-read-from-zero event, the cap just ages out
    # ids that can only be reached by re-reading from scratch (cost stays
    # correct there anyway, as it recomputes the whole file).
    state["billed"] = billed[-4096:]
    state["unpriced"] = unpriced[-8:]
    state["cost"] = cost