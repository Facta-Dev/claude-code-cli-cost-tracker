#!/usr/bin/env python3
"""Single unified Claude Code hook — session status for every platform.

One process per event. It:
  1. passes the hook JSON to the native state machine — macOS/iTerm2's
     cc-status (working/waiting/done/error/idle dot) — when present;
  2. maintains a per-session in-flight registry (tools from
     Pre/PostToolUse, subagents from SubagentStart/Stop);
  3. emits the status DETAIL per platform:
       darwin + iTerm2  -> it2 set-status --detail on that exact session
       darwin no iTerm  -> osascript notification (best-effort)
       linux            -> notify-send notification on waiting/done, plus a live
                           per-session record (CC_SESSIONS_DIR, default
                           <cache>/sessions) for hooks/linux/session_panel.py,
                           plus the terminal TAB TITLE when CC_TAB_TITLE=1
       windows          -> powershell -File session-status.ps1 (toast)
  with cost from the cccost state cache:  ⚙ Bash: npm test · 🤖 Explore · 💰 $3.09

Every step is best-effort: a missing binary, absent window server, or bad
payload silently degrades. Testability: --print prints the detail line and
skips every side effect; CC_COST_CACHE_DIR shares the tracker's cache.

    python3 session_status.py < hook_event.json
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

CACHE_DIR = os.environ.get("CC_COST_CACHE_DIR") or os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
    "claude-cost-tracker",
)
SESSIONS_DIR = os.environ.get("CC_SESSIONS_DIR") or os.path.join(CACHE_DIR, "sessions")
HERE = str(Path(__file__).resolve().parent)
IT2 = "/Applications/iTerm.app/Contents/Resources/utilities/it2"
CC_STATUS = os.path.join(os.path.expanduser("~/.config/iterm2"), "cc-status")
PS1 = os.path.join(HERE, "session-status.ps1")

TRUNC_TOOL = 34
TRUNC_DETAIL = 110


def registry_path(sid: str) -> Path:
    return Path(CACHE_DIR) / f"{sid}.procs.json"


def load_registry(sid: str) -> list[dict]:
    try:
        data = json.loads(registry_path(sid).read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_registry(sid: str, entries: list[dict]) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        registry_path(sid).write_text(json.dumps(entries))
    except Exception:
        pass


def short(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(value) > TRUNC_TOOL:
        value = value[: TRUNC_TOOL - 1] + "…"
    return value


def what_is_running(event: str, payload: dict) -> str:
    if event in ("PreToolUse", "PostToolUse"):
        tool = str(payload.get("tool_name") or "?").lower()
        input_ = payload.get("tool_input") or {}
        desc = input_.get("description") or input_.get("file_path") or input_.get("command") or ""
        return f"⚙ {tool}: {short(desc)}"
    if event in ("SubagentStart", "SubagentStop"):
        agent = (payload.get("agent") or {}).get("name") or payload.get("agent_name") or payload.get("agent_id") or "subagent"
        return f"🤖 {short(str(agent))}"
    return ""


def update_registry(event: str, payload: dict, sid: str) -> list[dict]:
    entries = load_registry(sid)
    item = what_is_running(event, payload)
    if item:
        while item in entries:
            entries.remove(item)  # newest-first display order
        if event in ("PreToolUse", "SubagentStart"):
            entries.append(item)
    if event in ("Stop", "SessionEnd", "StopFailure"):
        entries = []
    entries = entries[-6:]
    if item or event in ("Stop", "SessionEnd", "StopFailure"):
        save_registry(sid, entries)
    return entries


def session_cost(sid: str) -> str | None:
    try:
        cost = json.loads((Path(CACHE_DIR) / f"{sid}.json").read_text()).get("cost")
        return f"${float(cost or 0):.2f}"
    except Exception:
        return None


def build_detail(event: str, payload: dict, entries: list[dict], cost: str | None) -> str:
    if event == "Notification":
        return short("waiting — " + str(payload.get("message") or ""))[:TRUNC_DETAIL]
    parts = list(entries)
    if cost:
        parts.append(f"💰 {cost}")
    return " · ".join(parts)[:TRUNC_DETAIL]


# ---- linux: live session record (panel) + terminal tab title -----------------

# event -> (panel state, label, tab-title emoji)
LINUX_STATE = {
    "SessionStart":      ("new",     "new",        "⚪"),
    "UserPromptSubmit":  ("working", "working",    "🟡"),
    "PreToolUse":        ("working", "working",    "🟡"),
    "PostToolUse":       ("working", "working",    "🟡"),
    "Notification":      ("waiting", "waiting",    "🔴"),
    "PermissionRequest": ("waiting", "permission", "🔴"),
    "Stop":              ("done",    "done",       "🟢"),
    "StopFailure":       ("error",   "error",      "⛔"),
}


def clip(value: object, limit: int) -> str:
    """One line, no control characters (payload text is untrusted: it ends up
    in the record, the panel and the terminal title), at most `limit` chars."""
    return re.sub(r"[\x00-\x1f\x7f\s]+", " ", str(value or "")).strip()[:limit]


def repo_name(payload: dict) -> str:
    return clip(Path(str(payload.get("cwd") or os.getcwd())).name, 40) or "claude"


def session_cost_value(sid: str) -> float | None:
    try:
        return float(json.loads((Path(CACHE_DIR) / f"{sid}.json").read_text()).get("cost") or 0)
    except Exception:
        return None


def find_tty() -> tuple[str | None, int | None]:
    """Nearest ancestor whose stdin is a pty -> (/dev/pts/N, pid): the claude CLI
    of the terminal tab this hook belongs to."""
    pid = os.getpid()
    for _ in range(15):
        try:
            link = os.readlink(f"/proc/{pid}/fd/0")
            if link.startswith("/dev/pts/"):
                return link, pid
        except OSError:
            pass
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            pid = int(stat.rsplit(")", 1)[1].split()[1])  # ppid
        except Exception:
            return None, None
        if pid <= 1:
            return None, None
    return None, None


def update_session_record(event: str, payload: dict, sid: str, entries: list,
                          cost: float | None, tty: str | None, pid: int | None) -> dict | None:
    """Create/refresh the per-session record the panel reads; SessionEnd deletes it.
    Without a tty/pid there is nothing a panel could match, so nothing is written."""
    path = Path(SESSIONS_DIR) / f"{sid}.json"
    if event == "SessionEnd":
        try:
            path.unlink()
        except OSError:
            pass
        return None
    if event not in LINUX_STATE or not (tty and pid):
        return None
    state, label, _emoji = LINUX_STATE[event]
    try:
        rec = json.loads(path.read_text())
    except Exception:
        rec = {}
    now = time.time()
    rec.update({"session_id": sid, "repo": repo_name(payload), "cwd": clip(payload.get("cwd"), 200),
                "state": state, "label": label, "pid": pid, "tty": tty, "updated": now})
    rec.setdefault("started", now)
    if cost is not None:
        rec["cost"] = cost
    if event == "UserPromptSubmit":
        rec["task"], rec["detail"] = clip(payload.get("prompt"), 80), ""
    elif event == "Notification":
        rec["detail"] = clip(payload.get("message"), 90)
    else:
        rec["detail"] = clip(" · ".join(str(e) for e in entries), 110)  # in-flight tools/subagents
    try:
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False))
        os.replace(tmp, path)
    except OSError:
        return None
    return rec


def tab_title(event: str, payload: dict, cost: float | None) -> str | None:
    """'🟡 my-repo · working · $2.31'; SessionEnd restores a neutral title."""
    repo = repo_name(payload)
    if event == "SessionEnd":
        return repo
    if event not in LINUX_STATE:
        return None
    _state, label, emoji = LINUX_STATE[event]
    parts = [f"{emoji} {repo}", label]
    if cost is not None:
        parts.append(f"${cost:.2f}")
    return " · ".join(parts)


def write_tab_title(tty: str, title: str) -> bool:
    """OSC 0 to the session's own pty (VTE/WezTerm/kitty/xterm...); never blocks."""
    try:
        fd = os.open(tty, os.O_WRONLY | os.O_NOCTTY)
        try:
            os.write(fd, f"\033]0;{title}\007".encode())
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def linux_session_status(event: str, payload: dict, sid: str, entries: list) -> None:
    """Panel record always; tab title only when CC_TAB_TITLE=1 (pair it with
    CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1 so Claude Code does not overwrite it)."""
    try:
        if not sid:
            return
        tty, pid = find_tty()
        cost = session_cost_value(sid)
        update_session_record(event, payload, sid, entries, cost, tty, pid)
        # PreToolUse only feeds the panel's in-flight detail: no title repaint per tool
        if os.environ.get("CC_TAB_TITLE") == "1" and tty and event != "PreToolUse":
            title = tab_title(event, payload, cost)
            if title is not None:
                write_tab_title(tty, title)
    except Exception:
        pass


# ---- platform backends (each returns True when it emitted something) -------


def backend_iterm2(raw: str, detail: str) -> bool:
    ok = False
    try:
        subprocess.run([CC_STATUS], input=raw, capture_output=True, timeout=5)
        ok = True  # cc-status owns the native dot
    except Exception:
        pass
    if detail and os.access(IT2, os.X_OK):
        argv = [IT2, "session", "set-status"]
        sid_it2 = os.environ.get("ITERM_SESSION_ID")
        if sid_it2:
            argv += ["--session", sid_it2]
        argv += ["--detail", detail]
        try:
            subprocess.run(argv, capture_output=True, timeout=5)
        except Exception:
            pass
    elif detail:
        backend_osascript(detail)  # no iTerm2 -> still notify, natively
    return ok


def backend_osascript(detail: str) -> bool:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{detail}" with title "cccost"'],
            capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def backend_linux(raw: str, event: str, detail: str) -> bool:
    _ = raw
    # waiting/done/error are worth leaving Claude for; working/idle noise is not
    if event not in ("Notification", "PermissionRequest", "Stop", "StopFailure"):
        return False
    try:
        subprocess.run(["notify-send", "-a", "cccost", "cccost", detail or event],
                       capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def backend_windows(detail: str) -> bool:
    if not detail or not os.path.exists(PS1):
        return False
    exe = "powershell" if sys.platform == "win32" else "pwsh"
    try:
        subprocess.run([exe, "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", PS1, "-PrintFromJson"],
                       capture_output=True, timeout=15)
        return True
    except Exception:
        return False


# ---- main --------------------------------------------------------------------


def main() -> int:
    argv = sys.argv[1:]
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    event = str(payload.get("hook_event_name") or "")
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("session_id") or ""))

    entries = update_registry(event, payload, sid) if sid else []
    detail = build_detail(event, payload, entries, session_cost(sid) if sid else None)

    if argv and argv[0] == "--print":
        print(detail.rstrip())
        return 0

    raw = json.dumps(payload) if payload else ""
    if sys.platform == "darwin":
        backend_iterm2(raw, detail)
    elif sys.platform == "win32":
        backend_windows(detail)
    else:
        linux_session_status(event, payload, sid, entries)
        backend_linux(raw, event, detail)
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a hook must never make noise
    raise SystemExit(0)