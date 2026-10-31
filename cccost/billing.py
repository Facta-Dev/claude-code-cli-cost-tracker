"""The one pricing seam: usage token classes, model resolution, per-turn cost.

Every dollar figure in the tracker comes from here — the status line bills
single turns through this module, the history analyzer price-sheets whole
sessions, and the tests pin it against the shipped prices.json. Rates are
never hardcoded in any file.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")

SYNTHETIC = "<synthetic>"  # locally generated responses; not provider spend


def in_off_peak_window(when: datetime) -> bool:
    """Ollama Cloud's off-peak: weekends, and weekdays outside 12:00-18:00 UTC."""
    return when.weekday() >= 5 or not (12 <= when.hour < 18)


def usage_tokens(usage: dict) -> dict[str, int]:
    """Split a raw usage block into the five separately-priced classes.

    cache_creation_input_tokens is deliberately NOT used as a single number:
    on first-party Claude the 5-minute and 1-hour TTLs bill differently
    (1.25x vs 2.0x input) and the split lives in usage.cache_creation.
    Ollama Cloud has no separate write rate, so there the split is free to
    keep. Transcripts missing the detail fall back to the 5m bucket —
    an understatement, never a spike.
    """
    creation = usage.get("cache_creation") or {}
    w1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
    w5m = int(creation.get("ephemeral_5m_input_tokens") or 0)
    total_write = int(usage.get("cache_creation_input_tokens") or 0)
    if w1h + w5m == 0 and total_write:
        w5m = total_write
    return {
        "input": int(usage.get("input_tokens") or 0),
        "output": int(usage.get("output_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write_5m": w5m,
        "cache_write_1h": w1h,
    }


class Prices:
    """A date-stamped price sheet. Rates are never hardcoded in this file."""

    def __init__(self, path: Path):
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
        self.path = path
        self.as_of = raw.get("as_of")
        if not self.as_of:
            raise ValueError(
                f"{path}: price sheet has no 'as_of' date. Refusing to guess."
            )
        self.models: dict[str, dict] = dict(raw.get("models") or {})
        self.aliases = {
            k: v for k, v in (raw.get("aliases") or {}).items() if not k.startswith("_")
        }
        self.off_peak_factor = float(raw.get("off_peak_factor") or 0.5)
        self.off_peak = False  # the CLI flag sets this
        self.unknown: set[str] = set()

    def resolve(self, model: str) -> str:
        """Map a transcript model string to its price-sheet key.

        Aliases map first; then the decorations Claude Code adds are
        stripped and re-resolved — an "[1m]"-style suffix selects a
        context window (not a tier) and ":cloud" tags an Ollama-hosted
        model ("gpt-oss:120b" itself is a bare sheet key, never split —
        only the exact ":cloud" tag strips).
        """
        if model in self.models:
            return model
        if model in self.aliases:
            return self.aliases[model]
        for mark, cleaner in (
            ("[", lambda m: m.split("[", 1)[0]),
            (":cloud", lambda m: m[: -len(":cloud")]),
        ):
            if mark in model:
                stripped = cleaner(model)
                if stripped and stripped != model:
                    return self.resolve(stripped)
        return model

    def cost(self, model: str, tokens: dict[str, int],
             timestamp: str | None = None) -> float | None:
        """USD for one turn. None when the model is not on the price sheet."""
        if model == SYNTHETIC:
            return 0.0
        rates = self.models.get(self.resolve(model))
        if rates is None:
            self.unknown.add(model)
            return None
        # Off-peak is an Ollama Cloud concept (rows tagged off_peak): a
        # first-party Claude row must not inherit it, and the half rate
        # applies PER TURN by timestamp — weekends and weekdays outside
        # 12:00-18:00 UTC. Undated turns are treated as off-peak, so an
        # unknown stays an understatement, never a spike.
        factor = 1.0
        if self.off_peak and rates.get("off_peak"):
            when = None
            if timestamp:
                try:
                    when = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                except ValueError:
                    when = None
            if when is None or in_off_peak_window(when):
                factor = self.off_peak_factor
        return sum(tokens[f] * rates[f] * factor for f in TOKEN_FIELDS) / 1_000_000