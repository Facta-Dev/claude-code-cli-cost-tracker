#!/usr/bin/env python3
"""Billing checks for the cost tracker. Plain python3 or pytest both work.

    python3 tests/test_billing.py          # no dependencies needed
    pytest tests/test_billing.py

Regenerates the synthetic fixture, then checks the analyzer's arithmetic,
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

        assert len(turns) == 7, "dupes must collapse to one row per message id"
        a = session_row(sessions, "sessA")
        b = session_row(sessions, "sessB")

        # sessA: $1.40 (glm-5.3-flash w/ both TTLs) + $1.58 (glm-5.2) + $0 + $0
        assert float(a["cost_usd"]) == 2.98 and int(a["turns"]) == 4
        # sessB: $0.59 (glm-5.3-flash) + $3.00 (claude-sonnet-5) + $0.75 (subagent)
        assert float(b["cost_usd"]) == 4.34 and int(b["turns"]) == 3
        assert int(b["sidechain_turns"]) == 1, "subagent must fold into parent"
        # cache hit rates on hand-computed splits
        assert float(b["cache_hit_rate"]) == 0.5  # 8M read of 16M billed
        assert float(a["cache_hit_rate"]) == 0.9036  # 30M read of 33.2M billed


def test_off_peak_discounts_only_ollama():
    """--off-peak halves Ollama rows, never first-party Claude rows."""
    with analyze("--off-peak") as (_proc, out):
        sessions = read_csv(Path(out) / "sessions.csv")
        a = session_row(sessions, "sessA")
        b = session_row(sessions, "sessB")
        assert float(a["cost_usd"]) == 1.49  # 2.98 / 2 — all-Ollama session
        # 4.34 -> 0.295 + 0.375 + 3.00: the claude-sonnet-5 turn is untouched
        assert float(b["cost_usd"]) == 3.67


def test_unpriced_models_named():
    """Models missing from the sheet are counted, $0, and named — not silent."""
    with analyze() as (proc, out):
        assert "unknown-model-x" in proc.stdout, "unpriced model must be named"
        sessions = read_csv(Path(out) / "sessions.csv")
        assert int(session_row(sessions, "sessA")["unpriced_turns"]) == 1


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
    and re-renders bill only NEW lines (offsets, not totals)."""
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

        # a turn arrives mid-session
        with open(fixture, "a") as fh:
            fh.write(json.dumps({
                "type": "assistant",
                "message": {"id": "msg_005", "model": "glm-5.3-flash",
                            "usage": {"input_tokens": 10_000_000, "output_tokens": 1_000_000}},
            }) + "\n")
        out2 = statusline(payload, cd)
        assert "$4.98" in out2, f"incremental rerun must show +$2.00: {out2}"


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
    fixture = SLUG / "sessC.jsonl"
    fixture.write_text(json.dumps({
        "type": "assistant",
        "message": {"id": "msg_C1", "model": "mystery-model",
                    "usage": {"input_tokens": 50_000, "output_tokens": 500}},
    }) + "\n")
    with tempfile.TemporaryDirectory() as cd:
        out = statusline(
            {"session_id": "sessC", "transcript_path": str(fixture),
             "workspace": {"current_dir": "/Users/demo/repos/cost-lab"}},
            cd,
        )
        assert "⚠" in out, "unpriced session must be marked"


def test_statusline_survives_garbage():
    """Unreadable payload -> exit 0 with a fallback line, never dark."""
    proc = run(ROOT / "statusline.py", payload="not json")
    assert proc.returncode == 0 and "⚠" in proc.stdout


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