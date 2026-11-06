#!/usr/bin/env python3
"""Integration suite: transcript -> priced rows -> CSVs pipelines.

    python3 tests/integrations/tests.py
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from _common import *


make_fixture()  # fresh deterministic fixture before anything runs


def test_analyzer_billing():
    """Peak rates: dedup, TTL split, per-turn model pricing, fold subagents."""
    with analyze() as (_proc, out):
        sessions = read_csv(Path(out) / "sessions.csv")
        turns = read_csv(Path(out) / "turns.csv")

        assert len(turns) == 11, "dupes and corrupt-usage lines must not bill"
        a = session_row(sessions, "sessA")
        b = session_row(sessions, "sessB")

        # sessA: 1.40 + 1.58 + 0 + 0 + 3.72 (opus fast: 1.6+2.0+0.12)
        assert float(a["cost_usd"]) == 6.70 and int(a["turns"]) == 5
        # sessB: 0.59 + 3.00 (claude) + 2.00 + 2.00 (14:00 peak) + 0.75 + 0.35 (haiku tier)
        assert float(b["cost_usd"]) == 8.69 and int(b["turns"]) == 6
        assert int(b["sidechain_turns"]) == 1, "subagent must fold into parent"
        # cache hit rates on hand-computed splits
        assert float(b["cache_hit_rate"]) == 0.2213  # 8M read of 36.15M billed
        assert float(a["cache_hit_rate"]) == 0.8991


def test_off_peak_discounts_only_ollama():
    """--off-peak halves Ollama rows per turn by timestamp window, and never
    first-party Claude rows. Fixture: Friday 09:0x/09:10/09:15/09:30 UTC are
    off-peak; the 14:00 UTC turn is inside Ollama's peak window."""
    with analyze("--off-peak") as (_proc, out):
        sessions = read_csv(Path(out) / "sessions.csv")
        a = session_row(sessions, "sessA")
        b = session_row(sessions, "sessB")
        assert float(a["cost_usd"]) == 5.21  # 1.49 halved Ollama turns + 3.72 (claude fast, full)
        # 0.59->0.295 | claude 3.00 | 2.00->1.00 | 14:00 stays 2.00 | 0.75->0.375 | haiku 0.35 (claude row)
        assert float(b["cost_usd"]) == 7.02


def test_unpriced_models_named():
    """Models missing from the sheet are counted, $0, and named — not silent."""
    with analyze() as (proc, out):
        assert "unknown-model-x" in proc.stdout, "unpriced model must be named"
        sessions = read_csv(Path(out) / "sessions.csv")
        assert int(session_row(sessions, "sessA")["unpriced_turns"]) == 1



def test_fixture_regenerates_from_nothing():
    """make_fixture() wipes leftovers; a junk session cannot haunt totals."""
    junk = SLUG / "sessZZ.jsonl"
    junk.parent.mkdir(parents=True, exist_ok=True)
    junk.write_text(json.dumps({"type": "assistant", "model": "junk-model"}))
    make_fixture()
    assert not junk.exists() and (SLUG / "sessA.jsonl").exists()


def _load_hook(cache_dir: str):
    """Import hooks/session_status.py with its module-level dirs pointed at a temp cache."""
    import importlib.util
    import os
    saved = {k: os.environ.get(k) for k in ("CC_COST_CACHE_DIR", "CC_SESSIONS_DIR")}
    os.environ["CC_COST_CACHE_DIR"] = cache_dir
    os.environ.pop("CC_SESSIONS_DIR", None)
    try:
        spec = importlib.util.spec_from_file_location(
            "session_status_under_test", ROOT / "hooks" / "session_status.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_linux_session_record_lifecycle():
    """Hook events -> one live record per session for the panel: state per event,
    cost from the tracker cache, in-flight tools as detail, untrusted text sanitized,
    removed on SessionEnd, never written without a tty to match."""
    with tempfile.TemporaryDirectory() as td:
        hook = _load_hook(td)
        sid, tty, pid = "sess-1", "/dev/pts/9", 4242
        (Path(td) / f"{sid}.json").write_text(json.dumps({"cost": 2.5}))  # status-line cost cache
        cost = hook.session_cost_value(sid)
        assert cost == 2.5
        rec_path = Path(td) / "sessions" / f"{sid}.json"

        def fire(event, extra=None, entries=()):
            payload = {"hook_event_name": event, "session_id": sid,
                       "cwd": "/home/u/repos/my-repo", **(extra or {})}
            return hook.update_session_record(event, payload, sid, list(entries), cost, tty, pid)

        rec = fire("SessionStart")
        assert (rec["state"], rec["repo"], rec["tty"], rec["pid"]) == ("new", "my-repo", tty, pid)
        rec = fire("UserPromptSubmit", {"prompt": "fix\x1b]0;pwned\x07 the\nbug"})
        assert rec["state"] == "working"
        assert not any(c in rec["task"] for c in "\x1b\x07\n"), rec["task"]
        started = rec["started"]
        rec = fire("PreToolUse", entries=["⚙ bash: pytest"])
        assert rec["detail"] == "⚙ bash: pytest" and rec["task"].startswith("fix")
        assert rec["started"] == started, "started is stamped once per session"
        rec = fire("PermissionRequest", entries=["⚙ bash: pytest"])
        assert (rec["state"], rec["label"]) == ("waiting", "permission")
        rec = fire("Notification", {"message": "Claude needs\nyour input"})
        assert (rec["state"], rec["detail"]) == ("waiting", "Claude needs your input")
        rec = fire("Stop")
        assert (rec["state"], rec["detail"], rec["cost"]) == ("done", "", 2.5)
        assert json.loads(rec_path.read_text())["state"] == "done"
        fire("SessionEnd")
        assert not rec_path.exists(), "SessionEnd removes the record"
        # no tty/pid -> nothing a panel could match -> nothing written
        assert hook.update_session_record("Stop", {"cwd": "/x"}, sid, [], None, None, None) is None
        assert not rec_path.exists()


def test_linux_tab_title_format():
    """Title = emoji + repo + state (+ cost); SessionEnd neutral; unknown events silent."""
    with tempfile.TemporaryDirectory() as td:
        hook = _load_hook(td)
        p = {"cwd": "/home/u/repos/my-repo"}
        assert hook.tab_title("UserPromptSubmit", p, 2.5) == "🟡 my-repo · working · $2.50"
        assert hook.tab_title("Stop", p, None) == "🟢 my-repo · done"
        assert hook.tab_title("PermissionRequest", p, 0.0) == "🔴 my-repo · permission · $0.00"
        assert hook.tab_title("StopFailure", p, None) == "⛔ my-repo · error"
        assert hook.tab_title("SessionEnd", p, 1.0) == "my-repo"
        assert hook.tab_title("Mystery", p, 1.0) is None
        assert "\x1b" not in hook.tab_title("Stop", {"cwd": "/x/a\x1bb"}, None)


def test_linux_tab_title_reaches_the_pty():
    """write_tab_title emits an OSC 0 title sequence on the session's own pty."""
    import os
    import select
    if sys.platform == "win32" or not hasattr(os, "openpty"):
        return
    with tempfile.TemporaryDirectory() as td:
        hook = _load_hook(td)
        master, slave = os.openpty()
        try:
            assert hook.write_tab_title(os.ttyname(slave), "🟢 my-repo · done") is True
            ready, _, _ = select.select([master], [], [], 2)
            assert ready, "nothing arrived on the pty"
            data = os.read(master, 200)
            assert data == "\x1b]0;🟢 my-repo · done\x07".encode(), data
        finally:
            os.close(master)
            os.close(slave)
        assert hook.write_tab_title("/dev/pts/does-not-exist", "x") is False


def _load_panel(sessions_dir: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "session_panel_under_test", ROOT / "hooks" / "linux" / "session_panel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.SESSIONS_DIR = Path(sessions_dir)
    return mod


def test_session_panel_rows_follow_live_processes():
    """Rows = real claude processes: dead/reused-pid records are dropped, sessions
    without a record show as 'no hook', waiting sorts first."""
    import time
    with tempfile.TemporaryDirectory() as td:
        panel = _load_panel(td)
        now = time.time()
        panel.claude_procs = lambda: {
            101: {"tty": "/dev/pts/1", "cwd": "/w/alpha"},
            102: {"tty": "/dev/pts/2", "cwd": "/w/beta"},
            103: {"tty": "/dev/pts/3", "cwd": "/w/gamma"},   # pid reused: record says pts/9
            104: {"tty": "/dev/pts/4", "cwd": "/w/delta"},   # no record yet
        }
        def put(sid, **rec):
            (Path(td) / f"{sid}.json").write_text(json.dumps(rec))
        put("a", pid=101, tty="/dev/pts/1", repo="alpha", state="working", updated=now, cost=1.5)
        put("b", pid=102, tty="/dev/pts/2", repo="beta", state="waiting", label="permission", updated=now)
        put("dead", pid=999, tty="/dev/pts/8", repo="dead", state="done", updated=now)
        put("reused", pid=103, tty="/dev/pts/9", repo="old", state="done", updated=now)
        rows = panel.load_rows()
        assert [(r["repo"], r["state"]) for r in rows] == [
            ("beta", "waiting"), ("alpha", "working"), ("gamma", "nohook"), ("delta", "nohook")
        ], rows
        assert not (Path(td) / "dead.json").exists() and not (Path(td) / "reused.json").exists()


def test_session_panel_render():
    """One block per session: ▶ marks this tab's, cost/state on the row, stale 'working'
    flagged, untrusted text sanitized, nothing wider than the pane."""
    import time
    with tempfile.TemporaryDirectory() as td:
        panel = _load_panel(td)
        now = time.time()
        rows = [
            {"tty": "/dev/pts/1", "repo": "alpha", "state": "working", "updated": now, "cost": 1.5,
             "detail": "⚙ bash: \x1b[31mpytest\x1b[0m -x"},
            {"tty": "/dev/pts/2", "repo": "beta", "state": "waiting", "label": "permission", "updated": now},
            {"tty": "/dev/pts/3", "repo": "old-job", "state": "working", "updated": now - 3600},
        ]
        lines = panel.build(rows, 40, {"/dev/pts/1"})
        text = [t for t, *_ in lines]
        assert text[0].startswith("Claude Code · 3 session(s)")
        row_alpha = next(t for t in text if "alpha" in t)
        assert row_alpha.startswith("▶ alpha") and "working" in row_alpha and row_alpha.endswith("$1.50")
        assert next(t for t in text if "beta" in t).startswith("● beta")
        assert "permission" in next(t for t in text if "beta" in t)
        assert "working?" in next(t for t in text if "old-job" in t), "stale working is flagged"
        assert not any("\x1b" in t for t in text), "control characters never reach the screen"
        assert max(len(t) for t in text) <= 39
        idx = {i for *_rest, i in lines if i is not None}
        assert idx == {0, 1, 2}, "every row block is clickable"


def test_session_panel_jump_uses_the_wezterm_cli():
    """Click -> pane whose tty matches -> `wezterm cli activate-pane`; outside
    WezTerm the jump falls back to the generic window raise (which finds no
    shell on a fake pty and reports it), with "not in WezTerm" from a WezTerm
    pmap for a session living in another terminal."""
    import os
    import stat
    if sys.platform == "win32":
        return
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "calls.log"
        fake = Path(td) / "wezterm"
        fake.write_text(
            "#!/bin/sh\n"
            'echo "$@" >> "$FAKE_WEZTERM_LOG"\n'
            'if [ "$1" = cli ] && [ "$2" = list ]; then\n'
            "  echo '[{\"tab_id\":5,\"pane_id\":11,\"tty_name\":\"/dev/pts/1\"},"
            "{\"tab_id\":5,\"pane_id\":12,\"tty_name\":\"/dev/pts/7\"},"
            "{\"tab_id\":6,\"pane_id\":13,\"tty_name\":\"/dev/pts/2\"}]'\n"
            "fi\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        panel = _load_panel(td)
        keys = ("WEZTERM_EXECUTABLE_DIR", "WEZTERM_UNIX_SOCKET", "WEZTERM_PANE", "FAKE_WEZTERM_LOG")
        saved = {k: os.environ.get(k) for k in keys}
        try:
            os.environ.update({"WEZTERM_EXECUTABLE_DIR": td, "WEZTERM_UNIX_SOCKET": "x",
                               "WEZTERM_PANE": "12", "FAKE_WEZTERM_LOG": str(log)})
            pmap, own_tab = panel.pane_map()
            assert own_tab == 5 and set(pmap) == {"/dev/pts/1", "/dev/pts/7", "/dev/pts/2"}
            assert panel.goto({"repo": "beta", "tty": "/dev/pts/2"}, pmap) == "→ beta"
            assert "cli activate-pane --pane-id 13" in log.read_text()
            assert "not in WezTerm" in panel.goto({"repo": "elsewhere", "tty": "/dev/pts/5"}, pmap)
            # outside WezTerm the fallback is the any-terminal raise; /dev/pts/999
            # does not exist on a real machine, so no shell is found there and the
            # message stays deterministic (never probes or raises a real window)
            assert panel.goto({"repo": "x", "tty": "/dev/pts/99999"}, None) == "x: no shell on pts/99999"
            os.environ.pop("WEZTERM_UNIX_SOCKET")
            assert panel.pane_map() == (None, None), "outside WezTerm the panel is read-only"
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def main() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001 - report and continue
                failures += 1
                print(f"FAIL {name}: {exc}")
    print("ALL GREEN" if not failures else f"{failures} FAILURES")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
