#!/usr/bin/env python3
"""Live cost meter for Claude Code's status line.

claude-code-cli-cost-tracker

Unlike the upstream cost-per-turn statusline, this does not trust
cost.total_cost_usd: when Claude Code runs against Ollama Cloud the
response comes from a non-Anthropic backend, so Claude Code cannot price
it. Instead every turn is billed here, from the session transcript
(Claude Code already writes per-turn token usage to .jsonl) against the
date-stamped prices.json sheet — using the shared cccost package next to
this script.

Transcript parsing is incremental: state keyed by session id remembers a
byte offset per transcript file, so each render only prices the lines
that appeared since last time — cost is live without re-reading history
that was already billed.

Stdlib only. Nothing leaves the machine.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cccost import billing, session_state

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
                state = session_state.load_state(sid)
                if not isinstance(state.get("path"), str) \
                        or Path(state["path"]).resolve() != Path(transcript).resolve():
                    state = session_state.reset_state(str(transcript))
                prices = billing.Prices(Path(PRICES_PATH))
                session_state.bill_new_lines(state, str(transcript), prices)
                session_cost = float(state.get("cost") or 0.0)
                warn = bool(state.get("unpriced"))
                session_state.save_state(sid, state)
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
    # Subscription rate limits don't exist when the backend is Ollama Cloud;
    # render the segments only when the payload actually carries them.
    for window, label in (("five_hour", "5h"), ("seven_day", "7d")):
        limit = (payload.get("rate_limits") or {}).get(window)
        if limit is not None and limit.get("used_percentage") is not None:
            pct_limit = int(limit["used_percentage"])
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
        try:
            minimal_line(payload)
        except Exception:
            print("  cost tracker: statusline error ⚠")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())