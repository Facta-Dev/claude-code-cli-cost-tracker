#!/usr/bin/env python3
"""Live cost meter for Claude Code's status line.

claude-code-cli-cost-tracker

Unlike the upstream cost-per-turn statusline, this does not trust
cost.total_cost_usd: when Claude Code runs against Ollama Cloud the
response comes from a non-Anthropic backend, so Claude Code cannot price
it. Instead every turn is billed here, from the session transcript
(Claude Code already writes per-turn token usage to .jsonl) against the
date-stamped prices.json sheet.

Transcript parsing is incremental: state keyed by session id remembers a
byte offset per transcript file, so each render only prices the lines
that appeared since last time — cost is live without re-reading history
that was already billed.

Stdlib only. Nothing leaves the machine.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")

CACHE_DIR = os.environ.get("CC_COST_CACHE_DIR") or os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
    "claude-cost-tracker",
)
PRICES_PATH = (
    os.environ.get("CC_COST_PRICES")
    or str(Path(__file__).resolve().parent / "prices.json")
)

# colors -----------------------------------------------------------------


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


BLUE = "34"
CYAN = "36"
GREEN = "32"
YELLOW = "33"
RED = "31"
DIM = "2"

BAR_WIDTH = 8


def bar(pct: int) -> str:
    filled = int(pct * BAR_WIDTH / 100)
    return "▓" * filled + "░" * (BAR_WIDTH - filled)


# prices (same rules as analyze-history.py) -------------------------------


def load_prices() -> dict:
    with open(PRICES_PATH, encoding="utf-8") as fh:
        sheet = json.load(fh)
    if not sheet.get("as_of"):
        raise ValueError(f"{PRICES_PATH}: price sheet has no 'as_of' date")
    return sheet


def resolve(model: str, sheet: dict) -> str:
    models = sheet.get("models", {})
    aliases = {k: v for k, v in (sheet.get("aliases") or {}).items() if not k.startswith("_")}
    if model in models:
        return model
    if model in aliases:
        return aliases[model]
    # A bare "[1m]"-style suffix is a context-window selection, not a tier.
    if "[" in model:
        base = model.split("[", 1)[0]
        if base in models or base in aliases:
            return base
    # ":cloud" marks an Ollama-hosted tag; the sheet is keyed by the bare id.
    if model.endswith(":cloud"):
        return resolve(model[: -len(":cloud")], sheet)
    return model


def usage_tokens(usage: dict) -> dict[str, int]:
    """Split raw usage into the five separately-priced classes.

    Ollama Cloud has no separate cache-write rate, so writes bill at the
    input rate; the TTL split still matters for native-Anthropic sessions.
    Transcripts missing the TTL detail fall back to the 5m bucket.
    """
    creation = usage.get("cache_creation") or {}
    w1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
    w5m = int(creation.get("ephemeral_5m_input_tokens") or 0)
    total = int(usage.get("cache_creation_input_tokens") or 0)
    if w1h + w5m == 0 and total:
        w5m = total
    return {
        "input": int(usage.get("input_tokens") or 0),
        "output": int(usage.get("output_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write_5m": w5m,
        "cache_write_1h": w1h,
    }


def turn_cost(model: str, tokens: dict[str, int], sheet: dict) -> float | None:
    """USD for one turn. None when the model is not on the price sheet."""
    if model == "<synthetic>":
        return 0.0  # locally generated response; not provider spend
    key = resolve(model, sheet)
    rates = sheet.get("models", {}).get(key)
    if rates is None:
        return None
    return sum(tokens[f] * rates[f] for f in TOKEN_FIELDS) / 1_000_000


# transcript billing ------------------------------------------------------


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


def reset_state(session_id: str, transcript_path: str) -> dict:
    return {"path": transcript_path, "files": {}, "cost": 0.0, "billed": [], "unpriced": []}


def save_state(session_id: str, state: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    target = state_path(session_id)
    tmp = str(target) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, target)
    except OSError:
        pass  # a failed cache write must never break the status line


def bill_new_lines(state: dict, transcript_path: str, sheet: dict) -> None:
    """Price every line appended to the session's transcript files since
    the last render, storing byte offsets so nothing is billed twice."""
    files: dict[str, int] = dict(state.get("files") or {})
    files[transcript_path] = files.get(transcript_path, 0)

    # Subagent transcripts live next to the main file and bill to the same
    # session: <slug>/<session-id>/subagents/*.jsonl
    sid_dir = Path(transcript_path).parent / Path(transcript_path).stem / "subagents"
    for sub in sorted(glob.glob(str(sid_dir / "*.jsonl"))):
        files.setdefault(sub, 0)

    billed = set(state.get("billed") or [])
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
                obj = json.loads(line.decode("utf-8", "replace"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            message = (obj.get("message") or {}) if isinstance(obj, dict) else {}
            usage = message.get("usage")
            if (obj.get("type") != "assistant") or not isinstance(usage, dict):
                continue
            mid = message.get("id")
            if mid and mid in billed:
                continue  # one line per content block repeats identical usage
            tokens = usage_tokens(usage)
            c = turn_cost(str(message.get("model") or ""), tokens, sheet)
            if c is None:
                name = str(message.get("model") or "")
                if name and name not in unpriced:
                    unpriced.append(name)
            else:
                cost += c
            if mid:
                billed.add(mid)
        files[path] = offset + cut + 1

    state["files"] = files
    state["billed"] = sorted(billed)[-4096:]
    state["unpriced"] = unpriced[-8:]
    state["cost"] = cost


# status line -------------------------------------------------------------


def minimal_line(payload: dict) -> None:
    cwd = ((payload.get("workspace") or {}).get("current_dir") or payload.get("cwd") or "?")
    cost = ((payload.get("cost") or {}).get("total_cost_usd")) or 0
    model = (payload.get("model") or {}).get("display_name") or "?"
    print(f"  📁 {os.path.basename(cwd)} │ ${cost:.2f} ⚠ │ ◆ {model}")


def render(payload: dict) -> None:
    cwd_dir = ((payload.get("workspace") or {}).get("current_dir")) or payload.get("cwd") or ""
    dirname = os.path.basename(cwd_dir) if cwd_dir else "?"
    cost_block = payload.get("cost") or {}

    duration_ms = cost_block.get("total_duration_ms") or 0
    duration = f"{int(duration_ms // 60000)}m {int(duration_ms % 60000) // 1000:02d}s"

    added = int(cost_block.get("total_lines_added") or 0)
    removed = int(cost_block.get("total_lines_removed") or 0)

    ctx = payload.get("context_window") or {}
    pct = int(ctx.get("used_percentage") or 0)
    ctx_size = ctx.get("context_window_size") or 200_000
    cur = ctx.get("current_usage") or {}
    used = sum(
        int(cur.get(k) or 0)
        for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    )
    used_k = f"{used // 1000}k" if used >= 1000 else str(used)
    ctx_color = RED if pct >= 90 else YELLOW if pct >= 70 else GREEN

    model = (payload.get("model") or {}).get("display_name") or "?"

    # Session cost: self-billed from the transcript whenever Claude Code's own
    # figure is zero (its pricing can't know non-Anthropic model rates).
    session_cost = float(cost_block.get("total_cost_usd") or 0)
    warn = False
    if session_cost <= 0:
        sid = str(payload.get("session_id") or "")
        transcript = payload.get("transcript_path") or ""
        if sid and transcript and os.path.exists(transcript):
            try:
                state = load_state(sid)
                if not isinstance(state.get("path"), str) or Path(state["path"]) != Path(transcript):
                    state = reset_state(sid, str(transcript))
                sheet = load_prices()
                bill_new_lines(state, str(transcript), sheet)
                session_cost = float(state.get("cost") or 0.0)
                warn = bool(state.get("unpriced"))
                save_state(sid, state)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                warn = True  # $0.00 shown is the wrong figure — mark it
        else:
            warn = True
    cost_color = RED if session_cost > 5 else YELLOW if session_cost >= 1 else GREEN
    cost_str = color(f"${session_cost:.2f}", cost_color) + (" ⚠" if warn else "")

    segments = [
        color(f"📁 {dirname}", BLUE),
        color(f"⏱ {duration}", CYAN),
        color(f"▲ +{added} -{removed}", GREEN),
        color(f"◔ {used_k}/{ctx_size // 1000}k {bar(pct)} {pct}%", ctx_color),
        cost_str,
    ]
    # SubSCRIPTION rate limits don't exist when the backend is Ollama Cloud;
    # render the segments only when the payload actually carries them.
    for window, label in (("five_hour", "5h"), ("seven_day", "7d")):
        limit = (payload.get("rate_limits") or {}).get(window)
        pct_limit = int((limit or {}).get("used_percentage") or 0)
        if limit is not None:
            seg_color = RED if pct_limit >= 90 else YELLOW if pct_limit >= 70 else GREEN
            segments.append(color(f"{label} {bar(pct_limit)} {pct_limit}%", seg_color))
    segments.append(color(f"◆ {model}", DIM))

    print("  " + color(" │ ", DIM).join(segments))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        print("  cost tracker: unreadable status payload ⚠")
        return 0
    try:
        render(payload)
    except Exception:
        # The status line must never go dark over a bad field or file.
        minimal_line(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())