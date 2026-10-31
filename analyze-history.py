#!/usr/bin/env python3
"""Price the Claude Code transcripts already sitting on this machine.

claude-code-cli-cost-tracker — adapted (with thanks) from the open-source
cost-per-turn project, retargeted for a setup where Claude Code runs on
Ollama Cloud: the transcript records every turn's token usage regardless
of which backend served it, so each turn is priced per its own model
against the date-stamped price sheet (Ollama Cloud + first-party Claude
rates in prices.json).

Claude Code has been writing per-turn token usage to disk for every session
ever run. This reads those transcripts, prices each turn against a date-stamped
price sheet, and emits two CSVs: one row per session, one row per turn.

    ./analyze-history.py --list-repos
    ./analyze-history.py --repo my-project --repo another-repo
    ./analyze-history.py --repo my-project --off-peak

The --repo filter is required, not optional. Transcripts on a working machine
include work-adjacent sessions; only explicitly named repos are ever read into
the output. Run --list-repos first to see what is on disk (it prints repo names
and session counts only — no token, cost, or content data).

--off-peak bills Ollama Cloud models at half rate (their off-peak window:
weekends plus weekdays outside 12:00-18:00 UTC). Rows in prices.json without
the off_peak flag — first-party Claude models — are never discounted.

Stdlib only. No network. Nothing leaves the machine.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")


# --------------------------------------------------------------------------
# prices
# --------------------------------------------------------------------------


class Prices:
    """A date-stamped price sheet. Rates are never hardcoded in this file."""

    def __init__(self, path: Path):
        with path.open() as fh:
            raw = json.load(fh)
        self.path = path
        self.as_of = raw.get("as_of")
        if not self.as_of:
            sys.exit(f"{path}: price sheet has no 'as_of' date. Refusing to guess.")
        self.models = {k: v for k, v in raw.get("models", {}).items()}
        self.aliases = {
            k: v for k, v in raw.get("aliases", {}).items() if not k.startswith("_")
        }
        self.off_peak_factor = float(raw.get("off_peak_factor") or 0.5)
        self.off_peak = False
        self.unknown: set[str] = set()

    def resolve(self, model: str) -> str:
        if model in self.models:
            return model
        if model in self.aliases:
            return self.aliases[model]
        # A bare "[1m]"-style suffix is a context-window selection, not a tier.
        if "[" in model:
            base = model.split("[", 1)[0]
            if base in self.models:
                return base
            if base in self.aliases:
                return self.aliases[base]
        # ":cloud" tags an Ollama-hosted model; the sheet is keyed by the bare id.
        if model.endswith(":cloud"):
            return self.resolve(model[: -len(":cloud")])
        return model

    def cost(self, model: str, tokens: dict[str, int]) -> float | None:
        """USD for one turn. None when the model is not on the price sheet."""
        if model == "<synthetic>":
            return 0.0  # locally generated response; not provider spend
        key = self.resolve(model)
        rates = self.models.get(key)
        if rates is None:
            self.unknown.add(model)
            return None
        # Off-peak is an Ollama Cloud concept (rows tagged off_peak); a
        # first-party Claude row must not inherit the discount.
        factor = (
            self.off_peak_factor if self.off_peak and rates.get("off_peak") else 1.0
        )
        return sum(tokens[f] * rates[f] * factor for f in TOKEN_FIELDS) / 1_000_000


# --------------------------------------------------------------------------
# transcript parsing
# --------------------------------------------------------------------------


def repo_of(cwd: str | None, slug: str) -> str:
    """Best-effort repo name for a session.

    Prefer the working directory recorded on the line; fall back to the
    slugified-cwd directory name Claude Code uses for the project folder.
    A cwd of ~/repos/glutenornot.com/mobile belongs to repo glutenornot.com.
    """
    if cwd:
        parts = Path(cwd).parts
        for anchor in ("repos", "demos", "Documents"):
            if anchor in parts:
                i = parts.index(anchor)
                if i + 1 < len(parts):
                    return parts[i + 1]
                return anchor
        return Path(cwd).name
    name = slug.lstrip("-").replace("Users-", "", 1)
    return name.rsplit("-", 1)[-1] or slug


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def usage_tokens(usage: dict) -> dict[str, int]:
    """Split a raw usage block into the five separately-priced classes.

    cache_creation_input_tokens is deliberately NOT used as a single number:
    the 5-minute and 1-hour cache TTLs are priced differently (1.25x vs 2.0x
    input) on first-party Claude. Ollama Cloud has no separate write rate, so
    there the split costs nothing to keep. The split lives in
    usage.cache_creation.
    """
    creation = usage.get("cache_creation") or {}
    w1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
    w5m = int(creation.get("ephemeral_5m_input_tokens") or 0)
    total_write = int(usage.get("cache_creation_input_tokens") or 0)
    if w1h + w5m == 0 and total_write:
        # Older transcripts may lack the TTL split. Attribute to 5m (the
        # cheaper rate) so an unknown becomes an understatement, not a spike.
        w5m = total_write
    return {
        "input": int(usage.get("input_tokens") or 0),
        "output": int(usage.get("output_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write_5m": w5m,
        "cache_write_1h": w1h,
    }


def iter_turns(path: Path):
    """Yield one record per *API request*, deduplicated.

    Claude Code writes one JSONL line per content block of an assistant
    message (a thinking block, a text block, and each tool_use block are
    separate lines) and repeats the identical message.usage on every one.
    Summing assistant lines therefore multiple-counts real spend. message.id
    is the API response id, so it is the correct unit of billing.
    """
    seen: set[str] = set()
    with path.open(errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "assistant":
                continue
            message = obj.get("message") or {}
            usage = message.get("usage")
            if not usage:
                continue
            mid = message.get("id")
            if mid:
                if mid in seen:
                    continue
                seen.add(mid)
            yield {
                "message_id": mid or "",
                "model": message.get("model") or "",
                "timestamp": obj.get("timestamp"),
                "cwd": obj.get("cwd"),
                "is_sidechain": bool(obj.get("isSidechain")),
                "agent_id": obj.get("agentId") or "",
                "version": obj.get("version") or "",
                "tokens": usage_tokens(usage),
            }


def discover(projects_dir: Path):
    """Map session id -> (project slug, [transcript paths]).

    Subagent transcripts live at <project>/<session-id>/subagents/*.jsonl and
    carry the parent session's id. They are real spend on the parent session,
    so they are folded in rather than treated as sessions of their own.
    """
    sessions: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for path in sorted(projects_dir.rglob("*.jsonl")):
        rel = path.relative_to(projects_dir)
        slug = rel.parts[0]
        if len(rel.parts) == 2:
            session_id = path.stem
        elif len(rel.parts) >= 3:
            session_id = rel.parts[1]  # <project>/<session-id>/subagents/agent-*.jsonl
        else:
            continue
        sessions[(slug, session_id)].append(path)
    return sessions


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------


def build(projects_dir: Path, repos: list[str] | None, prices: Prices):
    """Return (session rows, turn rows, skipped repo names)."""
    session_rows, turn_rows = [], []
    skipped: set[str] = set()
    wanted = {r.lower() for r in repos} if repos else None

    for (slug, session_id), paths in sorted(discover(projects_dir).items()):
        turns = []
        for path in sorted(paths):
            turns.extend(iter_turns(path))
        if not turns:
            continue

        turns.sort(key=lambda t: (t["timestamp"] or "", t["message_id"]))
        cwds = [t["cwd"] for t in turns if t["cwd"]]
        repo = repo_of(
            max(set(cwds), key=cwds.count) if cwds else None,
            slug,
        )
        if wanted is not None and repo.lower() not in wanted:
            skipped.add(repo)
            continue

        totals = dict.fromkeys(TOKEN_FIELDS, 0)
        cost_total = 0.0
        unpriced = 0
        models: dict[str, int] = defaultdict(int)
        stamps = []

        for index, turn in enumerate(turns, start=1):
            tok = turn["tokens"]
            cost = prices.cost(turn["model"], tok)
            if cost is None:
                unpriced += 1
                cost = 0.0
            cost_total += cost
            models[turn["model"]] += 1
            for field in TOKEN_FIELDS:
                totals[field] += tok[field]
            ts = parse_ts(turn["timestamp"])
            if ts:
                stamps.append(ts)

            billed_in = tok["input"] + tok["cache_read"] + tok["cache_write_5m"] + tok["cache_write_1h"]
            turn_rows.append(
                {
                    "session_id": session_id,
                    "repo": repo,
                    "turn_index": index,
                    "timestamp": turn["timestamp"] or "",
                    "model": turn["model"],
                    "is_sidechain": int(turn["is_sidechain"]),
                    "agent_id": turn["agent_id"],
                    "input_tokens": tok["input"],
                    "output_tokens": tok["output"],
                    "cache_read_tokens": tok["cache_read"],
                    "cache_write_5m_tokens": tok["cache_write_5m"],
                    "cache_write_1h_tokens": tok["cache_write_1h"],
                    "context_tokens": billed_in,
                    "cost_usd": round(cost, 6),
                    "priced": int(prices.resolve(turn["model"]) in prices.models),
                }
            )

        billed_input = (
            totals["input"] + totals["cache_read"] + totals["cache_write_5m"] + totals["cache_write_1h"]
        )
        wall = (
            (max(stamps) - min(stamps)).total_seconds() if len(stamps) > 1 else 0.0
        )
        session_rows.append(
            {
                "session_id": session_id,
                "repo": repo,
                "project_slug": slug,
                "started_at": min(stamps).isoformat() if stamps else "",
                "ended_at": max(stamps).isoformat() if stamps else "",
                "wall_clock_s": round(wall, 1),
                "turns": len(turns),
                "sidechain_turns": sum(1 for t in turns if t["is_sidechain"]),
                "models": ";".join(sorted(models)),
                "input_tokens": totals["input"],
                "output_tokens": totals["output"],
                "cache_read_tokens": totals["cache_read"],
                "cache_write_5m_tokens": totals["cache_write_5m"],
                "cache_write_1h_tokens": totals["cache_write_1h"],
                "billed_input_tokens": billed_input,
                "cache_hit_rate": round(totals["cache_read"] / billed_input, 4)
                if billed_input
                else 0.0,
                "cost_usd": round(cost_total, 4),
                "cost_per_turn_usd": round(cost_total / len(turns), 4),
                "unpriced_turns": unpriced,
            }
        )

    return session_rows, turn_rows, skipped


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def money(value: float) -> str:
    return f"${value:,.2f}"


def bar(fraction: float, width: int = 28) -> str:
    filled = int(round(max(0.0, min(1.0, fraction)) * width))
    return "#" * filled + "." * (width - filled)


def report(session_rows, turn_rows, prices: Prices, curve_bins: int) -> None:
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


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo",
        action="append",
        metavar="NAME",
        help="Repo to include. Repeatable. REQUIRED — transcripts include "
        "work-adjacent sessions, so inclusion is always explicit.",
    )
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    parser.add_argument("--prices", type=Path, default=Path(__file__).parent / "prices.json")
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--curve-bins", type=int, default=12)
    parser.add_argument(
        "--off-peak",
        action="store_true",
        help="Bill Ollama Cloud rows (off_peak: true in prices.json) at half "
        "rate: weekends + weekdays outside 12:00-18:00 UTC. First-party "
        "Claude rows never get the discount.",
    )
    parser.add_argument(
        "--list-repos",
        action="store_true",
        help="Print repo names and session counts, then exit. No tokens, no "
        "costs, no content — safe to run before choosing a filter.",
    )
    args = parser.parse_args(argv)

    if not args.projects_dir.is_dir():
        sys.exit(f"no transcripts at {args.projects_dir}")

    if args.list_repos:
        counts: dict[str, int] = defaultdict(int)
        for (slug, session_id), paths in discover(args.projects_dir).items():
            cwd = None
            for path in paths:
                for turn in iter_turns(path):
                    if turn["cwd"]:
                        cwd = turn["cwd"]
                        break
                if cwd:
                    break
            counts[repo_of(cwd, slug)] += 1
        print(f"{'repo':<28}sessions")
        for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"{name:<28}{n}")
        print("\nPass the ones you want with --repo. Nothing is read into the CSVs until you do.")
        return 0

    if not args.repo:
        parser.error(
            "--repo is required. Run --list-repos to see what is on disk. "
            "This is a guardrail, not an oversight: shipping the wrong "
            "sessions anywhere should take a deliberate act."
        )

    prices = Prices(args.prices)
    prices.off_peak = bool(args.off_peak)
    session_rows, turn_rows, skipped = build(args.projects_dir, args.repo, prices)

    if not session_rows:
        sys.exit(
            f"no sessions matched --repo {', '.join(args.repo)}. "
            f"On disk: {', '.join(sorted(skipped)) or '(nothing)'}"
        )

    session_csv = args.out_dir / "sessions.csv"
    turn_csv = args.out_dir / "turns.csv"
    write_csv(session_csv, session_rows)
    write_csv(turn_csv, turn_rows)

    report(session_rows, turn_rows, prices, args.curve_bins)
    print(f"   wrote {session_csv}  ({len(session_rows)} rows)")
    print(f"   wrote {turn_csv}  ({len(turn_rows)} rows)")
    if skipped:
        print(f"   excluded by --repo: {', '.join(sorted(skipped))}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())