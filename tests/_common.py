"""Shared helpers for all test suites. Not a suite itself.

Sets up sys.path (repo root for `cccost`, tests/ for this helper) and the
Python-floor guard; each suite imports from here and runs with plain
python3 (pytest is deliberately absent from this project).
"""

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit(f"Python 3.10+ required (found {sys.version.split()[0]}): "
             f"this repo uses union type annotations in signatures")

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
PROJECTS = ROOT / "tests" / "fixtures" / "projects"
REPO_NAME = "cost-lab"
SLUG = PROJECTS / "-Users-demo-repos-cost-lab"

for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


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


def cccost(*args: str) -> subprocess.CompletedProcess:
    return run(ROOT / "cccost.py", *args)


def statusline(payload: dict, cache_dir: str) -> str:
    proc = run(
        ROOT / "statusline.py",
        env={"CC_COST_CACHE_DIR": cache_dir},
        payload=json.dumps(payload),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout