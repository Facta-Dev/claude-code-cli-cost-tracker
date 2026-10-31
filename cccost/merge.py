"""Cross-machine merge of analyzer exports: CSV in, deduped CSV out.

Merges sessions.csv (dedupe on session_id) and turns.csv (dedupe on
(session_id, turn_index)), keeping the higher-cost row when the same key
appears twice — the superset read when one machine re-billed a compacted
transcript. Pure CSV plumbing: no transcripts are ever scanned, no pricing
engine involved — costs are already in the rows. Merged output is
view-only data; it does not flow back through build() and it never relaxes
the --repo guardrail.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from cccost.analysis import write_csv

KINDS = ("sessions", "turns")
# Dedupe key per kind; keep rule is the same for both (higher cost wins).
KEYS = {
    "sessions": lambda row: (row.get("session_id") or "",),
    "turns": lambda row: (row.get("session_id") or "", str(row.get("turn_index") or "")),
}


def _load(path: Path):
    """(kind, rows) from a directory or a single named CSV file."""
    if path.is_dir():
        rows_by_kind = {}
        for kind in KINDS:
            f = path / f"{kind}.csv"
            if not f.exists():
                sys.exit(f"{path}: missing {kind}.csv — not a cccost export")
            rows_by_kind[kind] = list(csv.DictReader(f.open()))
        return rows_by_kind
    kind = path.name.removesuffix(".csv")
    if kind not in KINDS:
        sys.exit(f"{path}: name it sessions.csv or turns.csv, or pass its directory")
    return {kind: list(csv.DictReader(path.open()))}


def _keep(existing: dict, row: dict) -> dict:
    """Higher cost_usd wins; ties keep the first seen (deterministic)."""
    if float(existing.get("cost_usd") or 0) >= float(row.get("cost_usd") or 0):
        return existing
    return row


def merge(inputs: list[Path], out_dir: Path) -> int:
    if Path(out_dir).resolve() in {p.resolve() for p in inputs}:
        sys.exit("refusing to merge an export into itself: input == --out-dir")
    out_dir = Path(out_dir)

    merged: dict[str, dict] = {k: {} for k in KINDS}  # key -> row
    dropped = 0
    for path in inputs:
        by_kind = _load(Path(path))
        for kind, rows in by_kind.items():
            key_fn, bucket = KEYS[kind], merged[kind]
            for row in rows:
                key = key_fn(row)
                if not key[0] or (kind == "turns" and not key[1]):
                    dropped += 1
                    print(f"!  dropping row with no session_id: {path}", file=sys.stderr)
                    continue
                bucket[key] = _keep(bucket[key], row) if key in bucket else row

    total = sum(len(b) for b in merged.values())
    if not total:
        sys.exit("nothing to merge: no rows in the given exports")

    # union of row columns, first-seen order (exports differ in their column subsets)
    fieldnames = {
        kind: list({c: None for row in merged[kind].values() for c in row})
        for kind in KINDS
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        rows = list(merged[kind].values())
        if not rows:
            continue
        if kind == "sessions":
            rows.sort(key=lambda r: r.get("session_id") or "")
        else:
            def turn_key(r: dict):
                try:
                    idx = int(r.get("turn_index") or 0)
                except ValueError:
                    idx = 10**9
                return (r.get("session_id") or "", idx)
            rows.sort(key=turn_key)
        write_csv(out_dir / f"{kind}.csv", rows, fieldnames=fieldnames[kind])
        print(f"   merged {len(rows):>5} rows -> {out_dir / f'{kind}.csv'}")
    print(f"   duplicates dropped: {dropped}")
    print(f"   merged (view-only data; bill with --repo against transcripts, not these CSVs)")
    return 0