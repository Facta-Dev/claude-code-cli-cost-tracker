"""The analyzer's text report: the byte-compat surface, moved verbatim.

Anything that reads the CSVs programmatically cares about their columns;
anything that reads a human in the room cares about this text. It is
treated as a contract — output bytes are not allowed to drift.
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict

TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")


def money(value: float) -> str:
    return f"${value:,.2f}"


def bar(fraction: float, width: int = 28) -> str:
    filled = int(round(max(0.0, min(1.0, fraction)) * width))
    return "#" * filled + "." * (width - filled)


def report(session_rows, turn_rows, prices, curve_bins: int) -> None:
    out = sys.stdout.write
    total_cost = sum(r["cost_usd"] for r in session_rows)
    total_turns = sum(r["turns"] for r in session_rows)

    out("\n" + "=" * 74 + "\n")
    out(f"  BASELINE  ·  {len(session_rows)} sessions  ·  {total_turns:,} turns  ·  {money(total_cost)}\n")
    out(f"  priced against {prices.path.name} as of {prices.as_of}\n")
    if prices.off_peak:
        out("  off-peak: Ollama Cloud rows billed at half the listed rate\n")
    out("=" * 74 + "\n")

    # ---- 1. the curve -----------------------------------------------------
    # Subagent turns are excluded here. They are real spend (and are counted
    # everywhere else), but each subagent runs its own independent context, so
    # interleaving them by wall clock flattens exactly the growth this view
    # exists to show. The curve is the main thread's context growth.
    longest = max(session_rows, key=lambda r: r["turns"] - r["sidechain_turns"], default=None)
    if longest:
        out("\n1. COST PER TURN ACROSS A LONG SESSION  (the curve)\n")
        out(
            f"   longest session: {longest['session_id'][:8]}  repo={longest['repo']}  "
            f"{longest['turns']} turns ({longest['sidechain_turns']} subagent)  "
            f"{money(longest['cost_usd'])}\n"
        )
        out("   main thread only; subagent turns run their own context.\n\n")
        turns = [
            t
            for t in turn_rows
            if t["session_id"] == longest["session_id"] and not t["is_sidechain"]
        ]
        turns.sort(key=lambda t: t["turn_index"])
        size = max(1, len(turns) // curve_bins)
        chunks = [turns[i : i + size] for i in range(0, len(turns), size)]
        averages = [sum(t["cost_usd"] for t in c) / len(c) for c in chunks]
        peak = max(averages) or 1.0
        out("   turns        $/turn   ctx tokens\n")
        for chunk, avg in zip(chunks, averages):
            ctx = sum(t["context_tokens"] for t in chunk) / len(chunk)
            label = f"{chunk[0]['turn_index']:>4}-{chunk[-1]['turn_index']:<4}"
            out(f"   {label}  {avg:>8.4f}   {ctx:>10,.0f}   {bar(avg / peak)}\n")
        # Compare the first and last bins that actually cost something, so a
        # trailing zero-usage turn can't report a meaningless 0.0x.
        priced = [a for a in averages if a > 0]
        if len(priced) > 1 and priced[0] > 0:
            out(
                f"\n   last priced bin costs {priced[-1] / priced[0]:.1f}x the first, per turn.\n"
            )

    # ---- 2. cache hit rate ------------------------------------------------
    agg = {f: sum(r[f + "_tokens"] for r in session_rows) for f in TOKEN_FIELDS}
    billed = agg["input"] + agg["cache_read"] + agg["cache_write_5m"] + agg["cache_write_1h"]
    out("\n2. CACHE HIT RATE\n\n")
    if billed:
        out(f"   overall           {agg['cache_read'] / billed:>7.2%}   {bar(agg['cache_read'] / billed)}\n")
        out("   cache_read       = " + f"{agg['cache_read']:>15,}\n")
        out("   cache_write 1h   = " + f"{agg['cache_write_1h']:>15,}\n")
        out("   cache_write 5m   = " + f"{agg['cache_write_5m']:>15,}\n")
        out("   uncached input   = " + f"{agg['input']:>15,}\n")
        out("   output           = " + f"{agg['output']:>15,}\n")
        rates = [r["cache_hit_rate"] for r in session_rows if r["billed_input_tokens"]]
        if rates:
            rates.sort()
            out(
                f"\n   per session:  median {statistics.median(rates):.2%}   "
                f"p10 {rates[len(rates) // 10]:.2%}   p90 {rates[min(len(rates) - 1, 9 * len(rates) // 10)]:.2%}\n"
            )

    # ---- 3. cost by repo --------------------------------------------------
    out("\n3. COST BY REPO\n\n")
    by_repo: dict[str, dict] = defaultdict(
        lambda: {"cost": 0.0, "turns": 0, "sessions": 0, "read": 0, "billed": 0}
    )
    for row in session_rows:
        slot = by_repo[row["repo"]]
        slot["cost"] += row["cost_usd"]
        slot["turns"] += row["turns"]
        slot["sessions"] += 1
        slot["read"] += row["cache_read_tokens"]
        slot["billed"] += row["billed_input_tokens"]
    ordered = sorted(by_repo.items(), key=lambda kv: -kv[1]["cost"])
    top = ordered[0][1]["cost"] if ordered else 0
    out(f"   {'repo':<22}{'cost':>10}{'sess':>6}{'turns':>7}{'$/turn':>9}{'cache':>8}\n")
    for name, s in ordered:
        hit = s["read"] / s["billed"] if s["billed"] else 0
        out(
            f"   {name[:21]:<22}{money(s['cost']):>10}{s['sessions']:>6}{s['turns']:>7}"
            f"{s['cost'] / s['turns']:>9.4f}{hit:>8.1%}  {bar(s['cost'] / top if top else 0, 18)}\n"
        )

    if prices.unknown:
        out(
            "\n!  models missing from the price sheet (counted, priced at $0): "
            + ", ".join(sorted(prices.unknown))
            + "\n"
        )
    out("\n")