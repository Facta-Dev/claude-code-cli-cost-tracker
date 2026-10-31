# Contributing

Short and opinionated. The invariants that keep the numbers honest and the
project cheap to maintain.

## Invariants (do not break these)

1. **The price sheet stays external.** No rates in code — `prices.json` is
   date-stamped; editing rates means copy → edit → `--prices`. Never inline
   rates into the scripts.
2. **`message.id` is the billing unit.** Every parsed assistant line repeats
   identical usage; every walker dedupes on it. Any new report must reuse the
   dedupe (in `cccost/transcript.py`), never re-sums assistant lines.
3. **The report surface is a contract.** The text report and CSVs are
   byte-compat; if output formatting changes, the tests change with it.
4. `--repo` is required for every report — the guardrail is a feature, not
   friction. The single carve-out is `cccost merge`, which is CSV-only
   plumbing over already-billed exports (no transcripts scanned, no pricing,
   view-only output).
5. **Stdlib only.** No dependencies in the runtime or tests.
6. **Unpriced ≠ dropped.** A model missing from the sheet bills $0 and is
   named — both in reports and via `⚠` in the status line.
7. **The status line never goes dark.** Any runtime failure renders a
   fallback line or an empty-but-valid render; a crash must surface as `⚠`.
   (An install error should fail loud, though — see README.)
8. **The price sheet stays honest about its own honesty.** Known understatement
   (unpublished cached-input rates, Haiku tier) is noted inside prices.json
   itself.

# How to work here

```bash
python3 tests/test_billing.py   # 13 checks, stdlib only
```

Tests are subprocess-level and import the billing core directly; keep them
green, extend them when behavior changes. Python 3.10+.

## Commits

`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `ci:`
— one line, or one line + explanatory body. Merge queue is whatever the
maintainer says it is (currently: direct push to `main`).

Merge queue note: this project keeps direct pushes to `main`, so `ci.yml`
runs on push — a red CI means revert or fix, not hope.