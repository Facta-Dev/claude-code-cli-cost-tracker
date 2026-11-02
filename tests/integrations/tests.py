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
