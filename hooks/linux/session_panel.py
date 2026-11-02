#!/usr/bin/env python3
"""Live panel of EVERY Claude Code session running on this machine (Linux).

The Linux counterpart of iTerm2's "Session Status" panel: one row per session with
its state (working / waiting / done / error), cost, the tool in flight and the time
since its last event. It reads the per-session records written by
hooks/session_status.py ($CC_SESSIONS_DIR, default <cache>/sessions) and cross-checks
them with the real `claude` processes (/proc):
  - records of dead sessions are dropped;
  - sessions that have not fired a hook yet show as "no hook" (they appear at
    their first hook event).

Inside WezTerm a CLICK on a row jumps to that session
(`wezterm cli list` -> the pane whose tty matches -> `wezterm cli activate-pane`).
The row marked with ▶ is the session of this very tab. Outside WezTerm it is a
read-only panel.

    session_panel.py            interactive panel (q quits), refreshes every second
    session_panel.py --once     print one plain-text snapshot and exit
"""

from __future__ import annotations

import curses
import json
import locale
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

CACHE_DIR = os.environ.get("CC_COST_CACHE_DIR") or os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
    "claude-cost-tracker",
)
SESSIONS_DIR = Path(os.environ.get("CC_SESSIONS_DIR") or os.path.join(CACHE_DIR, "sessions"))
STALE_SECS = 15 * 60   # "working" with no event for this long gets a "?"
PANE_TTL = 3.0         # seconds between refreshes of the tty -> WezTerm pane map
SORT = {"waiting": 0, "error": 1, "working": 2, "new": 3, "done": 4, "nohook": 5}
TEXT = {"waiting": "waiting", "error": "error", "working": "working",
        "new": "new", "done": "done", "nohook": "no hook"}


# ---- sessions -----------------------------------------------------------------

def claude_procs() -> dict[int, dict]:
    """pid -> {tty, cwd} of every `claude` CLI attached to a pty (not claude-desktop)."""
    out: dict[int, dict] = {}
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            if (d / "comm").read_text().strip() != "claude":
                continue
            tty = os.readlink(d / "fd" / "0")
            if not tty.startswith("/dev/pts/"):
                continue
            out[int(d.name)] = {"tty": tty, "cwd": os.readlink(d / "cwd")}
        except OSError:
            continue
    return out


def load_rows() -> list[dict]:
    procs = claude_procs()
    recs: dict[int, dict] = {}
    if SESSIONS_DIR.is_dir():
        for f in SESSIONS_DIR.glob("*.json"):
            try:
                r = json.loads(f.read_text())
                p = procs.get(r.get("pid"))
            except Exception:
                continue
            if not p or p["tty"] != r.get("tty"):      # dead process or reused pid
                try:
                    f.unlink()
                except OSError:
                    pass
                continue
            recs[r["pid"]] = r
    rows = []
    for pid, p in procs.items():
        r = recs.get(pid)
        if r is None:
            r = {"pid": pid, "tty": p["tty"], "repo": Path(p["cwd"]).name or "?",
                 "state": "nohook", "label": "no hook",
                 "detail": "shows up at its first hook event", "updated": None}
        rows.append(r)
    rows.sort(key=lambda r: (SORT.get(r.get("state"), 9), -(r.get("updated") or 0)))
    return rows


# ---- WezTerm: tty -> pane map and jump ----------------------------------------

def wez_bin() -> str:
    d = os.environ.get("WEZTERM_EXECUTABLE_DIR")
    return os.path.join(d, "wezterm") if d else (shutil.which("wezterm") or "wezterm")


def pane_map() -> tuple[dict | None, int | None]:
    """-> (tty -> pane, this panel's tab id), or (None, None) outside WezTerm."""
    if not os.environ.get("WEZTERM_UNIX_SOCKET"):
        return None, None
    try:
        out = subprocess.run([wez_bin(), "cli", "list", "--format", "json"],
                             capture_output=True, text=True, timeout=3)
        data = json.loads(out.stdout)
    except Exception:
        return None, None
    own = os.environ.get("WEZTERM_PANE")
    own_tab = next((p["tab_id"] for p in data if str(p.get("pane_id")) == own), None)
    return {p["tty_name"]: p for p in data if p.get("tty_name")}, own_tab


def goto(row: dict, pmap: dict | None) -> str:
    """Jump to the session's pane. Returns the message for the footer."""
    name = row.get("repo") or "?"
    if pmap is None:
        return "not in WezTerm: cannot jump"
    pane = pmap.get(row.get("tty"))
    if not pane:
        return f"{name}: not in WezTerm ({str(row.get('tty')).replace('/dev/', '')})"
    try:
        r = subprocess.run([wez_bin(), "cli", "activate-pane", "--pane-id", str(pane["pane_id"])],
                           capture_output=True, text=True, timeout=3)
        return f"→ {name}" if r.returncode == 0 else f"jump failed: {r.stderr.strip()[:50]}"
    except Exception as exc:
        return f"jump failed: {exc}"


# ---- render -------------------------------------------------------------------

def age(ts: float | None) -> str:
    if not ts:
        return "-"
    s = max(0, int(time.time() - ts))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def cut(text: object, width: int) -> str:
    text = re.sub(r"[\x00-\x1f\x7f\s]+", " ", str(text or "")).strip()
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


def build(rows: list[dict], width: int, own_ttys: set | frozenset = frozenset()) -> list[tuple]:
    """-> [(text, color key, dim, row index | None)]"""
    w = max(20, width - 1)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    summary = " · ".join(f"{counts[k]} {TEXT[k]}" for k in SORT if counts.get(k))
    lines: list[tuple] = [(cut(f"Claude Code · {len(rows)} session(s)", w), "head", False, None),
                          (cut(summary or "no sessions running", w), "head", True, None),
                          ("", "", False, None)]
    for i, r in enumerate(rows):
        st = r.get("state", "nohook")
        label = TEXT.get(st, st)
        if r.get("label") and st in ("waiting", "new"):
            label = r["label"]
        stale = bool(st == "working" and r.get("updated") and time.time() - r["updated"] > STALE_SECS)
        if stale:
            label += "?"
        cost = f"${float(r['cost']):.2f}" if r.get("cost") is not None else ""
        right = f"{label} {cost}".strip()
        mark = "▶" if r.get("tty") in own_ttys else "●"
        left = cut(f"{mark} " + str(r.get("repo") or "?"), max(5, w - len(right) - 1))
        lines.append((left + " " * max(1, w - len(left) - len(right)) + right, st, stale, i))
        detail = r.get("detail") or r.get("task") or ""
        if detail:
            lines.append((cut("  " + detail, w), "", True, i))
        tail = f"  {str(r.get('tty', '')).replace('/dev/', '')} · {age(r.get('updated'))} ago"
        lines.append((cut(tail, w), "", True, i))
        lines.append(("", "", False, None))
    return lines


def run(stdscr: "curses._CursesWindow") -> None:
    locale.setlocale(locale.LC_ALL, "")
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.mouseinterval(0)                      # press and release as separate events
    curses.mousemask(curses.ALL_MOUSE_EVENTS)
    pairs = {"working": curses.COLOR_YELLOW, "waiting": curses.COLOR_RED, "error": curses.COLOR_MAGENTA,
             "done": curses.COLOR_GREEN, "new": curses.COLOR_CYAN, "nohook": curses.COLOR_WHITE,
             "head": curses.COLOR_CYAN}
    attr = {}
    for i, (k, c) in enumerate(pairs.items(), start=1):
        curses.init_pair(i, c, -1)
        attr[k] = curses.color_pair(i)
    stdscr.timeout(1000)

    pmap, own_tab, pmap_at = None, None, 0.0
    msg, msg_at = "", 0.0
    while True:
        now = time.time()
        if now - pmap_at > PANE_TTL:
            pmap, own_tab = pane_map()
            pmap_at = now
        h, w = stdscr.getmaxyx()
        rows = load_rows()
        own_ttys = {t for t, p in (pmap or {}).items() if own_tab is not None and p["tab_id"] == own_tab}
        stdscr.erase()
        hit: dict[int, int] = {}                  # screen y -> row index
        for y, (text, key, dim, idx) in enumerate(build(rows, w, own_ttys)[: h - 1]):
            a = attr.get(key, 0) | (curses.A_DIM if dim else 0) \
                | (curses.A_BOLD if key in ("waiting", "head") and not dim else 0)
            if idx is not None:
                hit[y] = idx
            try:
                stdscr.addstr(y, 0, text, a)
            except curses.error:
                pass
        footer = msg if (msg and now - msg_at < 4) else "click: jump to session · q quit"
        try:
            stdscr.addstr(h - 1, 0, cut(footer, w - 1), curses.A_DIM)
        except curses.error:
            pass
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            return
        if ch == curses.KEY_MOUSE:
            try:
                _id, _mx, my, _mz, bstate = curses.getmouse()
            except curses.error:
                continue
            if bstate & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED) and my in hit and hit[my] < len(rows):
                pmap, own_tab = pane_map()        # fresh map right before jumping
                pmap_at = time.time()
                msg, msg_at = goto(rows[hit[my]], pmap), time.time()


def main() -> int:
    if "--once" in sys.argv[1:]:
        pmap, own_tab = pane_map()
        own = {t for t, p in (pmap or {}).items() if own_tab is not None and p["tab_id"] == own_tab}
        for text, _k, _d, _i in build(load_rows(), 60, own):
            print(text)
        return 0
    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
