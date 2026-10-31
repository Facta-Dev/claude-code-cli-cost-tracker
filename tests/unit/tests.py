#!/usr/bin/env python3
"""Unit suite: the billing core against the shipped sheet, no subprocesses.

    python3 tests/unit/tests.py
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from _common import ROOT

from cccost.billing import in_off_peak_window, Prices, usage_tokens
from cccost.transcript import turn_from_obj


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


def test_speed_number_is_not_fast():
    """Ollama's numeric speed (tokens/s) — and any non-"fast" string — never counts."""
    from cccost.transcript import turn_from_obj
    prices = Prices(ROOT / "prices.json")
    usage_line = {"type": "assistant",
                  "message": {"id": "m1", "model": "glm-5.3-flash",
                              "usage": {"input_tokens": 1_000_000, "speed": 12.3}}}
    assert turn_from_obj(usage_line)["fast"] is False
    usage_line["message"]["model"] = "claude-sonnet-5"
    assert turn_from_obj(usage_line)["fast"] is False
    assert prices.cost("claude-sonnet-5", usage_tokens({"input_tokens": 1_000_000})) == 2.00


def test_fast_mode_pricing():
    """speed=='fast' on a claude- model bills the -fast sheet row (2x classes)."""
    prices = Prices(ROOT / "prices.json")
    tok = usage_tokens({"input_tokens": 200_000, "output_tokens": 50_000,
                        "cache_read_input_tokens": 300_000})
    assert prices.cost("claude-opus-5-5", tok) == 1.86
    assert prices.cost("claude-opus-5-5", tok, fast=True) == 3.72
    assert prices.cost("claude-opus-5-5[1m]", tok, fast=True) == 3.72
    assert prices.fast_fallback == 0


def test_fast_without_sheet_row_falls_back():
    """No -fast row: base rates + fallback counter; unknown models stay unknown."""
    prices = Prices(ROOT / "prices.json")
    tok = usage_tokens({"input_tokens": 1_000_000, "output_tokens": 100_000})
    assert prices.cost("claude-sonnet-5-5", tok) == 3.00
    assert prices.cost("claude-sonnet-5-5", tok, fast=True) == 3.00
    assert prices.fast_fallback == 1
    assert prices.cost("mystery-model", tok, fast=True) is None
    assert prices.fast_fallback == 1


def test_haiku_tier_boundary():
    """Sheet-carried tiers apply strictly above the threshold; only named classes."""
    prices = Prices(ROOT / "prices.json")
    base = usage_tokens({"input_tokens": 100_000, "output_tokens": 10_000})
    assert prices.cost("claude-haiku-5-5", base) == 0.015
    over = usage_tokens({"input_tokens": 150_000, "output_tokens": 10_000})
    assert prices.cost("claude-haiku-5-5", over) == 0.1  # tier: (150k*0.5 + 10k*2.5)/1e6
    # tier names input/output only — cache classes bill at the base row
    cached = usage_tokens({"input_tokens": 50_000, "cache_read_input_tokens": 60_000})
    assert prices.cost("claude-haiku-5-5", cached) == 0.0256
    # rows without tiers are untouched
    assert prices.cost("claude-sonnet-5", usage_tokens({"input_tokens": 500_000})) == 1.00


def test_off_peak_window_semantics():
    """The UTC window: weekends all day; weekdays outside 12:00-18:00 UTC."""
    from cccost.billing import in_off_peak_window
    from datetime import datetime, timezone
    d = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    assert in_off_peak_window(d("2026-10-30T09:00:00")) is True   # Fri, off-window
    assert in_off_peak_window(d("2026-10-30T14:00:00")) is False  # Fri, peak window
    assert in_off_peak_window(d("2026-10-31T14:00:00")) is True   # Saturday
    assert in_off_peak_window(d("2026-10-30T12:00:00")) is False  # window start inclusive
    assert in_off_peak_window(d("2026-10-30T18:00:00")) is True   # 18:00 already off
    # off-peak discount composes per turn: an off-window Ollama turn halves,
    # a peak-window one doesn't, and a Claude row never halves either way.
    prices = Prices(ROOT / "prices.json")
    prices.off_peak = True
    tok = usage_tokens({"input_tokens": 1_000_000})
    assert prices.cost("glm-5.3-flash", tok, "2026-10-30T09:00:00Z") == 0.075
    assert prices.cost("glm-5.3-flash", tok, "2026-10-30T14:00:00Z") == 0.15
    assert prices.cost("claude-sonnet-5", tok, "2026-10-30T09:00:00Z") == 2.00
    assert prices.cost("glm-5.3-flash", tok, None) == 0.075


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
