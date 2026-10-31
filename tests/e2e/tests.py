#!/usr/bin/env python3
"""E2E suite: full user surface — cccost CLI runs and statusline stdin payloads.

    python3 tests/e2e/tests.py
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from _common import *


def test_cccost_period_reports():
    """daily/weekly/monthly aggregate the same dollars the analyzer bills."""
    for command in ("daily", "weekly", "monthly"):
        proc = cccost(command, "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
        assert proc.returncode == 0, proc.stderr
        assert "$15.39" in proc.stdout, f"{command} must bill 6.70 + 8.69"


def test_cccost_session_json_and_guardrail():
    proc = cccost("session", "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
    assert proc.returncode == 0 and "sessA" in proc.stdout and "cost-lab" in proc.stdout
    assert "$6.70" in proc.stdout and "$8.69" in proc.stdout
    with tempfile.TemporaryDirectory() as td:
        proc = cccost("daily", "--json", "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
        data = json.loads(proc.stdout)
        assert data["rows"][0]["key"] == "2026-10-30" and data["total_cost_usd"] == 15.39
    proc = cccost("daily", "--projects-dir", str(PROJECTS))
    assert proc.returncode != 0, "period reports must keep the --repo guardrail"
    proc = cccost("--list-repos", "--projects-dir", str(PROJECTS))
    assert proc.returncode == 0 and REPO_NAME in proc.stdout and "$" not in proc.stdout


def test_cccost_models_report():
    """Which model burns the budget: cost-ordered per-model rows."""
    proc = cccost("models", "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
    assert proc.returncode == 0, proc.stderr
    assert "glm-5.3-flash" in proc.stdout and "$6.74" in proc.stdout  # 1.40+0.59+2+2+0.75
    assert "claude-sonnet-5" in proc.stdout and "$3.00" in proc.stdout
    assert "glm-5.2" in proc.stdout and "$1.58" in proc.stdout
    assert "unknown-model-x" in proc.stdout and "$0.00" in proc.stdout


def test_cccost_report_and_last():
    """The report subcommand (shared flow) and the --last window filter."""
    with tempfile.TemporaryDirectory() as td:
        proc = cccost("report", "--out-dir", td, "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
        assert proc.returncode == 0 and "BASELINE" in proc.stdout and "$15.39" in proc.stdout
        assert Path(td, "sessions.csv").exists() and Path(td, "turns.csv").exists()
    proc = cccost("daily", "--last", "365", "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
    assert "$15.39" in proc.stdout, "--last 365 keeps the whole fixture"


def test_merge_dedupes_on_ids():
    """Higher cost wins on key conflicts; rows union; output is sorted."""
    with tempfile.TemporaryDirectory() as d1_path, \
         tempfile.TemporaryDirectory() as d2_path, \
         tempfile.TemporaryDirectory() as out:
        d1, d2 = Path(d1_path), Path(d2_path)
        assert cccost("report", "--out-dir", str(d1), "--projects-dir", str(PROJECTS),
                      "--repo", REPO_NAME).returncode == 0
        (d2 / "sessions.csv").write_text(
            "session_id,repo,cost_usd\nsessA,cost-lab,3.00\nsessZ,other,1.23\n")
        (d2 / "turns.csv").write_text(
            "session_id,turn_index,cost_usd\nsessA,2,9.99\nsessB,7,0.50\nsessZ,1,1.23\n")
        proc = cccost("merge", str(d1), str(d2), "--out-dir", out)
        assert proc.returncode == 0, proc.stderr
        sessions = read_csv(Path(out) / "sessions.csv")
        assert [r["session_id"] for r in sessions] == ["sessA", "sessB", "sessZ"]
        assert float(next(r for r in sessions if r["session_id"] == "sessA")["cost_usd"]) == 6.70
        turns = read_csv(Path(out) / "turns.csv")
        assert len(turns) == 13, "conflict keeps higher cost; new keys union in"
        keys = {(r["session_id"], r["turn_index"]) for r in turns}
        assert ("sessA", "2") in keys and ("sessB", "7") in keys and ("sessZ", "1") in keys
        row = next(r for r in turns if r["session_id"] == "sessA" and r["turn_index"] == "2")
        assert float(row["cost_usd"]) == 9.99


def test_merge_needs_no_repo_and_never_scans_transcripts():
    """merge is CSV plumbing: no --repo, no transcript path, ever."""
    with tempfile.TemporaryDirectory() as d1_path, tempfile.TemporaryDirectory() as out:
        assert cccost("report", "--out-dir", d1_path, "--projects-dir", str(PROJECTS),
                      "--repo", REPO_NAME).returncode == 0
        assert cccost("merge", d1_path, "--out-dir", out).returncode == 0
        proc = cccost("merge", d1_path, "--projects-dir", "/nonexistent-xyz", "--out-dir", out)
        assert proc.returncode == 0, "merge must not touch transcript paths"


def test_merge_rejects_bad_inputs():
    """Loud refusals: empty export, self-merge, unknown file; keyless drop warns."""
    with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as empty:
        assert cccost("merge", empty, "--out-dir", out).returncode != 0
        assert cccost("merge", out, "--out-dir", out).returncode != 0
        stray = Path(out) / "foo.csv"
        stray.write_text("a\nb\n")
        assert cccost("merge", str(stray), "--out-dir", out).returncode != 0
        with tempfile.TemporaryDirectory() as d1_path, tempfile.TemporaryDirectory() as d2_path:
            assert cccost("report", "--out-dir", d1_path, "--projects-dir", str(PROJECTS),
                          "--repo", REPO_NAME).returncode == 0
            (Path(d2_path) / "turns.csv").write_text("session_id,cost_usd\nsessA,1.00\n")
            proc = cccost("merge", d1_path, str(Path(d2_path) / "turns.csv"), "--out-dir", out)
            assert proc.returncode == 0 and "session_id" in proc.stderr


def test_statusline_self_bills_incrementally():
    """Payload cost is dead under Ollama; cost comes from the transcript,
    re-renders bill only NEW lines (offsets, not totals), and subagent
    transcripts bill to the parent session."""
    make_fixture()  # fresh transcript
    fixture = SLUG / "sessA.jsonl"
    payload = {
        "session_id": "sessA",
        "transcript_path": str(fixture),
        "workspace": {"current_dir": "/Users/demo/repos/cost-lab"},
        "cost": {"total_duration_ms": 632000, "total_lines_added": 118, "total_lines_removed": 40},
        "model": {"display_name": "GLM 5.3 Flash"},
    }
    with tempfile.TemporaryDirectory() as cd:
        out1 = statusline(payload, cd)
        assert "$6.70" in out1 and "cost-lab" in out1 and "10m 32s" in out1
        assert "▲ +118 -40" in out1

        # a turn arrives mid-session (three duplicate content-block lines
        # must still bill once)
        turn = {
            "type": "assistant",
            "message": {"id": "msg_005", "model": "glm-5.3-flash",
                        "usage": {"input_tokens": 10_000_000, "output_tokens": 1_000_000}},
        }
        with open(fixture, "a") as fh:
            fh.write(json.dumps(turn) + "\n" + json.dumps(turn) + "\n")
        out2 = statusline(payload, cd)
        assert "$8.70" in out2, f"incremental rerun must show +$2.00: {out2}"

        # a subagent transcript appears for the parent session
        sub = SLUG / "sessA" / "subagents"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "agent-1.jsonl").write_text(json.dumps({
            "type": "assistant",
            "message": {"id": "msg_SUB_A1", "model": "glm-5.3-flash",
                        "usage": {"input_tokens": 4_000_000, "output_tokens": 1_000_000}},
        }) + "\n")
        out3 = statusline(payload, cd)
        assert "$9.80" in out3, f"subagent spend must fold in (+$1.10): {out3}"


def test_statusline_bills_tier_turns():
    """The haiku tier turn flows through the status line too (session B)."""
    with tempfile.TemporaryDirectory() as cd:
        out = statusline(
            {"session_id": "sessB", "transcript_path": str(SLUG / "sessB.jsonl"),
             "workspace": {"current_dir": "/Users/demo/repos/cost-lab"}},
            cd,
        )
        assert "$8.69" in out, "sessB = 0.59+3.00+2.00+2.00+0.75+0.35(tier)"


def test_statusline_payload_cost_wins_when_native():
    """When Claude Code provides a real cost figure, show it untouched."""
    with tempfile.TemporaryDirectory() as cd:
        out = statusline(
            {"session_id": "x", "cost": {"total_cost_usd": 12.34},
             "model": {"display_name": "Opus 5.5"},
             "workspace": {"current_dir": "/tmp/demo"},
             "rate_limits": {"five_hour": {"used_percentage": 22}, "seven_day": {"used_percentage": 61}}},
            cd,
        )
        assert "$12.34" in out and "5h" in out and "7d" in out
        assert "⚠" not in out


def test_statusline_flags_unpriced_models():
    """A turn from a model missing from the sheet shows as $0.00 ⚠."""
    with tempfile.TemporaryDirectory() as cd:
        fixture = Path(cd) / "sessC.jsonl"
        fixture.write_text(json.dumps({
            "type": "assistant",
            "message": {"id": "msg_C1", "model": "mystery-model",
                        "usage": {"input_tokens": 50_000, "output_tokens": 500}},
        }) + "\n")
        out = statusline(
            {"session_id": "sessC", "transcript_path": str(fixture),
             "workspace": {"current_dir": "/Users/demo/repos/cost-lab"}},
            cd,
        )
        assert "⚠" in out, "unpriced session must be marked"


def test_statusline_survives_garbage():
    """Unreadable payload, or corrupt-but-valid-JSON lines, never go dark."""
    proc = run(ROOT / "statusline.py", payload="not json")
    assert proc.returncode == 0 and "⚠" in proc.stdout
    proc = run(ROOT / "statusline.py", payload="[]")  # a JSONL-array payload shape
    assert proc.returncode == 0



def test_session_status_registry():
    """The unified hook persists in-flight tools/subagents per session and
    prints the same detail on --print; Stop clears the registry."""
    import json as _json
    import subprocess as _sp
    hook = ROOT / "hooks" / "session_status.py"
    sids = "e2e-procs-smoke"
    import os as _os
    cache = _tempfile.mkdtemp() if False else None
    env = {**_os.environ, "CC_COST_CACHE_DIR": tempfile.mkdtemp()}
    def feed(payload):
        r = _sp.run([PY, str(hook), "--print"], env=env,
                    input=_json.dumps(payload), capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        return r.stdout
    feed({"hook_event_name": "PreToolUse", "tool_name": "Bash",
          "tool_input": {"command": "npm run build"}, "session_id": sids})
    feed({"hook_event_name": "SubagentStart", "agent": {"name": "Explore"},
          "session_id": sids})
    regfile = Path(env["CC_COST_CACHE_DIR"]) / f"{sids}.procs.json"
    entries = _json.loads(regfile.read_text())
    assert entries == ["⚙ bash: npm run build", "🤖 Explore"], entries
    detail = feed({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "npm run build"}, "session_id": sids})
    assert "🤖 Explore" in detail and "bash" not in detail
    assert _json.loads(regfile.read_text()) == ["🤖 Explore"]
    feed({"hook_event_name": "Stop", "session_id": sids})
    assert _json.loads(regfile.read_text()) == []

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
