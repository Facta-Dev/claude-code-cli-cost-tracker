#!/usr/bin/env python3
"""Billing checks for the cost tracker. Plain python3 or pytest both work.

    python3 tests/test_billing.py          # no dependencies needed
    pytest tests/test_billing.py

Regenerates the synthetic fixture, pins the shared billing core directly
against the shipped price sheet, then checks the analyzer's arithmetic,
dedup, off-peak and --repo guardrail, and the statusline's incremental
billing against known-good numbers.
"""

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
PROJECTS = ROOT / "tests" / "fixtures" / "projects"
REPO_NAME = "cost-lab"
SLUG = PROJECTS / "-Users-demo-repos-cost-lab"

sys.path.insert(0, str(ROOT))
from cccost.billing import Prices, usage_tokens  # noqa: E402


def run(script: Path, *args: str, env: dict | None = None, payload: str | None = None):
    merged = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(Path.home())}
    if env:
        merged.update(env)
    return subprocess.run(
        [PY, str(script), *args],
        capture_output=True,
        text=True,
        input=payload,
        env=merged,
        timeout=120,
    )


def make_fixture() -> None:
    shutil.rmtree(PROJECTS, ignore_errors=True)
    subprocess.run([PY, str(ROOT / "tests" / "make_fixture.py")],
                   check=True, capture_output=True)


make_fixture()  # fresh fixture before anything runs (pytest import or plain run)


def read_csv(path: Path) -> list[dict]:
    with open(path) as fh:
        return list(csv.DictReader(fh))


def session_row(rows: list[dict], stem: str) -> dict:
    return next(r for r in rows if r["session_id"].split("-")[0].startswith(stem[:5]))


@contextmanager
def analyze(*args: str):
    with tempfile.TemporaryDirectory() as td:
        proc = run(
            ROOT / "analyze-history.py",
            "--projects-dir", str(PROJECTS),
            "--repo", REPO_NAME,
            "--out-dir", td,
            *args,
        )
        if proc.returncode != 0:
            raise AssertionError(f"analyzer failed: {proc.stderr}\nstdout:\n{proc.stdout}")
        yield proc, td


# ---- the billing core, pinned directly (would catch resolver drift) ------


def test_resolver_pins_real_sheet():
    """Every decoration resolves: alias, :cloud, [1m], compounds, exact keys."""
    prices = Prices(ROOT / "prices.json")
    assert prices.resolve("glm-5.3-flash") == "glm-5.3-flash"
    assert prices.resolve("glm-5.3-flash:cloud") == "glm-5.3-flash"
    assert prices.resolve("glm-5.3-flash:cloud[1m]") == "glm-5.3-flash"
    assert prices.resolve("claude-sonnet-5-5[1m]") == "claude-sonnet-5-5"
    assert prices.resolve("gpt-oss:120b") == "gpt-oss:120b"  # a tag, not a :cloud suffix
    assert prices.resolve("model-not-on-sheet") == "model-not-on-sheet"
    assert prices.cost("model-not-on-sheet", usage_tokens({"input_tokens": 1})) is None
    assert prices.cost("<synthetic>", usage_tokens({})) == 0.0


def test_usage_token_classes():
    """TTL split when present, fallback to 5m when not — understatement, never spike."""
    tok = usage_tokens({
        "input_tokens": 10, "output_tokens": 3,
        "cache_creation_input_tokens": 7,
        "cache_creation": {"ephemeral_5m_input_tokens": 4, "ephemeral_1h_input_tokens": 3},
    })
    assert tok == {"input": 10, "output": 3, "cache_read": 0, "cache_write_5m": 4, "cache_write_1h": 3}
    fallback = usage_tokens({"cache_creation_input_tokens": 7})
    assert fallback["cache_write_5m"] == 7 and fallback["cache_write_1h"] == 0
    nothing = usage_tokens({})
    assert nothing == {"input": 0, "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}


# ---- analyzer end-to-end ------------------------------------------------


def test_repo_guardrail():
    """Unlisted repos go nowhere: --list-repos shows names only."""
    proc = run(ROOT / "analyze-history.py", "--list-repos", "--projects-dir", str(PROJECTS))
    assert proc.returncode == 0
    assert REPO_NAME in proc.stdout
    assert "$" not in proc.stdout, "list-repos must not leak costs"


def test_repo_required():
    """Running without --repo is a parser error, not a silent full history."""
    proc = run(ROOT / "analyze-history.py", "--projects-dir", str(PROJECTS))
    assert proc.returncode != 0 and "--repo" in proc.stderr


def test_analyzer_billing():
    """Peak rates: dedup, TTL split, per-turn model pricing, fold subagents."""
    with analyze() as (_proc, out):
        sessions = read_csv(Path(out) / "sessions.csv")
        turns = read_csv(Path(out) / "turns.csv")

        assert len(turns) == 9, "dupes and corrupt-usage lines must not bill"
        a = session_row(sessions, "sessA")
        b = session_row(sessions, "sessB")

        # sessA: $1.40 (glm-5.3-flash w/ both TTLs) + $1.58 (glm-5.2) + $0 + $0
        assert float(a["cost_usd"]) == 2.98 and int(a["turns"]) == 4
        # sessB: 0.59 (off-h) + 3.00 (claude) + 2.00 (off-h) + 2.00 (peak-h) + 0.75 (sub)
        assert float(b["cost_usd"]) == 8.34 and int(b["turns"]) == 5
        assert int(b["sidechain_turns"]) == 1, "subagent must fold into parent"
        # cache hit rates on hand-computed splits
        assert float(b["cache_hit_rate"]) == 0.2222  # 8M read of 36M billed
        assert float(a["cache_hit_rate"]) == 0.9036  # 30M read of 33.2M billed


def test_off_peak_discounts_only_ollama():
    """--off-peak halves Ollama rows per turn by timestamp window, and never
    first-party Claude rows. Fixture: Friday 09:0x/09:10/09:15/09:30 UTC are
    off-peak; the 14:00 UTC turn is inside Ollama's peak window."""
    with analyze("--off-peak") as (_proc, out):
        sessions = read_csv(Path(out) / "sessions.csv")
        a = session_row(sessions, "sessA")
        b = session_row(sessions, "sessB")
        assert float(a["cost_usd"]) == 1.49  # 2.98 / 2 — all-Ollama session
        # 0.59->0.295 | claude 3.00 stays | 2.00->1.00 | 14:00 stays 2.00 | 0.75->0.375
        assert float(b["cost_usd"]) == 6.67


def test_unpriced_models_named():
    """Models missing from the sheet are counted, $0, and named — not silent."""
    with analyze() as (proc, out):
        assert "unknown-model-x" in proc.stdout, "unpriced model must be named"
        sessions = read_csv(Path(out) / "sessions.csv")
        assert int(session_row(sessions, "sessA")["unpriced_turns"]) == 1


# ---- status line ---------------------------------------------------------


# ---- cccost report CLI ---------------------------------------------------


def cccost(*args: str) -> subprocess.CompletedProcess:
    return run(ROOT / "cccost.py", *args)


def test_cccost_period_reports():
    """daily/weekly/monthly aggregate the same dollars the analyzer bills."""
    for command in ("daily", "weekly", "monthly"):
        proc = cccost(command, "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
        assert proc.returncode == 0, proc.stderr
        assert "$11.32" in proc.stdout, f"{command} must bill 2.98 + 8.34"


def test_cccost_session_json_and_guardrail():
    proc = cccost("session", "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
    assert proc.returncode == 0 and "sessA" in proc.stdout and "cost-lab" in proc.stdout
    assert "$2.98" in proc.stdout and "$8.34" in proc.stdout
    with tempfile.TemporaryDirectory() as td:
        proc = cccost("daily", "--json", "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
        data = json.loads(proc.stdout)
        assert data["rows"][0]["key"] == "2026-10-30" and data["total_cost_usd"] == 11.32
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
    assert "unknown-model-x" in proc.stdout and "$0.00" in proc.stdout  # named, $0


def test_cccost_report_and_last():
    """The report subcommand (shared flow) and the --last window filter."""
    with tempfile.TemporaryDirectory() as td:
        proc = cccost("report", "--out-dir", td, "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
        assert proc.returncode == 0 and "BASELINE" in proc.stdout and "$11.32" in proc.stdout
        assert Path(td, "sessions.csv").exists() and Path(td, "turns.csv").exists()
    proc = cccost("daily", "--last", "365", "--projects-dir", str(PROJECTS), "--repo", REPO_NAME)
    assert "$11.32" in proc.stdout, "--last 365 keeps the whole fixture"


def statusline(payload: dict, cache_dir: str) -> str:
    proc = run(
        ROOT / "statusline.py",
        env={"CC_COST_CACHE_DIR": cache_dir},
        payload=json.dumps(payload),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


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
        assert "$2.98" in out1 and "cost-lab" in out1 and "10m 32s" in out1
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
        assert "$4.98" in out2, f"incremental rerun must show +$2.00: {out2}"

        # a subagent transcript appears for the parent session
        sub = SLUG / "sessA" / "subagents"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "agent-1.jsonl").write_text(json.dumps({
            "type": "assistant",
            "message": {"id": "msg_SUB_A1", "model": "glm-5.3-flash",
                        "usage": {"input_tokens": 4_000_000, "output_tokens": 1_000_000}},
        }) + "\n")
        out3 = statusline(payload, cd)
        assert "$6.08" in out3, f"subagent spend must fold in (+$1.10): {out3}"


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